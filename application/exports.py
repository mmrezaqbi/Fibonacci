"""خروجی CSV محصولات، مطابق فرمت درون‌ریزی (Import) ووکامرس.

هر کالا یک ردیف «variable» می‌شود و هر ترکیب رنگ/سایز یک ردیف «variation» با موجودی و قیمت مستقل.
کالای بدون هیچ ترکیبی به‌صورت محصول ساده (simple) خارجی می‌شود.
"""
import csv

from django.db.models import Count, F, IntegerField, Prefetch, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.utils import timezone

from .models import Product, ProductVariant
from .permissions import role_required

COLOR_ATTR, SIZE_ATTR = "رنگ", "سایز"

HEADERS = [
    "ID", "Type", "SKU", "Name", "Published", "Visibility in catalog", "Description",
    "Tax status", "Tax class", "In stock?", "Stock", "Low stock amount",
    "Backorders allowed?", "Sold individually?", "Allow customer reviews?",
    "Regular price", "Categories", "Images", "Parent", "Position",
    "Attribute 1 name", "Attribute 1 value(s)", "Attribute 1 visible", "Attribute 1 global", "Attribute 1 default",
    "Attribute 2 name", "Attribute 2 value(s)", "Attribute 2 visible", "Attribute 2 global", "Attribute 2 default",
]


def _val(text):
    """کاما جداکننده‌ی مقدارهای ویژگی در ووکامرس است؛ داخل نام رنگ/سایز به «،» تبدیل می‌شود."""
    return str(text).replace(",", "،").strip()


def _price(value):
    return str(int(value)) if value else ""


def _row():
    return dict.fromkeys(HEADERS, "")


def _filtered_products(request):
    """همان فیلترهای صفحه‌ی لیست کالاها (q, category, gender, stock)."""
    q = request.GET.get("q", "").strip()
    category = request.GET.get("category", "").strip()
    gender = request.GET.get("gender", "").strip()
    stock = request.GET.get("stock", "").strip()

    qs = (
        Product.objects
        .select_related("category")
        .prefetch_related(
            Prefetch("variants", queryset=ProductVariant.objects.select_related("color", "size"))
        )
        .annotate(
            stock_sum=Coalesce(Sum("variants__stock"), Value(0), output_field=IntegerField()),
            low_n=Count("variants", filter=Q(variants__stock__lte=F("variants__min_stock"))),
        )
    )
    if q:
        qs = qs.filter(
            Q(name__icontains=q) | Q(sku__icontains=q) | Q(brand__icontains=q)
            | Q(pk__in=ProductVariant.objects.filter(
                Q(sku__icontains=q) | Q(barcode__icontains=q)
            ).values("product_id"))
        )
    if category.isdigit():
        qs = qs.filter(category_id=int(category))
    if gender in Product.Gender.values:
        qs = qs.filter(gender=gender)
    if stock == "out":
        qs = qs.filter(stock_sum=0)
    elif stock == "low":
        qs = qs.filter(stock_sum__gt=0, low_n__gt=0)
    elif stock == "ok":
        qs = qs.filter(stock_sum__gt=0, low_n=0)
    return qs.order_by("name", "pk")


def _image_url(request, product, with_images):
    if with_images and product.image:
        return request.build_absolute_uri(product.image.url)
    return ""


def _product_rows(request, product, with_images):
    variants = sorted(
        product.variants.all(),
        key=lambda v: (v.color.name, v.size.sort_order, v.size.name),
    )
    published = "1" if product.is_active else "-1"  # غیرفعال ← پیش‌نویس
    category = product.category.name if product.category else ""

    base = _row()
    base.update({
        "SKU": product.sku, "Name": product.name, "Published": published,
        "Visibility in catalog": "visible", "Description": product.description or "",
        "Tax status": "taxable", "Backorders allowed?": "0", "Sold individually?": "0",
        "Allow customer reviews?": "1", "Categories": category,
        "Images": _image_url(request, product, with_images),
    })

    if not variants:  # محصول ساده
        base.update({
            "Type": "simple", "In stock?": "0", "Stock": "0",
            "Regular price": _price(product.price),
        })
        return [base]

    colors = list(dict.fromkeys(_val(v.color.name) for v in variants))
    sizes = list(dict.fromkeys(_val(v.size.name) for v in variants))
    base.update({
        "Type": "variable",
        "In stock?": "1" if any(v.stock > 0 for v in variants) else "0",
        "Position": "0",
        "Attribute 1 name": COLOR_ATTR, "Attribute 1 value(s)": ", ".join(colors),
        "Attribute 1 visible": "1", "Attribute 1 global": "0",
        "Attribute 2 name": SIZE_ATTR, "Attribute 2 value(s)": ", ".join(sizes),
        "Attribute 2 visible": "1", "Attribute 2 global": "0",
    })
    rows = [base]

    for i, v in enumerate(variants):
        row = _row()
        row.update({
            "Type": "variation",
            "SKU": v.sku,
            "Name": f"{product.name} - {v.color.name}, {v.size.name}",
            "Published": "1" if v.is_active else "0",
            "Visibility in catalog": "visible",      # ← جدید (علت خطا)
            "Tax status": "taxable",                 # ← جدید
            "Tax class": "parent",
            "In stock?": "1" if v.stock > 0 else "0",
            "Stock": str(v.stock),
            "Low stock amount": str(v.min_stock),
            "Backorders allowed?": "0",
            "Regular price": _price(v.unit_price),
            "Parent": product.sku,
            "Position": str(i),
            "Attribute 1 name": COLOR_ATTR, "Attribute 1 value(s)": _val(v.color.name), "Attribute 1 global": "0",
            "Attribute 2 name": SIZE_ATTR, "Attribute 2 value(s)": _val(v.size.name), "Attribute 2 global": "0",
        })
        rows.append(row)
    return rows


@role_required("keeper")
def product_export_csv(request):
    with_images = request.GET.get("images") == "1"
    stamp = timezone.localtime().strftime("%Y%m%d-%H%M")

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="woocommerce-products-{stamp}.csv"'
    response.write("\ufeff")  # BOM تا فارسی در اکسل هم درست باز شود (ووکامرس آن را نادیده می‌گیرد)

    writer = csv.DictWriter(response, fieldnames=HEADERS)
    writer.writeheader()
    for product in _filtered_products(request):
        writer.writerows(_product_rows(request, product, with_images))
    return response