from django.contrib import admin
from django import forms
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.db.models import F, Sum
from django.utils.html import format_html, format_html_join

from .models import (
    Category,
    Color,
    Product,
    ProductVariant,
    Size,
    StockTransaction,
    Warehouse,
)

RED = "#e5484d"
AMBER = "#f5a524"
GREEN = "#30a46c"


# ---------------------------------------------------------------------------
# فیلتر وضعیت موجودی
# ---------------------------------------------------------------------------
class StockStatusFilter(admin.SimpleListFilter):
    title = "وضعیت موجودی"
    parameter_name = "stock_status"

    def lookups(self, request, model_admin):
        return [("out", "ناموجود"), ("low", "کم‌موجود"), ("ok", "موجودی کافی")]

    def queryset(self, request, queryset):
        if self.value() == "out":
            return queryset.filter(stock=0)
        if self.value() == "low":
            return queryset.filter(stock__gt=0, stock__lte=F("min_stock"))
        if self.value() == "ok":
            return queryset.filter(stock__gt=F("min_stock"))
        return queryset


# ---------------------------------------------------------------------------
# مدل‌های پایه
# ---------------------------------------------------------------------------
@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "product_count")
    search_fields = ("name",)

    @admin.display(description="تعداد محصول")
    def product_count(self, obj):
        return obj.products.count()


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ("name", "address", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "address")


@admin.register(Color)
class ColorAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "swatch")
    search_fields = ("name", "code")

    @admin.display(description="رنگ")
    def swatch(self, obj):
        return format_html(
            '<span style="display:inline-block;width:22px;height:22px;border-radius:6px;'
            'background:{};border:1px solid #888;vertical-align:middle"></span> '
            '<span style="direction:ltr;display:inline-block">{}</span>',
            obj.hex_code, obj.hex_code,
        )


@admin.register(Size)
class SizeAdmin(admin.ModelAdmin):
    list_display = ("name", "sort_order")
    list_editable = ("sort_order",)
    ordering = ("sort_order", "name")
    search_fields = ("name",)


# ---------------------------------------------------------------------------
# محصول + تنوع‌ها (رنگ/سایز)
# ---------------------------------------------------------------------------
class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 0
    fields = ("color", "size", "sku", "barcode", "price", "stock", "min_stock", "is_active")
    readonly_fields = ("stock",)  # موجودی فقط با ثبت تراکنش تغییر می‌کند
    autocomplete_fields = ("color", "size")
    show_change_link = True


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "thumb", "name", "sku", "brand", "category", "gender", "season",
        "price", "colors_display", "sizes_display", "total_stock_display", "is_active",
    )
    list_display_links = ("thumb", "name")
    list_filter = ("is_active", "gender", "season", "category", "brand")
    search_fields = ("name", "sku", "brand", "variants__sku", "variants__barcode")
    list_per_page = 25
    save_on_top = True
    inlines = [ProductVariantInline]
    actions = ["generate_all_variants", "activate", "deactivate"]
    readonly_fields = ("stock_table", "created_at", "updated_at")
    fieldsets = (
        ("اطلاعات اصلی", {"fields": ("name", "sku", "brand", "category", "image", "price", "is_active")}),
        ("مشخصات پوشاک", {"fields": ("gender", "season", "material", "description")}),
        ("جدول موجودی (رنگ × سایز)", {"fields": ("stock_table",)}),
        ("زمان‌ها", {"classes": ("collapse",), "fields": ("created_at", "updated_at")}),
    )

    def get_queryset(self, request):
        return (
            super().get_queryset(request)
            .select_related("category")
            .prefetch_related("variants__color", "variants__size")
            .annotate(_total_stock=Sum("variants__stock"))
        )

    # -- ستون‌های لیست --
    @admin.display(description="تصویر")
    def thumb(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="width:42px;height:42px;object-fit:cover;border-radius:8px">',
                obj.image.url,
            )
        return "—"

    @admin.display(description="رنگ‌ها")
    def colors_display(self, obj):
        colors = {v.color_id: v.color for v in obj.variants.all()}
        if not colors:
            return "—"
        return format_html_join(
            " ",
            '<span title="{}" style="display:inline-block;width:16px;height:16px;border-radius:50%;'
            'background:{};border:1px solid #888;vertical-align:middle"></span>',
            ((c.name, c.hex_code) for c in colors.values()),
        )

    @admin.display(description="سایزها")
    def sizes_display(self, obj):
        sizes = {v.size_id: v.size for v in obj.variants.all()}
        ordered = sorted(sizes.values(), key=lambda s: (s.sort_order, s.name))
        return "، ".join(s.name for s in ordered) or "—"

    @admin.display(description="موجودی کل", ordering="_total_stock")
    def total_stock_display(self, obj):
        total = obj._total_stock or 0
        return format_html('<b style="color:{}">{}</b>', RED if total == 0 else "inherit", total)

    # -- جدول رنگ × سایز در صفحه ویرایش --
    @admin.display(description="جدول موجودی")
    def stock_table(self, obj):
        if not obj.pk:
            return "ابتدا محصول را ذخیره کنید، سپس رنگ و سایز اضافه کنید."

        variants = list(obj.variants.select_related("color", "size"))
        if not variants:
            return "هنوز رنگ و سایزی برای این محصول تعریف نشده است."

        sizes = sorted({v.size for v in variants}, key=lambda s: (s.sort_order, s.name))
        by_color = {}
        for v in variants:
            by_color.setdefault(v.color.name, {})[v.size_id] = v.stock

        header = format_html_join("", "<th style='padding:6px 14px'>{}</th>", ((s.name,) for s in sizes))

        def cells(row):
            items = []
            for s in sizes:
                qty = row.get(s.id)
                if qty is None:
                    items.append(("opacity:.35", "—"))
                elif qty == 0:
                    items.append((f"color:{RED};font-weight:700", qty))
                else:
                    items.append(("", qty))
            return format_html_join("", "<td style='padding:6px 14px;text-align:center;{}'>{}</td>", items)

        rows = format_html_join(
            "",
            "<tr><th style='padding:6px 14px;text-align:right'>{}</th>{}</tr>",
            ((color, cells(row)) for color, row in by_color.items()),
        )
        return format_html(
            "<table style='border-collapse:collapse'><tr><th></th>{}</tr>{}</table>", header, rows
        )

    # -- اکشن‌ها --
    @admin.action(description="ساخت همه ترکیب‌های رنگ × سایز (از میان همه رنگ‌ها و سایزهای ثبت‌شده)")
    def generate_all_variants(self, request, queryset):
        colors = list(Color.objects.all())
        sizes = list(Size.objects.all())
        if not colors or not sizes:
            self.message_user(request, "ابتدا رنگ‌ها و سایزها را تعریف کنید.", messages.WARNING)
            return
        total = sum(len(p.generate_variants(colors, sizes)) for p in queryset)
        self.message_user(request, f"{total} ترکیب جدید ساخته شد.", messages.SUCCESS)

    @admin.action(description="فعال کردن")
    def activate(self, request, queryset):
        self.message_user(request, f"{queryset.update(is_active=True)} محصول فعال شد.")

    @admin.action(description="غیرفعال کردن")
    def deactivate(self, request, queryset):
        self.message_user(request, f"{queryset.update(is_active=False)} محصول غیرفعال شد.")


