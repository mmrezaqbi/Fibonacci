"""
فاکتور ورود / خروج چندقلمی با جستجوی AJAX و پشتیبانی از بارکدخوان.

ویوها:
  invoice_page     -> نمایش صفحه‌ی فاکتور (movement = "in" یا "out")
  variant_search   -> API تطابق دقیق بارکد / کد کالا (مخصوص بارکدخوان) و جستجوی ترکیب‌ها
  product_search   -> API جستجوی «محصول» (نه ترکیب) برای کادر جستجوی فاکتور
  product_variants -> API ترکیب‌های رنگ/سایز یک محصول (برای پاپ‌آپ انتخاب)
  invoice_submit   -> ثبت همه‌ی اقلام در یک تراکنش دیتابیس (یا همه ثبت می‌شوند، یا هیچ‌کدام)

هر قلم فاکتور یک StockTransaction جدا می‌سازد و از همان save() مدل استفاده می‌کند؛
پس منطق به‌روزرسانی موجودی همان قبلی است. برای اینکه اقلام یک فاکتور در گزارش‌ها
قابل پیگیری باشند، یک «شماره‌ی سند» در ابتدای توضیحات (note) هر تراکنش نوشته می‌شود.
قیمت واحد هر قلم (در فاکتور خروج) در StockTransaction.unit_price ذخیره می‌شود.
"""
import json
import uuid

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Case, Count, IntegerField, Q, Sum, Value, When
from django.db.models.functions import Coalesce
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .models import Product, ProductVariant, StockTransaction, Warehouse
from .reports import _jalali_stamp

MAX_LINES = 200
MAX_QTY = 100000
MAX_PRICE = 10 ** 12
SEARCH_LIMIT = 20
PRODUCT_SEARCH_LIMIT = 20

SEARCH_FIELDS = (
    "barcode", "sku", "product__name", "product__sku",
    "product__brand", "color__name", "size__name",
)

# ارقام فارسی و عربی -> انگلیسی (برای بارکد/کدی که با کیبورد فارسی تایپ شده)
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def _normalize(text):
    return str(text or "").translate(_DIGITS).strip()


def _variant_json(v):
    return {
        "id": v.pk,
        "product": v.product.name,
        "model_sku": v.product.sku,
        "color_id": v.color_id,
        "color": v.color.name,
        "hex": v.color.hex_code,
        "size_id": v.size_id,
        "size": v.size.name,
        "size_order": v.size.sort_order,
        "sku": v.sku,
        "barcode": v.barcode or "",
        "stock": v.stock,
        "min_stock": v.min_stock,
        "price": int(v.unit_price or 0),
    }


# ---------------------------------------------------------------------------
# صفحه
# ---------------------------------------------------------------------------
@login_required
def invoice_page(request, movement):
    warehouses = list(Warehouse.objects.filter(is_active=True))
    return render(request, "stock_invoice.html", {
        "movement": movement,
        "is_out": movement == "out",
        "warehouses": warehouses,
        "default_warehouse": warehouses[0].pk if len(warehouses) == 1 else "",
    })


# ---------------------------------------------------------------------------
# جستجوی AJAX
# ---------------------------------------------------------------------------
@login_required
@require_GET
def variant_search(request):
    """
    ?q=...          جستجوی معمولی (هر کلمه باید در یکی از فیلدها باشد)
    ?q=...&exact=1  تطابق دقیق بارکد یا کد کالا (مخصوص بارکدخوان)
    """
    q = _normalize(request.GET.get("q", ""))
    exact = request.GET.get("exact") == "1"
    if not q or (not exact and len(q) < 2):
        return JsonResponse({"results": []})

    qs = (
        ProductVariant.objects
        .select_related("product", "color", "size")
        .filter(is_active=True, product__is_active=True)
    )

    exact_cond = Q(barcode__iexact=q) | Q(sku__iexact=q)
    if exact:
        qs = qs.filter(exact_cond)
    else:
        for token in q.split()[:5]:
            cond = Q()
            for field in SEARCH_FIELDS:
                cond |= Q(**{f"{field}__icontains": token})
            qs = qs.filter(cond)

    qs = qs.annotate(
        rank=Case(When(exact_cond, then=0), default=1, output_field=IntegerField())
    ).order_by("rank", "product__name", "color__name", "size__sort_order", "pk")[:SEARCH_LIMIT]

    return JsonResponse({"results": [_variant_json(v) for v in qs]})


@login_required
@require_GET
def product_search(request):
    """
    جستجوی محصول (فقط خود محصول اصلی، بدون نمایش ترکیب‌ها).
    هر کلمه می‌تواند در نام، کد مدل، برند محصول یا در کد/بارکد/رنگ/سایز یکی از ترکیب‌های فعال‌اش باشد.
    """
    q = _normalize(request.GET.get("q", ""))
    if len(q) < 2:
        return JsonResponse({"results": []})

    active_variants = ProductVariant.objects.filter(is_active=True)
    qs = Product.objects.filter(is_active=True)
    for token in q.split()[:5]:
        qs = qs.filter(
            Q(name__icontains=token) | Q(sku__icontains=token) | Q(brand__icontains=token)
            | Q(pk__in=active_variants.filter(
                Q(sku__icontains=token) | Q(barcode__icontains=token)
                | Q(color__name__icontains=token) | Q(size__name__icontains=token)
            ).values("product_id"))
        )

    qs = (
        qs.annotate(
            stock_sum=Coalesce(
                Sum("variants__stock", filter=Q(variants__is_active=True)),
                Value(0), output_field=IntegerField(),
            ),
            variants_n=Count("variants", filter=Q(variants__is_active=True)),
        )
        .filter(variants_n__gt=0)
        .order_by("name", "pk")[:PRODUCT_SEARCH_LIMIT]
    )

    return JsonResponse({"results": [
        {
            "id": p.pk, "name": p.name, "sku": p.sku, "brand": p.brand,
            "stock": p.stock_sum, "variants": p.variants_n,
        }
        for p in qs
    ]})


