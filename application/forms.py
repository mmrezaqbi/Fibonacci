from django import forms
from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Color, Product, Size, StockTransaction, Warehouse
from .widgets import MoneyInput


def qty_name(color, size):
    """نام فیلد موجودی برای یک ترکیب رنگ/سایز، مثلاً qty_3_7"""
    return f"qty_{color.pk}_{size.pk}"


class ProductCreateForm(forms.ModelForm):
    """
    ثبت محصول پوشاک همراه با رنگ‌ها، سایزها و موجودی جداگانه‌ی هر ترکیب.

    برای هر ترکیب رنگ × سایز یک فیلد عددی (qty_<رنگ>_<سایز>) ساخته می‌شود.
    فقط ترکیب‌هایی که هم رنگ و هم سایزشان انتخاب شده باشد ثبت می‌شوند؛
    خانه‌ی خالی یعنی موجودی صفر. برای هر موجودی بزرگ‌تر از صفر یک تراکنش «ورود» ثبت می‌شود.
    """

    colors = forms.ModelMultipleChoiceField(
        label="رنگ‌ها",
        queryset=Color.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        error_messages={"required": "حداقل یک رنگ انتخاب کنید."},
    )
    sizes = forms.ModelMultipleChoiceField(
        label="سایزها",
        queryset=Size.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        error_messages={"required": "حداقل یک سایز انتخاب کنید."},
    )
    min_stock = forms.IntegerField(
        label="حداقل موجودی هر ترکیب", min_value=0, initial=3,
        help_text="کمتر یا مساوی این عدد، هشدار کم‌موجودی نمایش داده می‌شود.",
    )
    warehouse = forms.ModelChoiceField(
        label="انبار", queryset=Warehouse.objects.filter(is_active=True),
        required=False, empty_label="— انتخاب انبار —",
        help_text="اگر برای ترکیب‌ها موجودی وارد کرده‌اید، انتخاب انبار الزامی است.",
    )

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
            "price": MoneyInput(attrs={"placeholder": "تومان"}),
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields["category"].empty_label = "— بدون دسته‌بندی —"

        # یک فیلد موجودی برای هر ترکیب رنگ × سایز
        self._colors = list(Color.objects.all())
        self._sizes = list(Size.objects.all())
        for color in self._colors:
            for size in self._sizes:
                self.fields[qty_name(color, size)] = forms.IntegerField(
                    label=f"{color.name} / {size.name}",
                    min_value=0, max_value=1_000_000, required=False,
                    widget=forms.NumberInput(attrs={
                        "class": "qty", "min": 0, "placeholder": "0", "inputmode": "numeric",
                    }),
                )

    # ---- کمک‌ها برای قالب ----
    @property
    def matrix_sizes(self):
        return self._sizes

    def matrix_rows(self):
        """[(رنگ, [(سایز, فیلد), ...]), ...] برای رسم جدول"""
        return [
            (color, [(size, self[qty_name(color, size)]) for size in self._sizes])
            for color in self._colors
        ]

    def matrix_errors(self):
        errors = []
        for color in self._colors:
            for size in self._sizes:
                name = qty_name(color, size)
                if name in self.errors:
                    errors.append(f"{color.name} / {size.name}: {self.errors[name][0]}")
        return errors

    # ---- اعتبارسنجی ----
    def clean_sku(self):
        return self.cleaned_data["sku"].strip().upper()

    def clean_colors(self):
        colors = self.cleaned_data["colors"]
        # کد کالای هر تنوع از «کد کوتاه رنگ» ساخته می‌شود؛ کد تکراری باعث تداخل می‌شود
        codes = [c.code.strip().upper() for c in colors if c.code.strip()]
        if len(codes) != len(set(codes)):
            raise ValidationError(
                "دو رنگ انتخاب‌شده «کد کوتاه» یکسان دارند. کد رنگ‌ها را در ادمین اصلاح کنید."
            )
        return colors

    def clean(self):
        cleaned = super().clean()
        colors, sizes = cleaned.get("colors"), cleaned.get("sizes")
        if colors and sizes and not cleaned.get("warehouse"):
            total = sum(
                (cleaned.get(qty_name(c, s)) or 0) for c in colors for s in sizes
            )
            if total > 0:
                self.add_error("warehouse", "برای ثبت موجودی ترکیب‌ها، انبار را انتخاب کنید.")
        return cleaned

    # ---- ذخیره ----
    def save(self, commit=True):
        # این فرم همیشه ذخیره می‌کند، چون ساخت تنوع‌ها به محصول ذخیره‌شده نیاز دارد.
        colors = list(self.cleaned_data["colors"])
        sizes = list(self.cleaned_data["sizes"])
        warehouse = self.cleaned_data.get("warehouse")
        user = self.user if getattr(self.user, "pk", None) else None

        with transaction.atomic():
            product = super().save(commit=True)
            created = product.generate_variants(colors, sizes, min_stock=self.cleaned_data["min_stock"])
            variants = {(v.color_id, v.size_id): v for v in created}

            for color in colors:
                for size in sizes:
                    qty = self.cleaned_data.get(qty_name(color, size)) or 0
                    if qty > 0 and warehouse:
                        StockTransaction.objects.create(
                            variant=variants[(color.pk, size.pk)],
                            warehouse=warehouse,
                            type=StockTransaction.Type.IN,
                            quantity=qty,
                            note="موجودی اولیه",
                            created_by=user,
                        )
        return product


