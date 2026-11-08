import re

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

from . import permissions
from .models import Color, Size, Warehouse

User = get_user_model()
HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


class ColorForm(forms.ModelForm):
    class Meta:
        model = Color
        fields = ["name", "hex_code", "code"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "مثلاً مشکی", "maxlength": 50}),
            "hex_code": forms.TextInput(attrs={"type": "color"}),
            "code": forms.TextInput(attrs={"placeholder": "BLK", "dir": "ltr", "maxlength": 10}),
        }

    def clean_hex_code(self):
        value = self.cleaned_data["hex_code"].strip()
        if not HEX_RE.match(value):
            raise forms.ValidationError("کد رنگ باید مثل #1a2b3c باشد.")
        return value.lower()

    def clean_code(self):
        return self.cleaned_data["code"].strip().upper()

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        qs = Color.objects.filter(name__iexact=name).exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("رنگی با این نام قبلاً ثبت شده است.")
        return name


class SizeForm(forms.ModelForm):
    class Meta:
        model = Size
        fields = ["name", "sort_order"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "S، M، XL یا 42", "dir": "ltr", "maxlength": 20}),
            "sort_order": forms.NumberInput(attrs={"min": 0, "dir": "ltr", "inputmode": "numeric"}),
        }
        help_texts = {"sort_order": "عدد کوچک‌تر زودتر نمایش داده می‌شود (مثلاً S=1، M=2، L=3)."}

    def clean_name(self):
        name = self.cleaned_data["name"].strip().upper()
        qs = Size.objects.filter(name__iexact=name).exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("این سایز قبلاً ثبت شده است.")
        return name


class WarehouseForm(forms.ModelForm):
    class Meta:
        model = Warehouse
        fields = ["name", "address", "is_active"]
        labels = {"is_active": "انبار فعال است"}
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "مثلاً انبار مرکزی", "maxlength": 100}),
            "address": forms.TextInput(attrs={"placeholder": "اختیاری", "maxlength": 255}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["is_active"].initial = True

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if Warehouse.objects.filter(name__iexact=name).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("انباری با این نام قبلاً ثبت شده است.")
        return name


class _UserBase(forms.ModelForm):
    role = forms.ChoiceField(label="سطح دسترسی", choices=permissions.CHOICES,
                             help_text="مدیر: همه‌چیز • انباردار: افزودن کالا و ورود/خروج • مشاهده‌گر: فقط مشاهده")
    password1 = forms.CharField(label="رمز عبور", strip=False,
                                widget=forms.PasswordInput(attrs={"dir": "ltr", "autocomplete": "new-password"}))
    password2 = forms.CharField(label="تکرار رمز عبور", strip=False,
                                widget=forms.PasswordInput(attrs={"dir": "ltr", "autocomplete": "new-password"}))

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "is_active"]
        labels = {"username": "نام کاربری", "first_name": "نام", "last_name": "نام خانوادگی", "is_active": "حساب فعال است"}
        widgets = {"username": forms.TextInput(attrs={"dir": "ltr", "autocomplete": "off"})}
        help_texts = {"username": "حروف انگلیسی، عدد و @ . + - _", "is_active": ""}

    field_order = ["username", "first_name", "last_name", "role", "password1", "password2", "is_active"]
    password_required = True

    def __init__(self, *args, acting_user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.acting_user = acting_user
        self.fields["password1"].required = self.password_required
        self.fields["password2"].required = self.password_required
        self.fields["is_active"].initial = True

    def clean(self):
        data = super().clean()
        p1, p2 = data.get("password1"), data.get("password2")
        if p1 or p2:
            if p1 != p2:
                self.add_error("password2", "رمز عبور و تکرار آن یکسان نیستند.")
            else:
                try:
                    validate_password(p1, self.instance)
                except forms.ValidationError as exc:
                    self.add_error("password1", exc)
        return data

    def _commit(self, user):
        user.save()
        permissions.set_role(user, self.cleaned_data["role"])
        return user


class UserCreateForm(_UserBase):
    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        user.is_superuser = user.is_staff = False
        return self._commit(user)


class UserEditForm(_UserBase):
    password_required = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["role"].initial = permissions.get_role(self.instance)
        self.fields["password1"].label = "رمز عبور جدید"
        self.fields["password1"].help_text = "اگر نمی‌خواهید رمز عوض شود، خالی بگذارید."
        self.is_self = self.acting_user is not None and self.acting_user.pk == self.instance.pk

    def clean(self):
        data = super().clean()
        role, active = data.get("role"), data.get("is_active")
        was_admin = permissions.get_role(self.instance) == permissions.ADMIN and self.instance.is_active
        if was_admin and role is not None and active is not None and (role != permissions.ADMIN or not active):
            if self.is_self:
                raise forms.ValidationError("نمی‌توانید سطح دسترسی یا فعال بودن حساب خودتان را کاهش دهید.")
            others = User.objects.filter(is_superuser=True, is_active=True).exclude(pk=self.instance.pk)
            if not others.exists():
                raise forms.ValidationError("حداقل یک مدیر فعال باید در سامانه باقی بماند.")
        return data

    def save(self, commit=True):
        user = super().save(commit=False)
        if self.cleaned_data.get("password1"):
            user.set_password(self.cleaned_data["password1"])
        return self._commit(user)