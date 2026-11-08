"""همگام‌سازی موجودی انبار با ووکامرس.

انبار ← سایت : بعد از هر ورود/خروج، موجودی همان رنگ/سایز (به‌صورت عدد کل، نه تفاضل) به متغیر مربوطه در ووکامرس ارسال می‌شود.
سایت ← انبار : سفارش‌های سایت (وب‌هوک یا دریافت دستی/زمان‌بندی‌شده) به‌صورت «خروج» در انبار ثبت می‌شود.
"""
import threading
from datetime import timedelta, timezone as dt_timezone

from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from . import woo_client
from .models import (
    ProductVariant, StockTransaction, Warehouse,
    WooLog, WooOrder, WooProductLink, WooSettings, WooVariantLink,
)

ATTR_COLOR, ATTR_SIZE = "رنگ", "سایز"
DEDUCT_STATUSES = {"processing", "on-hold", "completed"}  # وضعیت‌هایی که ووکامرس خودش موجودی را کم می‌کند
RESTORE_STATUSES = {"cancelled", "refunded", "failed"}
CHUNK = 50

_lock = threading.RLock()  # جلوگیری از ساخت دوباره‌ی یک محصول توسط چند ارسال هم‌زمان


# ---------------------------------------------------------------------------
# ابزارها
# ---------------------------------------------------------------------------
def log(ok, message):
    WooLog.objects.create(ok=ok, message=str(message)[:500])
    old = list(WooLog.objects.values_list("id", flat=True)[200:])
    if old:
        WooLog.objects.filter(id__in=old).delete()


def get_client(settings=None):
    settings = settings or WooSettings.load()
    if not settings.configured:
        raise woo_client.WooError("اتصال به ووکامرس هنوز تنظیم نشده است.")
    return woo_client.WooClient(settings.site_url, settings.consumer_key, settings.consumer_secret)


def _chunks(items, n=CHUNK):
    for i in range(0, len(items), n):
        yield items[i:i + n]


def _unique(seq):
    seen, out = set(), []
    for x in seq:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _attributes(product):
    variants = list(product.variants.select_related("color", "size").order_by("size__sort_order", "color__name"))
    return [
        {"name": ATTR_COLOR, "visible": True, "variation": True,
         "options": _unique(v.color.name for v in variants)},
        {"name": ATTR_SIZE, "visible": True, "variation": True,
         "options": _unique(v.size.name for v in variants)},
    ]


def _variation_payload(variant):
    price = variant.unit_price
    return {
        "sku": variant.sku,
        "regular_price": str(int(price)) if price else "",
        "manage_stock": True,
        "stock_quantity": variant.stock,
        "status": "publish" if variant.is_active else "private",
        "attributes": [
            {"name": ATTR_COLOR, "option": variant.color.name},
            {"name": ATTR_SIZE, "option": variant.size.name},
        ],
    }


def _merge_attributes(client, woo_id, product):
    """گزینه‌های رنگ/سایز جدید را به ویژگی‌های محصولِ موجود در سایت اضافه می‌کند (چیزی حذف نمی‌شود)."""
    current = client.get(f"products/{woo_id}").get("attributes", [])
    wanted = {a["name"]: a for a in _attributes(product)}
    result = []
    for attr in current:
        extra = wanted.pop(attr.get("name"), None)
        if extra:
            attr["options"] = _unique(list(attr.get("options", [])) + extra["options"])
            attr["variation"] = True
        result.append(attr)
    result.extend(wanted.values())
    client.put(f"products/{woo_id}", {"attributes": result})


