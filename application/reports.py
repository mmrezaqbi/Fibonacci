import csv

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Q, Sum
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from .dates import parse_user_date, to_jalali_string
from .models import Category, Product, ProductVariant, StockTransaction, Warehouse

TX_PAGE_SIZE = 25
STOCK_PAGE_SIZE = 30


# ---------------------------------------------------------------------------
# ابزارهای مشترک
# ---------------------------------------------------------------------------
def _jalali_stamp(dt):
    """datetime → «1405/08/16 11:17» (شمسی، ارقام لاتین؛ مناسب خروجی Excel)"""
    local = timezone.localtime(dt)
    return f"{to_jalali_string(local)} {local:%H:%M}"


def _csv_safe(value):
    """جلوگیری از اجرای فرمول در Excel (CSV injection) برای متن‌هایی که با = + - @ شروع می‌شوند."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def _csv_response(filename, header, rows):
    """پاسخ CSV با BOM تا Excel فارسی را درست نشان دهد."""
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.write("﻿")
    writer = csv.writer(response)
    writer.writerow(header)
    for row in rows:
        writer.writerow([_csv_safe(cell) for cell in row])
    return response


def _paginate(request, queryset, size):
    paginator = Paginator(queryset, size)
    page_obj = paginator.get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    params.pop("export", None)
    return {
        "page_obj": page_obj,
        "page_range": list(paginator.get_elided_page_range(page_obj.number, on_each_side=1, on_ends=1)),
        "ellipsis": paginator.ELLIPSIS,
        "total_count": paginator.count,
        "querystring": params.urlencode(),
    }


def _user_name(user):
    if not user:
        return ""
    return user.get_full_name() or user.get_username()


# ---------------------------------------------------------------------------
# صفحه‌ی اصلی گزارش‌ها
# ---------------------------------------------------------------------------
@login_required
def reports_index(request):
    return redirect("application:report_transactions")


# ---------------------------------------------------------------------------
# گزارش تراکنش‌ها
# ---------------------------------------------------------------------------
@login_required
def report_transactions(request):
    q = request.GET.get("q", "").strip()
    # تاریخ‌ها شمسی وارد می‌شوند (مثلاً 1405/08/16)؛ تاریخ میلادی هم پذیرفته می‌شود
    raw_from = request.GET.get("date_from", "").strip()
    raw_to = request.GET.get("date_to", "").strip()
    date_from = parse_user_date(raw_from)
    date_to = parse_user_date(raw_to)
    date_error = bool((raw_from and not date_from) or (raw_to and not date_to))
    ttype = request.GET.get("type", "").strip()
    warehouse = request.GET.get("warehouse", "").strip()

    qs = StockTransaction.objects.select_related(
        "variant__product", "variant__color", "variant__size", "warehouse", "created_by"
    )
    if q:
        qs = qs.filter(
            Q(variant__product__name__icontains=q)
            | Q(variant__product__sku__icontains=q)
            | Q(variant__sku__icontains=q)
            | Q(note__icontains=q)
        )
    if date_from:
        qs = qs.filter(created_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(created_at__date__lte=date_to)
    if ttype in StockTransaction.Type.values:
        qs = qs.filter(type=ttype)
    if warehouse.isdigit():
        qs = qs.filter(warehouse_id=int(warehouse))
    qs = qs.order_by("-created_at", "-pk")

    if request.GET.get("export") == "csv":
        header = ["تاریخ", "نوع", "محصول", "کد مدل", "رنگ", "سایز", "کد کالا",
                  "تعداد", "انبار", "ثبت‌کننده", "توضیحات"]
        rows = (
            [
                _jalali_stamp(t.created_at),
                t.get_type_display(),
                t.variant.product.name,
                t.variant.product.sku,
                t.variant.color.name,
                t.variant.size.name,
                t.variant.sku,
                t.quantity,
                t.warehouse.name,
                _user_name(t.created_by),
                t.note,
            ]
            for t in qs.iterator(chunk_size=2000)
        )
        return _csv_response(f"transactions-{timezone.localdate():%Y%m%d}.csv", header, rows)

    agg = qs.aggregate(
        count=Count("pk"),
        in_qty=Sum("quantity", filter=Q(type=StockTransaction.Type.IN)),
        out_qty=Sum("quantity", filter=Q(type=StockTransaction.Type.OUT)),
    )
    in_qty, out_qty = agg["in_qty"] or 0, agg["out_qty"] or 0
    summary = {"count": agg["count"], "in": in_qty, "out": out_qty, "net": in_qty - out_qty}

    context = _paginate(request, qs, TX_PAGE_SIZE)
    context.update({
        "summary": summary,
        "warehouses": Warehouse.objects.all(),
        "filters": {
            "q": q,
            # تاریخ معتبر به شکل استاندارد شمسی نمایش داده می‌شود؛ ورودی نامعتبر همان‌طور که هست
            "date_from": to_jalali_string(date_from) if date_from else raw_from,
            "date_to": to_jalali_string(date_to) if date_to else raw_to,
            "type": ttype,
            "warehouse": warehouse,
        },
        "date_error": date_error,
        "has_filters": any([q, raw_from, raw_to, ttype, warehouse]),
    })
    return render(request, "report_transactions.html", context)


# ---------------------------------------------------------------------------
# گزارش موجودی (هر ترکیب رنگ/سایز)
# ---------------------------------------------------------------------------
def _stock_status(variant):
    if variant.stock == 0:
        return "out", "ناموجود"
    if variant.stock <= variant.min_stock:
        return "low", "کم‌موجود"
    return "ok", "موجود"


@login_required
def report_stock(request):
    q = request.GET.get("q", "").strip()
    category = request.GET.get("category", "").strip()
    gender = request.GET.get("gender", "").strip()
    status = request.GET.get("status", "").strip()
    include_inactive = request.GET.get("inactive") == "1"

    unit_price = Coalesce("price", "product__price")
    qs = (
        ProductVariant.objects
        .select_related("product", "product__category", "color", "size")
        .annotate(
            unit=unit_price,
            value=ExpressionWrapper(
                F("stock") * unit_price,
                output_field=DecimalField(max_digits=20, decimal_places=0),
            ),
        )
    )

    if not include_inactive:
        qs = qs.filter(is_active=True, product__is_active=True)
    if q:
        qs = qs.filter(
            Q(product__name__icontains=q) | Q(product__sku__icontains=q)
            | Q(sku__icontains=q) | Q(barcode__icontains=q) | Q(product__brand__icontains=q)
        )
    if category.isdigit():
        qs = qs.filter(product__category_id=int(category))
    if gender in Product.Gender.values:
        qs = qs.filter(product__gender=gender)
    if status == "out":
        qs = qs.filter(stock=0)
    elif status == "low":
        qs = qs.filter(stock__gt=0, stock__lte=F("min_stock"))
    elif status == "ok":
        qs = qs.filter(stock__gt=F("min_stock"))
    qs = qs.order_by("product__name", "color__name", "size__sort_order", "pk")

    if request.GET.get("export") == "csv":
        header = ["محصول", "کد مدل", "دسته‌بندی", "جنسیت", "رنگ", "سایز", "کد کالا", "بارکد",
                  "موجودی", "حداقل موجودی", "وضعیت", "قیمت واحد", "ارزش موجودی"]
        rows = (
            [
                v.product.name,
                v.product.sku,
                v.product.category.name if v.product.category else "",
                v.product.get_gender_display(),
                v.color.name,
                v.size.name,
                v.sku,
                v.barcode,
                v.stock,
                v.min_stock,
                _stock_status(v)[1],
                v.unit,
                v.value,
            ]
            for v in qs.iterator(chunk_size=2000)
        )
        return _csv_response(f"stock-{timezone.localdate():%Y%m%d}.csv", header, rows)

    # نام‌های مستعار نباید با فیلدها یا annotate های کوئری (stock, value, ...) هم‌نام باشند
    agg = qs.aggregate(
        n_variants=Count("pk"),
        sum_stock=Sum("stock"),
        sum_value=Sum("value"),
        n_low=Count("pk", filter=Q(stock__gt=0, stock__lte=F("min_stock"))),
        n_out=Count("pk", filter=Q(stock=0)),
    )
    summary = {
        "count": agg["n_variants"],
        "stock": agg["sum_stock"] or 0,
        "value": agg["sum_value"] or 0,
        "low": agg["n_low"],
        "out": agg["n_out"],
    }

    context = _paginate(request, qs, STOCK_PAGE_SIZE)
    page_obj = context["page_obj"]
    variants = list(page_obj.object_list)
    for v in variants:
        v.status_key, v.status_label = _stock_status(v)
    page_obj.object_list = variants

    context.update({
        "summary": summary,
        "categories": Category.objects.all(),
        "genders": Product.Gender.choices,
        "filters": {
            "q": q, "category": category, "gender": gender,
            "status": status, "inactive": include_inactive,
        },
        "has_filters": any([q, category, gender, status, include_inactive]),
    })
    return render(request, "report_stock.html", context)