import re

from django import forms
from django.contrib.auth import get_user_model
from django.db import transaction
from django.contrib.auth.password_validation import validate_password

from . import permissions
from .models import Color, Size, Warehouse , Category , Product

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




# ---------------------------------------------------------------------------
# ویرایش و حذف کالا (با تأیید رمز مدیر)
# ---------------------------------------------------------------------------
def _verify_admin(user, raw_password):
    return bool(
        user and getattr(user, "is_active", False)
        and user.is_superuser and user.check_password(raw_password)
    )


def _admin_password_field():
    return forms.CharField(
        label="رمز عبور مدیر", strip=False,
        widget=forms.PasswordInput(attrs={"dir": "ltr", "autocomplete": "current-password"}),
        help_text="برای تأیید این عملیات، رمز عبور حساب مدیر (سوپر ادمین) را وارد کنید.",
    )


class ProductEditForm(forms.ModelForm):
    add_colors = forms.ModelMultipleChoiceField(
        label="افزودن رنگ‌های جدید", queryset=Color.objects.none(), required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    add_sizes = forms.ModelMultipleChoiceField(
        label="افزودن سایزهای جدید", queryset=Size.objects.none(), required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    new_min_stock = forms.IntegerField(
        label="حداقل موجودی ترکیب‌های جدید", min_value=0, initial=3, required=False,
        help_text="فقط برای ترکیب‌هایی که الان ساخته می‌شوند؛ موجودی آن‌ها صفر است و از «ورود» ثبت می‌شود.",
    )
    admin_password = _admin_password_field()

    class Meta:
        model = Product
        fields = [
            "name", "sku", "brand", "category", "gender", "season",
            "material", "price", "image", "description", "is_active",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "مثلاً پیراهن کتان مردانه"}),
            "sku": forms.TextInput(attrs={"placeholder": "SH100", "dir": "ltr"}),
            "brand": forms.TextInput(attrs={"placeholder": "اختیاری"}),
            "material": forms.TextInput(attrs={"placeholder": "مثلاً کتان، پنبه"}),
            "price": forms.NumberInput(attrs={"placeholder": "تومان", "min": 0}),
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, acting_user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.acting_user = acting_user
        self.created_variants = []
        self.fields["category"].empty_label = "— بدون دسته‌بندی —"
        # فقط رنگ/سایزهایی که این کالا هنوز ندارد
        self.fields["add_colors"].queryset = Color.objects.exclude(variants__product=self.instance)
        self.fields["add_sizes"].queryset = Size.objects.exclude(variants__product=self.instance)

    def clean_sku(self):
        return self.cleaned_data["sku"].strip().upper()

    def clean_add_colors(self):
        new = list(self.cleaned_data["add_colors"])
        if not new:
            return new
        current = list(Color.objects.filter(variants__product=self.instance).distinct())
        codes = [c.code.strip().upper() for c in current + new if c.code.strip()]
        if len(codes) != len(set(codes)):
            raise forms.ValidationError(
                "رنگ انتخاب‌شده «کد کوتاه» تکراری با رنگ‌های این کالا دارد. کد رنگ‌ها را در تنظیمات اصلاح کنید."
            )
        return new

    def clean_admin_password(self):
        pw = self.cleaned_data["admin_password"]
        if not _verify_admin(self.acting_user, pw):
            raise forms.ValidationError("رمز عبور مدیر اشتباه است.")
        return pw

    def save(self, commit=True):
        with transaction.atomic():
            existing_colors = list(Color.objects.filter(variants__product=self.instance).distinct())
            existing_sizes = list(Size.objects.filter(variants__product=self.instance).distinct())
            product = super().save(commit=True)
            new_colors = list(self.cleaned_data.get("add_colors") or [])
            new_sizes = list(self.cleaned_data.get("add_sizes") or [])
            if new_colors or new_sizes:
                min_stock = self.cleaned_data.get("new_min_stock")
                self.created_variants = product.generate_variants(
                    existing_colors + new_colors,
                    existing_sizes + new_sizes,
                    min_stock=3 if min_stock is None else min_stock,
                )
        return product


class ProductDeleteForm(forms.Form):
    admin_password = _admin_password_field()
    delete_history = forms.BooleanField(
        label="تراکنش‌های ورود و خروج این کالا هم برای همیشه حذف شود",
        required=False,
    )

    def __init__(self, *args, acting_user=None, has_history=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.acting_user = acting_user
        self.has_history = has_history
        if not has_history:
            del self.fields["delete_history"]

    def clean_admin_password(self):
        pw = self.cleaned_data["admin_password"]
        if not _verify_admin(self.acting_user, pw):
            raise forms.ValidationError("رمز عبور مدیر اشتباه است.")
        return pw

    def clean(self):
        data = super().clean()
        if self.has_history and not data.get("delete_history"):
            self.add_error(
                "delete_history",
                "این کالا سابقه ورود/خروج دارد. برای حذف باید این گزینه را تیک بزنید؛ یا به‌جای حذف، کالا را در ویرایش غیرفعال کنید.",
            )
        return data