# ---------------------------------------------------------------------------
# انبار ← سایت
# ---------------------------------------------------------------------------
def ensure_product(client, product):
    """محصول و همه‌ی تنوع‌های بدون پیوندش را در ووکامرس می‌سازد (یا به مورد هم‌SKU وصل می‌کند).
    تعداد تنوع‌های جدیدِ ساخته/وصل‌شده را برمی‌گرداند."""
    link = WooProductLink.objects.filter(product=product).first()
    just_created = False
    if link is None:
        woo_id = None
        if product.sku:
            found = client.get("products", {"sku": product.sku})
            if found:
                woo_id = found[0]["id"]
        if woo_id is None:
            data = client.post("products", {
                "name": product.name,
                "type": "variable",
                "sku": product.sku,
                "status": "draft",  # پیش‌نویس؛ بعد از بررسی (تصویر، دسته‌بندی) از ووکامرس منتشر کنید
                "description": product.description or "",
                "attributes": _attributes(product),
            })
            woo_id, just_created = data["id"], True
        link = WooProductLink.objects.create(product=product, woo_id=woo_id)

    missing = list(product.variants.filter(woo_link__isnull=True).select_related("color", "size"))
    if not missing:
        return 0
    if not just_created:
        _merge_attributes(client, link.woo_id, product)

    existing = {}
    if not just_created:
        page = 1
        while True:
            rows = client.get(f"products/{link.woo_id}/variations", {"per_page": 100, "page": page})
            existing.update({r["sku"]: r["id"] for r in rows if r.get("sku")})
            if len(rows) < 100:
                break
            page += 1

    to_create, count = [], 0
    for v in missing:
        if v.sku in existing:
            WooVariantLink.objects.create(variant=v, woo_id=existing[v.sku])
            count += 1
        else:
            to_create.append(v)
    for chunk in _chunks(to_create):
        res = client.post(f"products/{link.woo_id}/variations/batch",
                          {"create": [_variation_payload(v) for v in chunk]})
        for v, item in zip(chunk, res.get("create", [])):
            if item.get("id") and not item.get("error"):
                WooVariantLink.objects.create(variant=v, woo_id=item["id"])
                count += 1
            else:
                msg = (item.get("error") or {}).get("message", "نامشخص")
                log(False, f"ساخت تنوع {v.sku} در ووکامرس ناموفق بود: {msg}")
    return count


def push_stock(client, variant_ids):
    """موجودی فعلی کالاهای داده‌شده را به‌صورت عدد کل در ووکامرس می‌نویسد."""
    links = (WooVariantLink.objects.filter(variant_id__in=variant_ids)
             .select_related("variant", "variant__product__woo_link"))
    by_product = {}
    for vl in links:
        by_product.setdefault(vl.variant.product.woo_link.woo_id, []).append(vl)
    sent = 0
    for woo_pid, vls in by_product.items():
        for chunk in _chunks(vls):
            res = client.post(f"products/{woo_pid}/variations/batch", {"update": [
                {"id": vl.woo_id, "manage_stock": True, "stock_quantity": vl.variant.stock} for vl in chunk
            ]})
            for vl, item in zip(chunk, res.get("update", [])):
                if (item.get("error") or {}).get("message"):
                    log(False, f"به‌روزرسانی موجودی {vl.variant.sku} ناموفق بود: {item['error']['message']}")
                else:
                    sent += 1
    return sent


def _worker(variant_id):
    try:
        with _lock:
            client = get_client()
            variant = ProductVariant.objects.select_related("product").get(pk=variant_id)
            ensure_product(client, variant.product)
            push_stock(client, [variant_id])
    except Exception as exc:  # noqa: BLE001 — خطای سایت نباید ثبت ورود/خروج را خراب کند
        try:
            log(False, f"ارسال موجودی به سایت ناموفق بود: {exc}")
        except Exception:  # noqa: BLE001
            pass
    finally:
        connection.close()


def schedule_push(variant_id):
    settings = WooSettings.load()
    if not (settings.enabled and settings.configured):
        return
    transaction.on_commit(lambda: threading.Thread(target=_worker, args=(variant_id,), daemon=True).start())


def sync_all():
    """همه‌ی محصولات فعال را می‌سازد/وصل می‌کند و موجودی همه‌ی کالاها را می‌فرستد."""
    from .models import Product
    client = get_client()
    result = {"products": 0, "variants_linked": 0, "stock_sent": 0, "errors": 0}
    with _lock:
        for product in Product.objects.filter(is_active=True, variants__isnull=False).distinct():
            try:
                result["variants_linked"] += ensure_product(client, product)
                result["stock_sent"] += push_stock(client, list(product.variants.values_list("pk", flat=True)))
                result["products"] += 1
            except woo_client.WooError as exc:
                result["errors"] += 1
                log(False, f"محصول «{product.name}»: {exc}")
    log(result["errors"] == 0,
        f"همگام‌سازی کامل: {result['products']} محصول، {result['variants_linked']} تنوع جدید، "
        f"موجودی {result['stock_sent']} کالا ارسال شد، {result['errors']} خطا.")
    return result


# ---------------------------------------------------------------------------
# سایت ← انبار
# ---------------------------------------------------------------------------
def _match_variant(line):
    vid = line.get("variation_id") or 0
    if vid:
        vl = WooVariantLink.objects.filter(woo_id=vid).select_related("variant").first()
        if vl:
            return vl.variant
    sku = line.get("sku")
    return ProductVariant.objects.filter(sku=sku).first() if sku else None


