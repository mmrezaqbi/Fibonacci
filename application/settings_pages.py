"""صفحه‌های تنظیمات (فقط مدیر): رنگ‌ها، سایزها و کاربران."""
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db.models import Count , IntegerField , Sum , Value
from django.core.paginator import Paginator
from django.db import transaction    
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.db.models.functions import Coalesce
from . import permissions
from .models import Color, Size, Warehouse , Product , StockTransaction , StoreSettings
from .settings_forms import ColorForm, SizeForm, UserCreateForm, UserEditForm, WarehouseForm , ProductEditForm , ProductDeleteForm , StoreSettingsForm

User = get_user_model()
admin_only = permissions.role_required(permissions.ADMIN)

# تنظیمات مشترک رنگ و سایز
SIMPLE = {
    "color": {
        "model": Color, "form": ColorForm, "list_url": "application:color_list", "edit_url": "application:color_edit", "delete_url": "application:color_delete",
        "title": "رنگ‌ها", "subtitle": "رنگ‌هایی که هنگام افزودن کالا قابل انتخاب‌اند",
        "singular": "رنگ", "add_title": "افزودن رنگ جدید",
    },
    "size": {
        "model": Size, "form": SizeForm, "list_url": "application:size_list", "edit_url": "application:size_edit", "delete_url": "application:size_delete",
        "title": "سایزها", "subtitle": "سایزهایی که هنگام افزودن کالا قابل انتخاب‌اند",
        "singular": "سایز", "add_title": "افزودن سایز جدید",
    },
    "warehouse": {
        "model": Warehouse, "form": WarehouseForm, "list_url": "application:warehouse_settings", "edit_url": "application:warehouse_edit", "delete_url": "application:warehouse_delete",
        "title": "انبارها", "subtitle": "افزودن و ویرایش انبارها؛ انباری که تراکنش دارد فقط غیرفعال می‌شود",
        "singular": "انبار", "add_title": "افزودن انبار جدید", "rel": "transactions", "used_label": "تعداد تراکنش",
    },
}
for _cfg in SIMPLE.values():
    _cfg.setdefault("rel", "variants")
    _cfg.setdefault("used_label", "تعداد ترکیب‌های ثبت‌شده")


@admin_only
def settings_index(request):
    return redirect("application:color_list")


@admin_only
def store_settings(request):
    """نام فروشگاه (بالای فاکتور چاپی) را اضافه یا ویرایش می‌کند."""
    store = StoreSettings.load()
    form = StoreSettingsForm(request.POST or None, instance=store)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "اطلاعات فروشگاه ذخیره شد.")
        return redirect("application:store_settings")
    return render(request, "settings_form.html", {
        "form": form, "title": "اطلاعات فروشگاه",
        "lead": "نام فروشگاه روی بالای فاکتورهای چاپی نمایش داده می‌شود.",
        "submit": "ذخیره", "cancel_url": reverse("application:store_settings"), "section": "store",
    })


@admin_only
def simple_list(request, kind):
    cfg = SIMPLE[kind]
    form = cfg["form"](request.POST or None)
    if request.method == "POST" and form.is_valid():
        obj = form.save()
        messages.success(request, f"{cfg['singular']} «{obj.name}» اضافه شد.")
        return redirect(cfg["list_url"])
    items = list(cfg["model"].objects.annotate(used=Count(cfg["rel"])))
    for it in items:  # آدرس‌ها در ویو ساخته می‌شوند تا قالب به {% url %} متغیر وابسته نباشد
        it.edit_href = reverse(cfg["edit_url"], args=[it.pk])
        it.delete_href = reverse(cfg["delete_url"], args=[it.pk])
    return render(request, "settings_simple.html", {"kind": kind, "section": kind, "cfg": cfg, "form": form, "items": items})


@admin_only
def simple_edit(request, kind, pk):
    cfg = SIMPLE[kind]
    obj = get_object_or_404(cfg["model"], pk=pk)
    form = cfg["form"](request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"{cfg['singular']} «{obj.name}» ذخیره شد.")
        return redirect(cfg["list_url"])
    return render(request, "settings_form.html", {
        "form": form, "title": f"ویرایش {cfg['singular']} «{obj.name}»", "lead": "",
        "submit": "ذخیره تغییرات", "cancel_url": reverse(cfg["list_url"]), "section": kind,
    })


@admin_only
@require_POST
def simple_delete(request, kind, pk):
    cfg = SIMPLE[kind]
    obj = get_object_or_404(cfg["model"], pk=pk)
    if getattr(obj, cfg["rel"]).exists():
        extra = " به‌جای حذف، آن را غیرفعال کنید." if kind == "warehouse" else ""
        messages.error(request, f"{cfg['singular']} «{obj.name}» سابقه دارد و حذف نمی‌شود.{extra}")
    else:
        obj.delete()
        messages.success(request, f"{cfg['singular']} «{obj.name}» حذف شد.")
    return redirect(cfg["list_url"])


# ---------------------------------------------------------------------------
# کاربران
# ---------------------------------------------------------------------------
@admin_only
def user_list(request):
    users = list(User.objects.order_by("-is_superuser", "username").prefetch_related("groups"))
    for u in users:
        role = permissions.get_role(u)
        u.role_key, u.role_label = role, permissions.LABELS[role]
        u.is_me = u.pk == request.user.pk
    return render(request, "settings_users.html", {
        "users": users, "section": "user",
        "roles": [(k, permissions.LABELS[k], permissions.DESCRIPTIONS[k]) for k in (permissions.ADMIN, permissions.KEEPER, permissions.VIEWER)],
    })


