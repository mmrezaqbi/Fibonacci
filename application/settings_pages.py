"""صفحه‌های تنظیمات (فقط مدیر): رنگ‌ها، سایزها و کاربران."""
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from . import permissions
from .models import Color, Size, Warehouse
from .settings_forms import ColorForm, SizeForm, UserCreateForm, UserEditForm, WarehouseForm

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