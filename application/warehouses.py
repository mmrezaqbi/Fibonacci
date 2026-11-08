"""نمایش انبارها.

موجودی ProductVariant.stock سراسری است (نه به تفکیک انبار)؛ بنابراین موجودی هر انبار
از روی تراکنش‌ها محاسبه می‌شود: مجموع ورودها منهای مجموع خروج‌های همان انبار.
"""
from collections import defaultdict

from django.contrib.auth.decorators import login_required
from django.db.models import Count, F, Max, Q, Sum
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, render

from .models import ProductVariant, StockTransaction, Warehouse
from .reports import _paginate

IN, OUT = StockTransaction.Type.IN, StockTransaction.Type.OUT
DETAIL_PAGE_SIZE = 20


@login_required
def warehouse_list(request):
    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")

    warehouses = Warehouse.objects.annotate(
        tx_n=Count("transactions"),
        sum_in=Coalesce(Sum("transactions__quantity", filter=Q(transactions__type=IN)), 0),
        sum_out=Coalesce(Sum("transactions__quantity", filter=Q(transactions__type=OUT)), 0),
        last_at=Max("transactions__created_at"),
    )
    if q:
        warehouses = warehouses.filter(Q(name__icontains=q) | Q(address__icontains=q))
    if status == "active":
        warehouses = warehouses.filter(is_active=True)
    elif status == "inactive":
        warehouses = warehouses.filter(is_active=False)

    # تعداد ترکیب رنگ/سایزِ دارای موجودی در هر انبار (یک کوئری گروه‌بندی‌شده)
    nets = (
        StockTransaction.objects
        .values("warehouse_id", "variant_id")
        .annotate(
            net=Coalesce(Sum("quantity", filter=Q(type=IN)), 0)
            - Coalesce(Sum("quantity", filter=Q(type=OUT)), 0)
        )
    )
    variants_in = defaultdict(int)
    for row in nets:
        if row["net"] > 0:
            variants_in[row["warehouse_id"]] += 1

    items = list(warehouses)
    for w in items:
        w.net = w.sum_in - w.sum_out
        w.variants_n = variants_in.get(w.pk, 0)

    return render(request, "warehouse_list.html", {
        "warehouses": items,
        "filters": {"q": q, "status": status},
        "has_filters": bool(q or status),
        "summary": {
            "count": len(items),
            "active": sum(1 for w in items if w.is_active),
            "stock": sum(w.net for w in items),
            "tx": sum(w.tx_n for w in items),
        },
    })


@login_required
def warehouse_detail(request, pk):
    warehouse = get_object_or_404(Warehouse, pk=pk)
    q = request.GET.get("q", "").strip()
    show = request.GET.get("show", "")  # "" = دارای موجودی، "all" = همه‌ی سابقه‌دارها

    variants = (
        ProductVariant.objects
        .annotate(
            w_in=Coalesce(Sum("transactions__quantity",
                              filter=Q(transactions__warehouse=warehouse, transactions__type=IN)), 0),
            w_out=Coalesce(Sum("transactions__quantity",
                               filter=Q(transactions__warehouse=warehouse, transactions__type=OUT)), 0),
        )
        .annotate(w_net=F("w_in") - F("w_out"))
        .filter(Q(w_in__gt=0) | Q(w_out__gt=0))
        .select_related("product", "color", "size")
        .order_by("product__name", "color__name", "size__sort_order")
    )
    if q:
        variants = variants.filter(
            Q(product__name__icontains=q) | Q(product__sku__icontains=q) | Q(sku__icontains=q)
        )
    if show != "all":
        variants = variants.exclude(w_net=0)

    totals = StockTransaction.objects.filter(warehouse=warehouse).aggregate(
        count=Count("id"),
        sum_in=Coalesce(Sum("quantity", filter=Q(type=IN)), 0),
        sum_out=Coalesce(Sum("quantity", filter=Q(type=OUT)), 0),
        last_at=Max("created_at"),
    )
    net = totals["sum_in"] - totals["sum_out"]

    # فهرست کامل برای شمارش ترکیب‌ها و ناهمخوانی‌های منفی (بدون صفحه‌بندی)
    all_nets = (
        StockTransaction.objects.filter(warehouse=warehouse)
        .values("variant_id")
        .annotate(n=Coalesce(Sum("quantity", filter=Q(type=IN)), 0)
                  - Coalesce(Sum("quantity", filter=Q(type=OUT)), 0))
    )
    positive = sum(1 for r in all_nets if r["n"] > 0)
    negative = sum(1 for r in all_nets if r["n"] < 0)

    ctx = _paginate(request, variants, DETAIL_PAGE_SIZE)
    for v in ctx["page_obj"]:
        v.state = "neg" if v.w_net < 0 else ("zero" if v.w_net == 0 else "ok")

    recent = (
        StockTransaction.objects.filter(warehouse=warehouse)
        .select_related("variant__product", "variant__color", "variant__size", "created_by")
        .order_by("-created_at")[:8]
    )
    ctx.update({
        "warehouse": warehouse,
        "filters": {"q": q, "show": show},
        "has_filters": bool(q or show),
        "summary": {**totals, "net": net, "positive": positive, "negative": negative},
        "recent": recent,
    })
    return render(request, "warehouse_detail.html", ctx)
