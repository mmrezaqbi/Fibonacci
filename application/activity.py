"""ثبت فعالیت کاربران. خطا در ثبت لاگ هرگز نباید کار اصلی کاربر را خراب کند."""
import logging

from .models import ActivityLog

logger = logging.getLogger(__name__)
A = ActivityLog.Action


def _client_ip(request):
    if request is None:
        return None
    # پشت پروکسی معکوس ممکن است X-Forwarded-For باشد؛ فقط برای اطلاع است، نه امنیت
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    ip = forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR", "")
    return ip or None


def log_activity(request, action, detail="", user=None):
    try:
        user = user or getattr(request, "user", None)
        if user is not None and not getattr(user, "is_authenticated", False):
            user = None
        ActivityLog.objects.create(
            user=user,
            username=getattr(user, "username", "") or "",
            action=action,
            detail=str(detail)[:500],
            ip_address=_client_ip(request),
        )
    except Exception:  # noqa: BLE001
        logger.exception("ثبت فعالیت کاربر انجام نشد")
