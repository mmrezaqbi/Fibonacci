import csv
import datetime

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, DecimalField, ExpressionWrapper, F, IntegerField, Max, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from . import permissions
from .dates import parse_user_date, to_jalali_string, to_jalali_tuple
from .invoice_utils import invoice_search_q
from .xlsx import build_xlsx
from .models import ActivityLog, Category, Invoice, Product, ProductVariant, StockTransaction, StoreSettings, Warehouse
from .templatetags.jalali_tags import JMONTHS

TX_PAGE_SIZE = 25
INVOICE_PAGE_SIZE = 25
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


REPORT_TITLES = {
    "report_transactions": "گزارش تراکنش‌های ورود و خروج",
    "report_invoices": "گزارش فاکتورها",
    "report_stock": "گزارش موجودی انبار",
    "report_sales": "گزارش فروش",
    "report_assets": "گزارش دارایی انبار",
    "report_activity": "گزارش فعالیت کاربران",
}
XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PRINT_LIMIT = 5000   # حداکثر ردیف در نسخه‌ی چاپی


def _wants_export(request):
    return request.GET.get("export") in ("xlsx", "csv")


def _export_response(request, name, sheets):
    """
    خروجی Excel (xlsx) یا CSV از همان داده‌ی فیلترشده‌ی گزارش (بدون صفحه‌بندی).
    sheets: لیست (عنوان شیت، سرستون‌ها، ردیف‌ها)
    """
    stamp = f"{timezone.localdate():%Y%m%d}"
    sheets = [(t, h, [list(r) for r in rows]) for t, h, rows in sheets]
    if request.GET.get("export") == "csv":
        return _csv_response(f"{name}-{stamp}.csv", sheets[0][1], sheets[0][2])
    response = HttpResponse(build_xlsx(sheets), content_type=XLSX_TYPE)
    response["Content-Disposition"] = f'attachment; filename="{name}-{stamp}.xlsx"'
    return response


def _date_range(qs, date_from, date_to, field="created_at"):
    """
    فیلتر بازه‌ی تاریخ با بازه‌ی زمانی (نه created_at__date).
    __date در MySQL به جدول‌های منطقه‌ی زمانی نیاز دارد و بدون آن‌ها NULL می‌دهد (نتیجه خالی یا None).
    """
    tz = timezone.get_current_timezone()
    if date_from:
        qs = qs.filter(**{f"{field}__gte": timezone.make_aware(datetime.datetime.combine(date_from, datetime.time.min), tz)})
    if date_to:
        end = datetime.datetime.combine(date_to + datetime.timedelta(days=1), datetime.time.min)
        qs = qs.filter(**{f"{field}__lt": timezone.make_aware(end, tz)})
    return qs


def _paginate(request, queryset, size):
    paginator = Paginator(queryset, size)
    print_mode = request.GET.get("print") == "1"
    if print_mode:
        # نسخه‌ی چاپی: همه‌ی ردیف‌های فیلترشده در یک صفحه (تا سقف PRINT_LIMIT)
        paginator = Paginator(queryset, max(1, min(paginator.count, PRINT_LIMIT)))
    page_obj = paginator.get_page(1 if print_mode else request.GET.get("page"))
    params = request.GET.copy()
    for key in ("page", "export", "print"):
        params.pop(key, None)
    return {
        "print_mode": print_mode,
        "print_truncated": print_mode and paginator.count > PRINT_LIMIT,
        "print_store": StoreSettings.load().store_name,
        "print_time": _jalali_stamp(timezone.now()),
        "report_title": REPORT_TITLES.get(getattr(request.resolver_match, "url_name", ""), "گزارش"),
        "can_export": True,
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
            | Q(invoice__code__icontains=q)
            | Q(invoice__buyer_name__icontains=q)
            | Q(invoice__buyer_phone__icontains=q)
        )
    qs = _date_range(qs, date_from, date_to)
    if ttype in StockTransaction.Type.values:
        qs = qs.filter(type=ttype)
    if warehouse.isdigit():
        qs = qs.filter(warehouse_id=int(warehouse))
    qs = qs.order_by("-created_at", "-pk")

    if _wants_export(request):
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
        return _export_response(request, "transactions", [("تراکنش‌ها", header, rows)])

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

    if _wants_export(request):
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
        return _export_response(request, "stock", [("موجودی انبار", header, rows)])

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


# ---------------------------------------------------------------------------
# گزارش فاکتورها
# ---------------------------------------------------------------------------
_MONEY = DecimalField(max_digits=20, decimal_places=0)