class StockOutForm(forms.Form):
    """
    ثبت خروج از انبار برای یک محصول.
    برای هر ترکیب رنگ/سایز یک فیلد تعداد (qty_<variant_id>) ساخته می‌شود و برای هر
    تعداد بزرگ‌تر از صفر یک تراکنش «خروج» ثبت می‌شود. همه‌ی خطوط در یک تراکنش دیتابیس
    ذخیره می‌شوند؛ اگر یکی از آن‌ها خطا بدهد، هیچ‌کدام ثبت نمی‌شود.
 
    StockInForm همین فرم را برای «ورود» به کار می‌برد؛ فقط سه ویژگی کلاس تفاوت دارد.
    """
 
    movement_type = StockTransaction.Type.OUT
    limit_to_stock = True  # در خروج، تعداد نباید از موجودی بیشتر باشد
    empty_message = "حداقل برای یک رنگ و سایز، تعداد خروج را وارد کنید."
 
    def _qty_attrs(self, variant):
        attrs = {"class": "qty", "min": 0, "placeholder": "0", "inputmode": "numeric"}
        if self.limit_to_stock:
            attrs["max"] = variant.stock
        return attrs
 
    warehouse = forms.ModelChoiceField(
        label="انبار", queryset=Warehouse.objects.filter(is_active=True),
        empty_label="— انتخاب انبار —",
        error_messages={"required": "انبار را انتخاب کنید."},
    )
    note = forms.CharField(
        label="توضیحات", max_length=255, required=False,
        widget=forms.TextInput(attrs={"placeholder": "مثلاً شماره فاکتور یا نام گیرنده (اختیاری)"}),
    )
 
    def __init__(self, *args, product, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.product = product
        self.user = user
        self.lines = []  # [(variant, qty)] بعد از اعتبارسنجی پر می‌شود
 
        self._variants = list(product.variants.select_related("color", "size"))
        self._colors = sorted({v.color for v in self._variants}, key=lambda c: c.name)
        self._sizes = sorted({v.size for v in self._variants}, key=lambda s: (s.sort_order, s.name))
 
        for v in self._variants:
            self.fields[f"qty_{v.pk}"] = forms.IntegerField(
                label=f"{v.color.name} / {v.size.name}",
                min_value=0, max_value=1_000_000, required=False,
                # ترکیب غیرفعال (و در خروج، ترکیب ناموجود) قابل انتخاب نیست
                disabled=(not v.is_active or (self.limit_to_stock and v.stock == 0)),
                widget=forms.NumberInput(attrs=self._qty_attrs(v)),
            )
 
        warehouses = list(self.fields["warehouse"].queryset[:2])
        if len(warehouses) == 1:
            self.fields["warehouse"].initial = warehouses[0].pk
 
    # ---- کمک‌ها برای قالب ----
    @property
    def matrix_sizes(self):
        return self._sizes
 
    def matrix_rows(self):
        """[(رنگ, [ {variant, field} | None, ... ]), ...]"""
        by_key = {(v.color_id, v.size_id): v for v in self._variants}
        rows = []
        for color in self._colors:
            cells = []
            for size in self._sizes:
                v = by_key.get((color.pk, size.pk))
                cells.append({"variant": v, "field": self[f"qty_{v.pk}"]} if v else None)
            rows.append((color, cells))
        return rows
 
    # ---- اعتبارسنجی ----
    def clean(self):
        cleaned = super().clean()
        lines = []
        for v in self._variants:
            name = f"qty_{v.pk}"
            qty = cleaned.get(name) or 0
            if self.limit_to_stock and qty > v.stock:
                self.add_error(name, f"بیشتر از موجودی است (موجودی: {v.stock})")
            elif qty > 0:
                lines.append((v, qty))
 
        if not self.errors and not lines:
            raise ValidationError(self.empty_message)
        self.lines = lines
        return cleaned
 
    # ---- ذخیره ----
    def save(self):
        """
        تعداد قلم‌ها و مجموع تعداد خروج را برمی‌گرداند.
        اگر در لحظه‌ی ثبت موجودی کافی نباشد (مثلاً کاربر دیگری هم‌زمان خروج زده باشد)،
        StockTransaction ValidationError می‌دهد و کل عملیات برگشت داده می‌شود.
        """
        warehouse = self.cleaned_data["warehouse"]
        note = self.cleaned_data.get("note", "")
        user = self.user if getattr(self.user, "pk", None) else None
 
        with transaction.atomic():
            for variant, qty in self.lines:
                StockTransaction.objects.create(
                    variant=variant, warehouse=warehouse,
                    type=self.movement_type,
                    quantity=qty, note=note, created_by=user,
                )
        return len(self.lines), sum(qty for _, qty in self.lines)
 
 
class StockInForm(StockOutForm):
    """ثبت ورود به انبار: همان ماتریس رنگ × سایز، بدون سقف موجودی، با نوع تراکنش «ورود»."""
 
    movement_type = StockTransaction.Type.IN
    limit_to_stock = False
    empty_message = "حداقل برای یک رنگ و سایز، تعداد ورود را وارد کنید."
 
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["note"].widget.attrs["placeholder"] = (
            "مثلاً شماره فاکتور خرید یا نام تأمین‌کننده (اختیاری)"
        )