@login_required
@require_GET
def product_variants(request, pk):
    """همه‌ی ترکیب‌های فعال یک محصول (برای ساخت جدول رنگ × سایز در پاپ‌آپ)."""
    product = get_object_or_404(Product, pk=pk, is_active=True)
    variants = (
        product.variants.filter(is_active=True)
        .select_related("product", "color", "size")
        .order_by("color__name", "size__sort_order", "size__name")
    )
    return JsonResponse({
        "product": {"id": product.pk, "name": product.name, "sku": product.sku, "brand": product.brand},
        "variants": [_variant_json(v) for v in variants],
    })


# ---------------------------------------------------------------------------
# ثبت فاکتور
# ---------------------------------------------------------------------------
class _InvoiceError(Exception):
    def __init__(self, errors):
        super().__init__("invoice rejected")
        self.errors = errors


def _fail(message, status=400, errors=None):
    return JsonResponse({"ok": False, "message": message, "errors": errors or []}, status=status)


def _fit_note(text):
    limit = StockTransaction._meta.get_field("note").max_length
    return text[:limit] if limit else text


@login_required
@require_POST
def invoice_submit(request):
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return _fail("درخواست نامعتبر است.")
    if not isinstance(payload, dict):
        return _fail("درخواست نامعتبر است.")

    movement = payload.get("type")
    if movement not in ("in", "out"):
        return _fail("نوع فاکتور نامعتبر است.")
    kind = StockTransaction.Type.IN if movement == "in" else StockTransaction.Type.OUT

    try:
        warehouse = Warehouse.objects.get(pk=int(payload.get("warehouse")), is_active=True)
    except (TypeError, ValueError, Warehouse.DoesNotExist):
        return _fail("انبار را انتخاب کنید.")

    raw_items = payload.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        return _fail("فاکتور خالی است.")
    if len(raw_items) > MAX_LINES:
        return _fail(f"حداکثر {MAX_LINES} قلم در هر فاکتور مجاز است.")

    # ادغام ردیف‌های تکراریِ یک کالا (تعدادها جمع می‌شوند؛ قیمت آخرین ردیف می‌ماند)
    wanted, prices = {}, {}
    for item in raw_items:
        try:
            vid = int(item.get("variant"))
            qty = int(item.get("quantity"))
        except (AttributeError, TypeError, ValueError):
            return _fail("اطلاعات یکی از اقلام نامعتبر است.")
        if qty < 1 or qty > MAX_QTY:
            return _fail("تعداد هر قلم باید عددی مثبت (حداکثر %d) باشد." % MAX_QTY)

        raw_price = item.get("price")
        try:
            price = None if raw_price in (None, "") else int(raw_price)
        except (TypeError, ValueError):
            return _fail("قیمت یکی از اقلام نامعتبر است.")
        if price is not None and not (0 <= price <= MAX_PRICE):
            return _fail("قیمت هر قلم باید بین ۰ و %d باشد." % MAX_PRICE)

        wanted[vid] = wanted.get(vid, 0) + qty
        if price is not None:
            prices[vid] = price

    code = f"F{timezone.localtime():%y%m%d}-{uuid.uuid4().hex[:5].upper()}"
    label = "فاکتور خروج" if movement == "out" else "فاکتور ورود"
    user_note = str(payload.get("note") or "").strip()
    note = _fit_note(f"{label} {code}" + (f" — {user_note}" if user_note else ""))

    ids = sorted(wanted)
    done = []
    try:
        with transaction.atomic():
            # قفل ردیف‌ها به ترتیب شناسه (جلوگیری از deadlock بین دو فاکتور هم‌زمان)
            locked = {
                v.pk: v for v in
                ProductVariant.objects.select_for_update().filter(pk__in=ids).order_by("pk")
            }

            errors = []
            for vid in ids:
                v = locked.get(vid)
                if v is None or not v.is_active:
                    errors.append({"variant": vid, "message": "این کالا پیدا نشد یا غیرفعال است."})
                elif kind == StockTransaction.Type.OUT and v.stock < wanted[vid]:
                    errors.append({
                        "variant": vid, "stock": v.stock,
                        "message": f"موجودی کافی نیست (موجودی فعلی: {v.stock}).",
                    })
            if errors:
                raise _InvoiceError(errors)

            for vid in ids:
                v = locked[vid]
                StockTransaction(
                    variant=v, warehouse=warehouse, type=kind,
                    quantity=wanted[vid], unit_price=prices.get(vid),
                    note=note, created_by=request.user,
                ).save()
                v.refresh_from_db(fields=["stock"])
                done.append({
                    "variant": vid, "quantity": wanted[vid],
                    "price": prices.get(vid), "stock": v.stock,
                })
    except _InvoiceError as exc:
        return _fail("فاکتور ثبت نشد؛ اقلام مشخص‌شده را اصلاح کنید.", status=409, errors=exc.errors)
    except ValidationError as exc:
        return _fail(" ".join(exc.messages) or "ثبت فاکتور انجام نشد.", status=409)

    return JsonResponse({
        "ok": True,
        "code": code,
        "type": movement,
        "lines": len(done),
        "quantity": sum(d["quantity"] for d in done),
        "total": sum(d["quantity"] * (d["price"] or 0) for d in done),
        "warehouse": warehouse.name,
        "date": _jalali_stamp(timezone.now()),
        "items": done,
    })
