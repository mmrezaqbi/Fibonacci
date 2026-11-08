from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import F, Sum


class Category(models.Model):
    name = models.CharField("نام دسته‌بندی", max_length=100, unique=True)

    class Meta:
        verbose_name = "دسته‌بندی"
        verbose_name_plural = "دسته‌بندی‌ها"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Warehouse(models.Model):
    name = models.CharField("نام انبار", max_length=100, unique=True)
    address = models.CharField("آدرس", max_length=255, blank=True)
    is_active = models.BooleanField("فعال", default=True)

    class Meta:
        verbose_name = "انبار"
        verbose_name_plural = "انبارها"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Color(models.Model):
    name = models.CharField("نام رنگ", max_length=50, unique=True)
    code = models.CharField("کد کوتاه", max_length=10, blank=True, help_text="برای ساخت کد کالا، مثلاً BLK")
    hex_code = models.CharField("کد رنگ (HEX)", max_length=7, default="#000000")

    class Meta:
        verbose_name = "رنگ"
        verbose_name_plural = "رنگ‌ها"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Size(models.Model):
    name = models.CharField("سایز", max_length=20, unique=True, help_text="مثلاً S، M، XL یا 42")
    sort_order = models.PositiveSmallIntegerField("ترتیب نمایش", default=0)

    class Meta:
        verbose_name = "سایز"
        verbose_name_plural = "سایزها"
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


class Product(models.Model):
    """مدل کلی پوشاک (مثلاً «پیراهن کتان مردانه»). رنگ و سایز در ProductVariant نگهداری می‌شود."""

    class Gender(models.TextChoices):
        MEN = "men", "مردانه"
        WOMEN = "women", "زنانه"
        BOY = "boy", "پسرانه"
        GIRL = "girl", "دخترانه"
        UNISEX = "unisex", "یونیسکس"

    class Season(models.TextChoices):
        SPRING = "spring", "بهار"
        SUMMER = "summer", "تابستان"
        AUTUMN = "autumn", "پاییز"
        WINTER = "winter", "زمستان"
        ALL = "all", "چهارفصل"

    name = models.CharField("نام محصول", max_length=200, db_index=True)
    sku = models.CharField("کد مدل", max_length=50, unique=True)
    brand = models.CharField("برند", max_length=100, blank=True)
    category = models.ForeignKey(
        Category, verbose_name="دسته‌بندی",
        on_delete=models.SET_NULL, null=True, blank=True, related_name="products",
    )
    gender = models.CharField("جنسیت", max_length=10, choices=Gender.choices, default=Gender.UNISEX)
    season = models.CharField("فصل", max_length=10, choices=Season.choices, default=Season.ALL)
    material = models.CharField("جنس پارچه", max_length=100, blank=True)
    description = models.TextField("توضیحات", blank=True)
    image = models.ImageField("تصویر", upload_to="products/%Y/%m/", blank=True, null=True)
    price = models.DecimalField("قیمت پایه", max_digits=14, decimal_places=0, default=0)
    is_active = models.BooleanField("فعال", default=True)
    created_at = models.DateTimeField("تاریخ ایجاد", auto_now_add=True)
    updated_at = models.DateTimeField("آخرین ویرایش", auto_now=True)

    class Meta:
        verbose_name = "محصول"
        verbose_name_plural = "محصولات"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.sku})"

    @property
    def total_stock(self):
        return self.variants.aggregate(s=Sum("stock"))["s"] or 0

    @property
    def colors(self):
        return Color.objects.filter(variants__product=self).distinct()

    @property
    def sizes(self):
        return Size.objects.filter(variants__product=self).distinct()

    def stock_matrix(self):
        """
        جدول موجودی رنگ × سایز، مناسب نمایش در صفحه جزئیات:
        {"مشکی": {"S": 4, "M": 10}, "سفید": {"S": 0, "M": 7}}
        """
        matrix = {}
        for v in self.variants.select_related("color", "size").order_by("color__name", "size__sort_order"):
            matrix.setdefault(v.color.name, {})[v.size.name] = v.stock
        return matrix

    def generate_variants(self, colors, sizes, min_stock=3):
        """ساخت خودکار همه ترکیب‌های رنگ و سایز (ترکیب‌های موجود دست نمی‌خورند)."""
        created = []
        for color in colors:
            for size in sizes:
                variant, was_created = ProductVariant.objects.get_or_create(
                    product=self, color=color, size=size,
                    defaults={"min_stock": min_stock},
                )
                if was_created:
                    created.append(variant)
        return created