def _order_created_at(order):
    raw = order.get("date_created_gmt") or order.get("date_created")
    dt = parse_datetime(raw) if raw else None
    if dt and timezone.is_naive(dt):
        dt = dt.replace(tzinfo=dt_timezone.utc)
    return dt


def _move(variant, warehouse, kind, qty, order_id):
    tx = StockTransaction(variant=variant, warehouse=warehouse, type=kind, quantity=qty,
                          note=f"سفارش سایت #{order_id}")
    tx._skip_woo = True  # موجودی سایت خودش درست شده؛ دوباره نفرستیم
    tx.save()


def apply_order(order, settings=None):
    """یک سفارش ووکامرس را در انبار اعمال می‌کند (idempotent). یکی از «deducted / restored / unchanged / skipped» را برمی‌گرداند."""
    settings = settings or WooSettings.load()
    order_id, status = int(order["id"]), order.get("status", "")

    created = _order_created_at(order)
    if settings.sync_started_at and created and created < settings.sync_started_at:
        return "skipped"  # سفارش قدیمی‌تر از زمان فعال‌سازی؛ موجودی‌اش قبلاً در انبار لحاظ شده

    warehouse = settings.default_warehouse or Warehouse.objects.filter(is_active=True).first()
    if warehouse is None:
        log(False, f"سفارش #{order_id}: انباری برای ثبت خروج تعیین نشده است.")
        return "skipped"

    with transaction.atomic():
        wo, _ = WooOrder.objects.select_for_update().get_or_create(order_id=order_id)
        wo.status = status
        notes = []
        outcome = "unchanged"

        if status in DEDUCT_STATUSES and not wo.deducted:
            lines = []
            for line in order.get("line_items", []):
                variant = _match_variant(line)
                qty = int(line.get("quantity") or 0)
                if variant is None:
                    notes.append(f"کالای «{line.get('sku') or line.get('name')}» در انبار پیدا نشد")
                    continue
                if qty <= 0:
                    continue
                available = ProductVariant.objects.get(pk=variant.pk).stock
                take = min(qty, available)
                if take < qty:
                    notes.append(f"{variant.sku}: {qty} سفارش، فقط {available} موجود بود")
                if take > 0:
                    try:
                        _move(variant, warehouse, StockTransaction.Type.OUT, take, order_id)
                        lines.append({"variant": variant.pk, "qty": take})
                    except ValidationError as exc:
                        notes.append(f"{variant.sku}: {'; '.join(exc.messages)}")
            wo.lines, wo.deducted, outcome = lines, True, "deducted"

        elif status in RESTORE_STATUSES and wo.deducted:
            for line in wo.lines:
                variant = ProductVariant.objects.filter(pk=line["variant"]).first()
                if variant:
                    _move(variant, warehouse, StockTransaction.Type.IN, line["qty"], order_id)
            wo.deducted, outcome = False, "restored"

        wo.note = "؛ ".join(notes)[:500]
        wo.save()

    if notes:
        log(False, f"سفارش #{order_id}: " + "؛ ".join(notes))
    elif outcome != "unchanged":
        log(True, f"سفارش #{order_id} ({status}): " + ("خروج از انبار ثبت شد" if outcome == "deducted" else "موجودی برگشت داده شد"))
    return outcome


def pull_orders():
    """سفارش‌های تغییریافته‌ی سایت از آخرین دریافت تا الان را می‌گیرد و اعمال می‌کند (برای وقتی که وب‌هوک در دسترس نیست)."""
    settings = WooSettings.load()
    client = get_client(settings)
    started = timezone.now()
    if settings.last_order_pull is None:
        settings.sync_started_at = settings.sync_started_at or started
        settings.last_order_pull = started
        settings.save(update_fields=["sync_started_at", "last_order_pull"])
        return {"first": True, "orders": 0, "deducted": 0, "restored": 0}

    since = settings.last_order_pull.astimezone(dt_timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    result = {"first": False, "orders": 0, "deducted": 0, "restored": 0}
    page = 1
    while True:
        rows = client.get("orders", {
            "per_page": 100, "page": page, "orderby": "modified", "order": "asc",
            "modified_after": since, "dates_are_gmt": "true", "status": "any",
        })
        for order in rows:
            outcome = apply_order(order, settings)
            result["orders"] += 1
            if outcome in ("deducted", "restored"):
                result[outcome] += 1
        if len(rows) < 100:
            break
        page += 1
    settings.last_order_pull = started - timedelta(minutes=2)  # کمی هم‌پوشانی؛ اعمال سفارش تکراری بی‌اثر است
    settings.save(update_fields=["last_order_pull"])
    return result
