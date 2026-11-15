"""PWA: مانیفست، سرویس‌ورکر و صفحه‌ی آفلاین (برای نصب برنامه روی گوشی).

هر سه آدرس باید بدون لاگین در دسترس باشند و از ریشه‌ی سایت سرو شوند
(سرویس‌ورکر فقط روی مسیرهای زیرمجموعه‌ی آدرس خودش کنترل دارد).
"""
import json

from django.http import HttpResponse
from django.shortcuts import render
from django.templatetags.static import static
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe

APP_NAME = "سامانه انبارداری فیبوناچی"
SHORT_NAME = "انبار"
THEME_COLOR = "#0b0e14"


@require_safe
def manifest(request):
    data = {
        "id": "/",
        "name": APP_NAME,
        "short_name": SHORT_NAME,
        "description": "مدیریت موجودی، فاکتور و گزارش‌های انبار پوشاک",
        "lang": "fa",
        "dir": "rtl",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "orientation": "any",
        "background_color": THEME_COLOR,
        "theme_color": THEME_COLOR,
        "icons": [
            {"src": static("icons/icon-192.png"), "sizes": "192x192", "type": "image/png", "purpose": "any"},
            {"src": static("icons/icon-512.png"), "sizes": "512x512", "type": "image/png", "purpose": "any"},
            {"src": static("icons/icon-maskable-512.png"), "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
        ],
    }
    response = HttpResponse(
        json.dumps(data, ensure_ascii=False),
        content_type="application/manifest+json; charset=utf-8",
    )
    response["Cache-Control"] = "public, max-age=3600"
    return response


@require_safe
@never_cache
def service_worker(request):
    response = render(request, "pwa/sw.js", content_type="application/javascript; charset=utf-8")
    response["Service-Worker-Allowed"] = "/"
    return response


@require_safe
def offline(request):
    return render(request, "pwa/offline.html", {"app_name": APP_NAME})