@login_required
def report_invoices(request):
    """فهرست فاکتورهای ورود و خروج؛ جستجو بر اساس شماره فاکتور، موبایل یا نام خریدار."""
    q = request.GET.get("q", "").strip()
    raw_from = request.GET.get("date_from", "").strip()
    raw_to = request.GET.get("date_to", "").strip()
    date_from = parse_user_date(raw_from)
    date_to = parse_user_date(raw_to)
    date_error = bool((raw_from and not date_from) or (raw_to and not date_to))
    itype = request.GET.get("type", "").strip()
    warehouse = request.GET.get("warehouse", "").strip()

    base = Invoice.objects.all()
    if q:
        base = base.filter(invoice_search_q(q))
    base = _date_range(base, date_from, date_to)
    if itype in StockTransaction.Type.values:
        base = base.filter(type=itype)
    if warehouse.isdigit():
        base = base.filter(warehouse_id=int(warehouse))

    line_amount = ExpressionWrapper(
        F("transactions__quantity") * Coalesce("transactions__unit_price", Value(0), output_field=_MONEY),
        output_field=_MONEY,
    )
    qs = (
        base.select_related("warehouse", "created_by")
        .annotate(
            n_lines=Count("transactions"),
            qty_sum=Coalesce(Sum("transactions__quantity"), Value(0), output_field=IntegerField()),
            amount=Coalesce(Sum(line_amount), Value(0), output_field=_MONEY),
        )
        .order_by("-created_at", "-pk")
    )

    if _wants_export(request):
        header = ["شماره فاکتور", "تاریخ", "نوع", "نام خریدار", "موبایل خریدار", "انبار",
                  "تعداد قلم", "تعداد کالا", "مبلغ (تومان)", "ثبت‌کننده", "توضیحات"]
        rows = (
            [i.code, _jalali_stamp(i.created_at), i.get_type_display(), i.buyer_name, i.buyer_phone,
             i.warehouse.name, i.n_lines, i.qty_sum,
             int(i.amount) if i.type == StockTransaction.Type.OUT else "",
             _user_name(i.created_by), i.note]
            for i in qs.iterator(chunk_size=2000)
        )
        return _export_response(request, "invoices", [("فاکتورها", header, rows)])

    counts = base.aggregate(
        count=Count("pk"),
        n_out=Count("pk", filter=Q(type=StockTransaction.Type.OUT)),
        n_in=Count("pk", filter=Q(type=StockTransaction.Type.IN)),
    )
    out_amount = StockTransaction.objects.filter(
        invoice__in=base.values("pk"), type=StockTransaction.Type.OUT,
    ).aggregate(
        total=Sum(ExpressionWrapper(
            F("quantity") * Coalesce("unit_price", Value(0), output_field=_MONEY), output_field=_MONEY,
        ))
    )["total"] or 0
    summary = {
        "count": counts["count"], "out": counts["n_out"], "in": counts["n_in"], "out_amount": out_amount,
    }

    context = _paginate(request, qs, INVOICE_PAGE_SIZE)
    context.update({
        "summary": summary,
        "warehouses": Warehouse.objects.all(),
        "filters": {
            "q": q,
            "date_from": to_jalali_string(date_from) if date_from else raw_from,
            "date_to": to_jalali_string(date_to) if date_to else raw_to,
            "type": itype,
            "warehouse": warehouse,
        },
        "date_error": date_error,
        "has_filters": any([q, raw_from, raw_to, itype, warehouse]),
    })
    return render(request, "report_invoices.html", context)



# ---------------------------------------------------------------------------
# گزارش فروش
# ---------------------------------------------------------------------------
SALES_PAGE_SIZE = 31


def _pct(value, top):
    return int(round(value * 100 / top)) if top else 0