class ProductVariant(models.Model):
    """یک ترکیب مشخص از محصول: رنگ + سایز، با موجودی مستقل."""

    product = models.ForeignKey(
        Product, verbose_name="محصول", on_delete=models.CASCADE, related_name="variants"
    )
    color = models.ForeignKey(
        Color, verbose_name="رنگ", on_delete=models.PROTECT, related_name="variants"
    )
    size = models.ForeignKey(
        Size, verbose_name="سایز", on_delete=models.PROTECT, related_name="variants"
    )
    sku = models.CharField("کد کالا", max_length=80, unique=True, blank=True)
    barcode = models.CharField("بارکد", max_length=64, blank=True, db_index=True)
    price = models.DecimalField(
        "قیمت (اختیاری)", max_digits=14, decimal_places=0, null=True, blank=True,
        help_text="اگر خالی باشد، قیمت پایه محصول استفاده می‌شود.",
    )
    stock = models.PositiveIntegerField("موجودی", default=0, editable=False)
    min_stock = models.PositiveIntegerField("حداقل موجودی", default=3)
    is_active = models.BooleanField("فعال", default=True)

    class Meta:
        verbose_name = "تنوع محصول (رنگ/سایز)"
        verbose_name_plural = "تنوع‌های محصول (رنگ/سایز)"
        ordering = ["product__name", "color__name", "size__sort_order"]
        constraints = [
            models.UniqueConstraint(fields=["product", "color", "size"], name="unique_product_color_size"),
        ]
        indexes = [models.Index(fields=["is_active", "stock"])]

    def __str__(self):
        return f"{self.product.name} | {self.color.name} | {self.size.name}"

    def save(self, *args, **kwargs):
        if not self.sku:
            color_part = self.color.code or str(self.color_id)
            self.sku = f"{self.product.sku}-{color_part}-{self.size.name}".upper()
        super().save(*args, **kwargs)

    # نام‌ها و ویژگی‌هایی که داشبورد استفاده می‌کند
    @property
    def name(self):
        return str(self)

    @property
    def unit_price(self):
        return self.price if self.price is not None else self.product.price

    @property
    def is_low_stock(self):
        return self.stock <= self.min_stock

    @property
    def percent(self):
        if not self.min_stock:
            return 100
        return min(100, round(self.stock / self.min_stock * 100))


class StockTransaction(models.Model):
    class Type(models.TextChoices):
        IN = "in", "ورود"
        OUT = "out", "خروج"

    variant = models.ForeignKey(
        ProductVariant, verbose_name="کالا (رنگ/سایز)",
        on_delete=models.PROTECT, related_name="transactions",
    )
    warehouse = models.ForeignKey(
        Warehouse, verbose_name="انبار", on_delete=models.PROTECT, related_name="transactions"
    )
    type = models.CharField("نوع", max_length=3, choices=Type.choices)
    quantity = models.PositiveIntegerField("تعداد")
    note = models.CharField("توضیحات", max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="ثبت‌کننده",
        on_delete=models.SET_NULL, null=True, blank=True, related_name="stock_transactions",
    )
    created_at = models.DateTimeField("تاریخ", auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "تراکنش انبار"
        verbose_name_plural = "تراکنش‌های انبار"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_type_display()} {self.quantity} × {self.variant}"

    def clean(self):
        if self.quantity is not None and self.quantity <= 0:
            raise ValidationError({"quantity": "تعداد باید بزرگ‌تر از صفر باشد."})

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("تراکنش ثبت‌شده قابل ویرایش نیست؛ یک تراکنش جبرانی ثبت کنید.")
        self.full_clean(exclude=["created_by"])

        with transaction.atomic():
            variant = ProductVariant.objects.select_for_update().get(pk=self.variant_id)

            if self.type == self.Type.OUT:
                if self.quantity > variant.stock:
                    raise ValidationError(
                        f"موجودی کافی نیست (موجودی فعلی {variant}: {variant.stock})."
                    )
                ProductVariant.objects.filter(pk=variant.pk).update(stock=F("stock") - self.quantity)
            else:
                ProductVariant.objects.filter(pk=variant.pk).update(stock=F("stock") + self.quantity)

            super().save(*args, **kwargs)