@admin_only
def user_create(request):
    form = UserCreateForm(request.POST or None, acting_user=request.user)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        messages.success(request, f"کاربر «{user.username}» با سطح دسترسی {permissions.LABELS[permissions.get_role(user)]} ساخته شد.")
        return redirect("application:user_list")
    return render(request, "settings_form.html", {
        "form": form, "title": "افزودن کاربر جدید", "lead": "نام کاربری، رمز عبور و سطح دسترسی را تعیین کنید.",
        "submit": "ساخت کاربر", "cancel_url": reverse("application:user_list"), "section": "user",
    })


@admin_only
def user_edit(request, pk):
    user = get_object_or_404(User, pk=pk)
    form = UserEditForm(request.POST or None, instance=user, acting_user=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"اطلاعات «{user.username}» ذخیره شد.")
        return redirect("application:user_list")
    return render(request, "settings_form.html", {
        "form": form, "title": f"ویرایش کاربر «{user.username}»", "lead": "",
        "submit": "ذخیره تغییرات", "cancel_url": reverse("application:user_list"), "section": "user",
    })


@admin_only
@require_POST
def user_delete(request, pk):
    user = get_object_or_404(User, pk=pk)
    if user.pk == request.user.pk:
        messages.error(request, "نمی‌توانید حساب خودتان را حذف کنید.")
    elif user.is_superuser and not User.objects.filter(is_superuser=True, is_active=True).exclude(pk=user.pk).exists():
        messages.error(request, "حداقل یک مدیر فعال باید در سامانه باقی بماند.")
    else:
        name = user.username
        user.delete()  # تراکنش‌های ثبت‌شده‌ی او حفظ می‌شود (ثبت‌کننده خالی می‌شود)
        messages.success(request, f"کاربر «{name}» حذف شد.")
    return redirect("application:user_list")




# ---------------------------------------------------------------------------
# کالاها: ویرایش و حذف (فقط مدیر، با تأیید رمز)
# ---------------------------------------------------------------------------
PRODUCT_PAGE_SIZE = 20


@admin_only
def product_manage_list(request):
    q = request.GET.get("q", "").strip()
    qs = (
        Product.objects.select_related("category")
        .annotate(
            stock_sum=Coalesce(Sum("variants__stock"), Value(0), output_field=IntegerField()),
            variants_n=Count("variants"),
        )
    )
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(sku__icontains=q) | Q(brand__icontains=q))

    paginator = Paginator(qs.order_by("name", "pk"), PRODUCT_PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)

    return render(request, "settings_products.html", {
        "section": "product",
        "page_obj": page_obj,
        "page_range": list(paginator.get_elided_page_range(page_obj.number, on_each_side=1, on_ends=1)),
        "ellipsis": paginator.ELLIPSIS,
        "querystring": params.urlencode(),
        "total_count": paginator.count,
        "q": q,
    })


@admin_only
def product_manage_edit(request, pk):
    product = get_object_or_404(Product, pk=pk)
    original_name = product.name  # برای عنوان صفحه (فرم هنگام اعتبارسنجی نمونه را تغییر می‌دهد)
    form = ProductEditForm(
        request.POST or None, request.FILES or None,
        instance=product, acting_user=request.user,
    )
    if request.method == "POST" and form.is_valid():
        product = form.save()
        msg = f"محصول «{product.name}» ذخیره شد."
        if form.created_variants:
            msg += (f" {len(form.created_variants)} ترکیب جدید رنگ/سایز با موجودی صفر ساخته شد؛ "
                    "موجودی را از بخش «ورود» ثبت کنید.")
        messages.success(request, msg)
        return redirect("application:product_manage_list")
    return render(request, "settings_product_edit.html", {
        "form": form, "product": product, "original_name": original_name, "section": "product",
    })


@admin_only
def product_manage_delete(request, pk):
    product = get_object_or_404(Product, pk=pk)
    tx_count = StockTransaction.objects.filter(variant__product=product).count()
    form = ProductDeleteForm(
        request.POST or None, acting_user=request.user, has_history=tx_count > 0,
    )
    if request.method == "POST" and form.is_valid():
        name = product.name
        image_name, storage = product.image.name, product.image.storage
        try:
            with transaction.atomic():
                if tx_count:
                    StockTransaction.objects.filter(variant__product=product).delete()
                product.delete()  # تنوع‌ها و لینک‌های ووکامرس با CASCADE پاک می‌شوند
        except ProtectedError:
            messages.error(request, f"محصول «{name}» به‌دلیل وابستگی به داده‌های دیگر حذف نشد.")
            return redirect("application:product_manage_list")
        if image_name:
            try:
                storage.delete(image_name)
            except OSError:
                pass
        messages.success(request, f"محصول «{name}» حذف شد.")
        return redirect("application:product_manage_list")

    return render(request, "settings_product_delete.html", {
        "form": form, "product": product, "section": "product",
        "tx_count": tx_count, "has_history": tx_count > 0,
        "variants_n": product.variants.count(), "stock_total": product.total_stock,
    })