@login_required
def report_sales(request):
    """
    میزان فروش = مجموع خروج‌های انبار × قیمت واحد ثبت‌شده در فاکتور.
    خروج‌هایی که قیمت ندارند (مثل سفارش‌های همگام‌شده از سایت) در تعداد حساب می‌شوند ولی مبلغشان صفر است.
    """
    raw_from = request.GET.get("date_from", "").strip()
    raw_to = request.GET.get("date_to", "").strip()
    date_from = parse_user_date(raw_from)
    date_to = parse_user_date(raw_to)
    date_error = bool((raw_from and not date_from) or (raw_to and not date_to))
    group = request.GET.get("group", "day")
    if group not in ("day", "month", "product"):
        group = "day"

    qs = StockTransaction.objects.filter(type=StockTransaction.Type.OUT)
    qs = _date_range(qs, date_from, date_to)

    amount_expr = ExpressionWrapper(
        F("quantity") * Coalesce("unit_price", Value(0), output_field=_MONEY), output_field=_MONEY,
    )
    agg = {
        "qty": Coalesce(Sum("quantity"), Value(0), output_field=IntegerField()),
        "amount": Coalesce(Sum(amount_expr), Value(0), output_field=_MONEY),
        "invoices": Count("invoice", distinct=True),
    }
    totals = qs.aggregate(**agg)
    summary = dict(totals)
    summary["average"] = (totals["amount"] // totals["invoices"]) if totals["invoices"] else 0

    rows = []
    if group == "product":
        for r in (
            qs.values("variant__product_id", "variant__product__name", "variant__product__sku")
            .annotate(**agg).order_by("-amount", "variant__product__name")
        ):
            rows.append({"label": r["variant__product__name"], "sub": r["variant__product__sku"],
                         "qty": r["qty"], "amount": r["amount"], "invoices": r["invoices"]})
    else:
        # گروه‌بندی روز در پایتون و با منطقه‌ی زمانی برنامه (بدون وابستگی به جدول‌های timezone دیتابیس)
        days = {}
        seen = {}
        for created, qty, price, inv_id in qs.values_list("created_at", "quantity", "unit_price", "invoice_id"):
            day = timezone.localtime(created).date()
            row = days.setdefault(day, {"qty": 0, "amount": 0, "invoices": 0})
            row["qty"] += qty
            row["amount"] += qty * (price or 0)
            if inv_id is not None and (day, inv_id) not in seen:
                seen[(day, inv_id)] = True
                row["invoices"] += 1
        ordered = sorted(days.items(), reverse=True)
        if group == "day":
            for day, r in ordered:
                rows.append({"label": to_jalali_string(day), "sub": "",
                             "qty": r["qty"], "amount": r["amount"], "invoices": r["invoices"]})
        else:  # ماه شمسی
            months = {}
            for day, r in ordered:
                y, m, _d = to_jalali_tuple(day)
                row = months.setdefault((y, m), {"label": f"{JMONTHS[m - 1]} {y}", "sub": "",
                                                 "qty": 0, "amount": 0, "invoices": 0})
                row["qty"] += r["qty"]
                row["amount"] += r["amount"]
                row["invoices"] += r["invoices"]
            rows = [months[k] for k in sorted(months, reverse=True)]

    top = max((r["amount"] for r in rows), default=0)
    for r in rows:
        r["pct"] = _pct(r["amount"], top)

    if _wants_export(request):
        first = {"day": "تاریخ", "month": "ماه", "product": "کالا"}[group]
        header = [first] + (["کد مدل"] if group == "product" else []) + ["تعداد فاکتور", "تعداد کالا", "مبلغ فروش (تومان)"]
        out = [
            [r["label"]] + ([r["sub"]] if group == "product" else []) + [r["invoices"], r["qty"], int(r["amount"])]
            for r in rows
        ]
        out.append(["جمع کل"] + ([""] if group == "product" else [])
                   + [summary["invoices"], summary["qty"], int(summary["amount"])])
        return _export_response(request, "sales", [("فروش", header, out)])

    context = _paginate(request, rows, SALES_PAGE_SIZE)
    context.update({
        "summary": summary,
        "group": group,
        "filters": {
            "date_from": to_jalali_string(date_from) if date_from else raw_from,
            "date_to": to_jalali_string(date_to) if date_to else raw_to,
        },
        "date_error": date_error,
        "has_filters": any([raw_from, raw_to, group != "day"]),
    })
    return render(request, "report_sales.html", context)


# ---------------------------------------------------------------------------
# گزارش دارایی (ارزش موجودی انبار بر اساس قیمت پایه‌ی کالا)
# ---------------------------------------------------------------------------
ASSET_PAGE_SIZE = 30


@login_required
def report_assets(request):
    """ارزش دارایی هر کالا = جمع موجودی همه‌ی رنگ و سایزها × «قیمت پایه»ی همان کالا (قیمت اختصاصی تنوع‌ها نادیده گرفته می‌شود)."""
    q = request.GET.get("q", "").strip()
    category = request.GET.get("category", "").strip()
    include_inactive = request.GET.get("inactive") == "1"

    qs = ProductVariant.objects.all()
    if not include_inactive:
        qs = qs.filter(is_active=True, product__is_active=True)
    if q:
        qs = qs.filter(
            Q(product__name__icontains=q) | Q(product__sku__icontains=q) | Q(product__brand__icontains=q)
        )
    if category.isdigit():
        qs = qs.filter(product__category_id=int(category))

    products = []
    for r in (
        qs.values("product_id", "product__name", "product__sku", "product__price", "product__category__name")
        .annotate(stock_sum=Coalesce(Sum("stock"), Value(0), output_field=IntegerField()))
        .order_by()
    ):
        price = r["product__price"] or 0
        products.append({
            "id": r["product_id"], "name": r["product__name"], "sku": r["product__sku"],
            "category": r["product__category__name"] or "بدون دسته‌بندی",
            "price": price, "stock": r["stock_sum"], "value": r["stock_sum"] * price,
        })
    products.sort(key=lambda p: (-p["value"], p["name"]))

    by_category = {}
    for p in products:
        row = by_category.setdefault(p["category"], {"name": p["category"], "products": 0, "stock": 0, "value": 0})
        row["products"] += 1
        row["stock"] += p["stock"]
        row["value"] += p["value"]
    categories_rows = sorted(by_category.values(), key=lambda c: (-c["value"], c["name"]))

    total_value = sum(p["value"] for p in products)
    total_stock = sum(p["stock"] for p in products)
    for c in categories_rows:
        c["pct"] = _pct(c["value"], total_value)
    for p in products:
        p["pct"] = _pct(p["value"], total_value)

    summary = {
        "products": len(products),
        "stock": total_stock,
        "value": total_value,
        "no_price": sum(1 for p in products if p["price"] == 0 and p["stock"] > 0),
    }

    if _wants_export(request):
        prod_rows = [[p["name"], p["sku"], p["category"], int(p["price"]), p["stock"], int(p["value"])] for p in products]
        prod_rows.append(["جمع کل", "", "", "", total_stock, int(total_value)])
        cat_rows = [[c["name"], c["products"], c["stock"], int(c["value"])] for c in categories_rows]
        cat_rows.append(["جمع کل", len(products), total_stock, int(total_value)])
        return _export_response(request, "assets", [
            ("دارایی کالاها", ["کالا", "کد مدل", "دسته‌بندی", "قیمت پایه (تومان)", "موجودی", "ارزش (تومان)"], prod_rows),
            ("دارایی دسته‌بندی‌ها", ["دسته‌بندی", "تعداد کالا", "موجودی", "ارزش (تومان)"], cat_rows),
        ])

    context = _paginate(request, products, ASSET_PAGE_SIZE)
    context.update({
        "summary": summary,
        "category_rows": categories_rows,
        "categories": Category.objects.all(),
        "filters": {"q": q, "category": category, "inactive": include_inactive},
        "has_filters": any([q, category, include_inactive]),
    })
    return render(request, "report_assets.html", context)


# ---------------------------------------------------------------------------
# گزارش فعالیت کاربران (فقط مدیر)
# ---------------------------------------------------------------------------
ACTIVITY_PAGE_SIZE = 40


@permissions.role_required(permissions.ADMIN)
def report_activity(request):
    q = request.GET.get("q", "").strip()
    user_id = request.GET.get("user", "").strip()
    action = request.GET.get("action", "").strip()
    raw_from = request.GET.get("date_from", "").strip()
    raw_to = request.GET.get("date_to", "").strip()
    date_from = parse_user_date(raw_from)
    date_to = parse_user_date(raw_to)
    date_error = bool((raw_from and not date_from) or (raw_to and not date_to))

    qs = ActivityLog.objects.select_related("user")
    if q:
        qs = qs.filter(Q(detail__icontains=q) | Q(username__icontains=q))
    if user_id.isdigit():
        qs = qs.filter(user_id=int(user_id))
    if action in ActivityLog.Action.values:
        qs = qs.filter(action=action)
    qs = _date_range(qs, date_from, date_to)
    qs = qs.order_by("-created_at", "-pk")

    if _wants_export(request):
        header = ["زمان", "کاربر", "فعالیت", "توضیح", "آدرس IP"]
        rows = (
            [_jalali_stamp(a.created_at), a.username, a.get_action_display(), a.detail, a.ip_address or ""]
            for a in qs.iterator(chunk_size=2000)
        )
        return _export_response(request, "activity", [("فعالیت کاربران", header, rows)])

    agg = qs.aggregate(count=Count("pk"), users=Count("username", distinct=True), last=Max("created_at"))

    context = _paginate(request, qs, ACTIVITY_PAGE_SIZE)
    context.update({
        "summary": agg,
        "users": get_user_model().objects.filter(activity_logs__isnull=False).distinct().order_by("username"),
        "actions": ActivityLog.Action.choices,
        "filters": {
            "q": q, "user": user_id, "action": action,
            "date_from": to_jalali_string(date_from) if date_from else raw_from,
            "date_to": to_jalali_string(date_to) if date_to else raw_to,
        },
        "date_error": date_error,
        "has_filters": any([q, user_id, action, raw_from, raw_to]),
    })
    return render(request, "report_activity.html", context)