# ---------------------------------------------------------------------------
# تنوع محصول
# ---------------------------------------------------------------------------
@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = ("sku", "product", "color", "size", "stock", "min_stock", "status", "is_active")
    list_filter = (StockStatusFilter, "is_active", "color", "size", "product__category")
    list_editable = ("min_stock",)
    search_fields = ("sku", "barcode", "product__name", "product__sku")
    list_select_related = ("product", "color", "size")
    autocomplete_fields = ("product", "color", "size")
    readonly_fields = ("stock",)
    list_per_page = 40

    @admin.display(description="وضعیت")
    def status(self, obj):
        if obj.stock == 0:
            return format_html('<b style="color:{}">ناموجود</b>', RED)
        if obj.is_low_stock:
            return format_html('<b style="color:{}">کم‌موجود</b>', AMBER)
        return format_html('<span style="color:{}">موجود</span>', GREEN)


# ---------------------------------------------------------------------------
# تراکنش‌های انبار: فقط ثبت و مشاهده (بدون ویرایش و حذف)
# ---------------------------------------------------------------------------
class StockTransactionForm(forms.ModelForm):
    class Meta:
        model = StockTransaction
        fields = ("variant", "warehouse", "type", "quantity", "note")

    def clean(self):
        cleaned = super().clean()
        variant = cleaned.get("variant")
        type_ = cleaned.get("type")
        qty = cleaned.get("quantity")
        if variant and qty and type_ == StockTransaction.Type.OUT and qty > variant.stock:
            raise ValidationError(
                f"موجودی کافی نیست. موجودی فعلی «{variant}»: {variant.stock}"
            )
        return cleaned


@admin.register(StockTransaction)
class StockTransactionAdmin(admin.ModelAdmin):
    form = StockTransactionForm
    list_display = ("created_at", "variant", "type_badge", "quantity", "warehouse", "created_by")
    list_filter = ("type", "warehouse", "created_at")
    search_fields = ("variant__sku", "variant__product__name", "note")
    list_select_related = ("variant__product", "variant__color", "variant__size", "warehouse", "created_by")
    autocomplete_fields = ("variant",)
    date_hierarchy = "created_at"
    list_per_page = 40

    def get_fields(self, request, obj=None):
        fields = ["variant", "warehouse", "type", "quantity", "note"]
        return fields + ["created_by", "created_at"] if obj else fields

    # تراکنش ثبت‌شده فقط قابل مشاهده است
    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        obj.created_by = request.user
        super().save_model(request, obj, form, change)

    @admin.display(description="نوع", ordering="type")
    def type_badge(self, obj):
        if obj.type == StockTransaction.Type.IN:
            return format_html('<b style="color:{}">▲ ورود</b>', GREEN)
        return format_html('<b style="color:{}">▼ خروج</b>', RED)