# ===========================================================================
# اتصال به ووکامرس (وردپرس)
# ===========================================================================
class WooSettings(models.Model):
    """تنظیمات اتصال به ووکامرس (فقط یک ردیف)."""

    site_url = models.CharField("آدرس سایت", max_length=255, blank=True, help_text="مثلاً https://example.com")
    consumer_key = models.CharField("Consumer key", max_length=120, blank=True)
    consumer_secret = models.CharField("Consumer secret", max_length=120, blank=True)
    webhook_secret = models.CharField("کلید وب‌هوک (Secret)", max_length=120, blank=True)
    default_warehouse = models.ForeignKey(
        Warehouse, verbose_name="انبار ثبت سفارش‌های سایت", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
        help_text="خروج کالا بابت سفارش‌های سایت از این انبار ثبت می‌شود.",
    )
    enabled = models.BooleanField("همگام‌سازی فعال است", default=False)
    sync_started_at = models.DateTimeField("شروع همگام‌سازی", null=True, blank=True, editable=False)
    last_order_pull = models.DateTimeField("آخرین دریافت سفارش‌ها", null=True, blank=True, editable=False)

    class Meta:
        verbose_name = "تنظیمات ووکامرس"
        verbose_name_plural = "تنظیمات ووکامرس"

    def __str__(self):
        return "تنظیمات ووکامرس"

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def configured(self):
        return bool(self.site_url and self.consumer_key and self.consumer_secret)


class WooProductLink(models.Model):
    product = models.OneToOneField(Product, on_delete=models.CASCADE, related_name="woo_link")
    woo_id = models.PositiveIntegerField("شناسه در ووکامرس")


class WooVariantLink(models.Model):
    variant = models.OneToOneField(ProductVariant, on_delete=models.CASCADE, related_name="woo_link")
    woo_id = models.PositiveIntegerField("شناسه‌ی تنوع در ووکامرس")


class WooOrder(models.Model):
    """سفارش‌های سایت که موجودی‌شان در انبار اعمال شده؛ برای جلوگیری از کسر تکراری."""

    order_id = models.BigIntegerField(unique=True)
    status = models.CharField(max_length=30, blank=True)
    deducted = models.BooleanField(default=False)
    lines = models.JSONField(default=list, blank=True)  # [{"variant": id, "qty": n}]
    note = models.CharField(max_length=500, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]


class WooLog(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    ok = models.BooleanField(default=True)
    message = models.CharField(max_length=500)

    class Meta:
        ordering = ["-id"]


from django.db.models.signals import post_save  # noqa: E402
from django.dispatch import receiver  # noqa: E402


@receiver(post_save, sender=StockTransaction)
def _push_stock_to_woocommerce(sender, instance, created, **kwargs):
    """بعد از هر ورود/خروج، موجودی همان کالا به ووکامرس ارسال می‌شود (پس‌زمینه، بدون کند کردن فرم)."""
    if created and not getattr(instance, "_skip_woo", False):
        from .woo_sync import schedule_push
        schedule_push(instance.variant_id)