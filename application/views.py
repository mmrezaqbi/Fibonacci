from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, F, IntegerField, Prefetch, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .permissions import role_required
from .forms import ProductCreateForm, StockInForm, StockOutForm
from .models import Category, Product, ProductVariant, StockTransaction

PAGE_SIZE = 12


@login_required
def home(request):
    today = timezone.localdate()

    # فقط تنوع‌های فعالِ محصولات فعال در آمار حساب می‌شوند
    variants = ProductVariant.objects.filter(is_active=True, product__is_active=True)
    low_stock = variants.filter(stock__lte=F("min_stock"))

    context = {
        "stats": {
            "total_products": Product.objects.filter(is_active=True).count(),
            "total_stock": variants.aggregate(total=Sum("stock"))["total"] or 0,
            "low_stock_count": low_stock.count(),
            "today_transactions": StockTransaction.objects.filter(created_at__date=today).count(),
        },
        "recent_transactions": (
            StockTransaction.objects
            .select_related("variant__product", "variant__color", "variant__size", "warehouse")
            .order_by("-created_at")[:8]
        ),
        "low_stock_items": (
            low_stock
            .select_related("product", "color", "size")
            .order_by("stock", "product__name")[:5]
        ),
    }
    return render(request, "home.html", context)


@login_required
def product_list(request):
    """لیست محصولات با موجودی کل هر محصول، جستجو، فیلتر و صفحه‌بندی."""
    q = request.GET.get("q", "").strip()
    category = request.GET.get("category", "").strip()
    gender = request.GET.get("gender", "").strip()
    stock = request.GET.get("stock", "").strip()

    qs = (
        Product.objects
        .select_related("category")
        .prefetch_related(
            Prefetch("variants", queryset=ProductVariant.objects.select_related("color"))
        )
        .annotate(
            # نام‌ها عمداً با property های مدل (total_stock) تداخل ندارند
            stock_sum=Coalesce(Sum("variants__stock"), Value(0), output_field=IntegerField()),
            variants_n=Count("variants"),
            low_n=Count("variants", filter=Q(variants__stock__lte=F("variants__min_stock"))),
        )
    )

    if q:
        qs = qs.filter(
            Q(name__icontains=q) | Q(sku__icontains=q) | Q(brand__icontains=q)
            # جستجو در کد/بارکد تنوع‌ها با subquery تا جمع موجودی خراب نشود
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

    paginator = Paginator(qs.order_by("name", "pk"), PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get("page"))

    products = list(page_obj.object_list)
    for p in products:
        colors = {}
        for v in p.variants.all():
            colors[v.color_id] = v.color
        p.color_list = list(colors.values())
        if p.stock_sum == 0:
            p.stock_status = "out"
        elif p.low_n > 0:
            p.stock_status = "low"
        else:
            p.stock_status = "ok"
    page_obj.object_list = products

    params = request.GET.copy()
    params.pop("page", None)

    return render(request, "product_list.html", {
        "page_obj": page_obj,
        "page_range": list(paginator.get_elided_page_range(page_obj.number, on_each_side=1, on_ends=1)),
        "ellipsis": paginator.ELLIPSIS,
        "total_count": paginator.count,
        "querystring": params.urlencode(),
        "categories": Category.objects.all(),
        "genders": Product.Gender.choices,
        "filters": {"q": q, "category": category, "gender": gender, "stock": stock},
        "has_filters": any([q, category, gender, stock]),
    })


@login_required
def product_detail(request, pk):
    """جزئیات محصول: موجودی هر رنگ و هر سایز در قالب جدول رنگ × سایز."""
    product = get_object_or_404(Product.objects.select_related("category"), pk=pk)
    variants = list(product.variants.select_related("color", "size"))

    colors = sorted({v.color for v in variants}, key=lambda c: c.name)
    sizes = sorted({v.size for v in variants}, key=lambda s: (s.sort_order, s.name))
    by_key = {(v.color_id, v.size_id): v for v in variants}

    def cell(v):
        if v is None:
            return None
        if v.stock == 0:
            cls = "zero"
        elif v.is_low_stock:
            cls = "low"
        else:
            cls = "ok"
        return {"variant": v, "stock": v.stock, "cls": cls}

    rows = []
    for color in colors:
        cells = [cell(by_key.get((color.pk, size.pk))) for size in sizes]
        rows.append({
            "color": color,
            "cells": cells,
            "total": sum(c["stock"] for c in cells if c),
        })
    col_totals = [
        sum(by_key[(c.pk, s.pk)].stock for c in colors if (c.pk, s.pk) in by_key)
        for s in sizes
    ]

    stats = {
        "total": sum(v.stock for v in variants),
        "variants": len(variants),
        "out": sum(1 for v in variants if v.stock == 0),
        "low": sum(1 for v in variants if 0 < v.stock <= v.min_stock),
        "value": sum(v.stock * v.unit_price for v in variants),
    }

    transactions = (
        StockTransaction.objects
        .filter(variant__product=product)
        .select_related("variant__color", "variant__size", "warehouse", "created_by")
        .order_by("-created_at")[:10]
    )

    return render(request, "product_detail.html", {
        "product": product,
        "sizes": sizes,
        "rows": rows,
        "col_totals": col_totals,
        "stats": stats,
        "transactions": transactions,
    })


@role_required("keeper")
def product_create(request):
    if request.method == "POST":
        form = ProductCreateForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            product = form.save()
            messages.success(
                request,
                f"محصول «{product.name}» با {product.variants.count()} ترکیب رنگ/سایز "
                f"و موجودی کل {product.total_stock} ثبت شد.",
            )
            return redirect("application:product_detail", pk=product.pk)
    else:
        form = ProductCreateForm(user=request.user)

    return render(request, "product_form.html", {"form": form})


def _stock_movement(request, *, form_class, ui):
    """
    منطق مشترک ورود و خروج: انتخاب محصول (GET ?product=<id>) ← ماتریس رنگ × سایز ←
    ثبت تراکنش‌ها. ارسال فرم به همین آدرس (با همان ?product) انجام می‌شود.
    """
    product = None
    product_id = request.GET.get("product", "")
    if product_id.isdigit():
        product = get_object_or_404(Product, pk=int(product_id))

    form = None
    if product:
        if request.method == "POST":
            form = form_class(request.POST, product=product, user=request.user)
            if form.is_valid():
                try:
                    count, total = form.save()
                except ValidationError as e:
                    # مثلاً موجودی هم‌زمان توسط کاربر دیگری کم شده است
                    form.add_error(None, e)
                else:
                    messages.success(
                        request, ui["done"].format(count=count, total=total, name=product.name)
                    )
                    return redirect("application:product_detail", pk=product.pk)
        else:
            form = form_class(product=product, user=request.user)

    products = (
        Product.objects.filter(is_active=True)
        .annotate(stock_sum=Coalesce(Sum("variants__stock"), Value(0), output_field=IntegerField()))
        .order_by("name")
    )
    recent = (
        StockTransaction.objects.filter(type=form_class.movement_type)
        .select_related("variant__product", "variant__color", "variant__size", "warehouse", "created_by")
        .order_by("-created_at")[:8]
    )

    return render(request, "stock_movement.html", {
        "product": product,
        "form": form,
        "products": products,
        "recent": recent,
        "mode": form_class.movement_type.value,  # "in" یا "out"
        "ui": ui,
    })


@role_required("keeper")
def stock_out(request):
    return _stock_movement(request, form_class=StockOutForm, ui={
        "title": "خروج از انبار",
        "subtitle": "محصول را انتخاب کنید و برای هر رنگ و سایز تعداد خروج را وارد کنید",
        "pick_lead": "محصولی را که می‌خواهید از آن خروج بزنید انتخاب کنید. موجودی کل هر محصول کنار نامش نوشته شده است.",
        "step2_title": "۲. تعداد خروج هر رنگ و سایز",
        "step2_lead": "فقط خانه‌هایی را پر کنید که از آن‌ها خروج می‌زنید. خانه‌ی خالی یعنی خروجی ثبت نمی‌شود.",
        "submit": "ثبت خروج",
        "post_url": reverse("application:stock_out"),
        "done": "خروج {count} قلم کالا (مجموع {total} عدد) از «{name}» ثبت شد.",
        "recent_title": "آخرین خروج‌ها",
        "recent_lead": "۸ خروج اخیر در کل انبار",
        "recent_empty": "هنوز خروجی ثبت نشده است.",
    })


@role_required("keeper")
def stock_in(request):
    return _stock_movement(request, form_class=StockInForm, ui={
        "title": "ورود به انبار",
        "subtitle": "محصول را انتخاب کنید و برای هر رنگ و سایز تعداد ورودی را وارد کنید",
        "pick_lead": "محصولی را که کالایش وارد انبار شده انتخاب کنید. موجودی کل هر محصول کنار نامش نوشته شده است.",
        "step2_title": "۲. تعداد ورود هر رنگ و سایز",
        "step2_lead": "فقط خانه‌هایی را پر کنید که کالا وارد شده است. خانه‌ی خالی یعنی ورودی ثبت نمی‌شود.",
        "submit": "ثبت ورود",
        "post_url": reverse("application:stock_in"),
        "done": "ورود {count} قلم کالا (مجموع {total} عدد) به «{name}» ثبت شد.",
        "recent_title": "آخرین ورودی‌ها",
        "recent_lead": "۸ ورودی اخیر در کل انبار",
        "recent_empty": "هنوز ورودی ثبت نشده است.",
    })
