"""سطح دسترسی کاربران.

سه نقش وجود دارد:
  • مدیر (admin)       : کاربر superuser؛ دسترسی کامل از جمله تنظیمات و پنل مدیریت
  • انباردار (keeper)  : عضو گروه «انباردار»؛ می‌تواند کالا اضافه کند و ورود/خروج ثبت کند
  • مشاهده‌گر (viewer) : عضو گروه «مشاهده‌گر» (یا بدون گروه)؛ فقط مشاهده‌ی کالاها، انبارها و گزارش‌ها

نقش‌ها در گروه‌های جنگو ذخیره می‌شوند؛ گروه‌ها در صورت نبودن خودکار ساخته می‌شوند
و نیازی به migration یا تعریف permission جداگانه نیست.
"""
from functools import wraps

from django.contrib import messages
from django.contrib.auth.models import Group
from django.contrib.auth.views import redirect_to_login
from django.shortcuts import redirect

ADMIN, KEEPER, VIEWER = "admin", "keeper", "viewer"
LEVEL = {VIEWER: 1, KEEPER: 2, ADMIN: 3}
LABELS = {ADMIN: "مدیر", KEEPER: "انباردار", VIEWER: "مشاهده‌گر"}
DESCRIPTIONS = {
    ADMIN: "دسترسی کامل: مدیریت کاربران، تنظیمات (رنگ و سایز)، پنل مدیریت و همه‌ی امکانات انبار",
    KEEPER: "افزودن کالا و ثبت ورود و خروج؛ مشاهده‌ی کالاها، انبارها و گزارش‌ها",
    VIEWER: "فقط مشاهده‌ی کالاها، انبارها و گزارش‌ها",
}
GROUP_NAMES = {KEEPER: "انباردار", VIEWER: "مشاهده‌گر"}
CHOICES = [(r, LABELS[r]) for r in (ADMIN, KEEPER, VIEWER)]


def get_role(user):
    if not getattr(user, "is_authenticated", False):
        return None
    if user.is_superuser:
        return ADMIN
    names = set(user.groups.values_list("name", flat=True))
    if GROUP_NAMES[KEEPER] in names:
        return KEEPER
    return VIEWER


def has_role(user, level):
    role = get_role(user)
    return bool(role) and user.is_active and LEVEL[role] >= LEVEL[level]


def set_role(user, role):
    """نقش را روی کاربر (که باید قبلاً ذخیره شده باشد) اعمال می‌کند."""
    if role not in LEVEL:
        raise ValueError(role)
    user.groups.remove(*Group.objects.filter(name__in=GROUP_NAMES.values()))
    if role == ADMIN:
        user.is_superuser = user.is_staff = True
    else:
        user.is_superuser = user.is_staff = False
        group, _ = Group.objects.get_or_create(name=GROUP_NAMES[role])
        user.groups.add(group)
    user.save(update_fields=["is_superuser", "is_staff"])


def role_required(level):
    """ورود لازم است و کاربر باید حداقل سطح دسترسی `level` را داشته باشد."""
    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if not has_role(request.user, level):
                messages.error(request, "شما به این بخش دسترسی ندارید.")
                return redirect("home")
            return view(request, *args, **kwargs)
        return wrapper
    return decorator
