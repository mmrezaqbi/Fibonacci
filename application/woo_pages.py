"""صفحه‌ی تنظیمات ووکامرس (فقط مدیر) و آدرس وب‌هوک."""
import base64
import hashlib
import hmac
import json

from django import forms
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from . import permissions, woo_client, woo_sync
from .models import (
    ProductVariant, Warehouse, WooLog, WooOrder, WooProductLink, WooSettings, WooVariantLink,
)

admin_only = permissions.role_required(permissions.ADMIN)


class WooSettingsForm(forms.ModelForm):
    class Meta:
        model = WooSettings
        fields = ["site_url", "consumer_key", "consumer_secret", "webhook_secret", "default_warehouse", "enabled"]
        widgets = {
            "site_url": forms.TextInput(attrs={"dir": "ltr", "placeholder": "https://example.com", "autocomplete": "off"}),
            "consumer_key": forms.TextInput(attrs={"dir": "ltr", "placeholder": "ck_...", "autocomplete": "off"}),
            "consumer_secret": forms.PasswordInput(render_value=False, attrs={"dir": "ltr", "placeholder": "cs_...", "autocomplete": "new-password"}),
            "webhook_secret": forms.PasswordInput(render_value=False, attrs={"dir": "ltr", "autocomplete": "new-password"}),
        }
        labels = {"enabled": "همگام‌سازی فعال است"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("consumer_secret", "webhook_secret"):
            self.fields[name].required = False
            if getattr(self.instance, name):
                self.fields[name].help_text = "ذخیره شده است؛ برای حفظ مقدار فعلی خالی بگذارید."
        self.fields["default_warehouse"].queryset = Warehouse.objects.filter(is_active=True)
        self.fields["default_warehouse"].required = False
        self.fields["site_url"].required = False
        self.fields["consumer_key"].required = False

    def clean_site_url(self):
        url = self.cleaned_data["site_url"].strip().rstrip("/")
        if url and not url.lower().startswith(("http://", "https://")):
            raise forms.ValidationError("آدرس باید با http:// یا https:// شروع شود.")
        return url

    def clean_consumer_secret(self):
        return self.cleaned_data["consumer_secret"] or self.instance.consumer_secret

    def clean_webhook_secret(self):
        return self.cleaned_data["webhook_secret"] or self.instance.webhook_secret

    def clean(self):
        data = super().clean()
        if data.get("enabled") and not (data.get("site_url") and data.get("consumer_key") and data.get("consumer_secret")):
            raise forms.ValidationError("برای فعال‌سازی، آدرس سایت، Consumer key و Consumer secret را وارد کنید.")
        return data

    def save(self, commit=True):
        obj = super().save(commit=False)
        if obj.enabled:
            now = timezone.now()
            obj.sync_started_at = obj.sync_started_at or now  # سفارش‌های قدیمی‌تر از این لحظه هرگز از انبار کم نمی‌شوند
            obj.last_order_pull = obj.last_order_pull or now
        obj.save()
        return obj


def _run_action(request, action):
    try:
        if action == "test":
            woo_sync.get_client().get("products", {"per_page": 1})
            messages.success(request, "اتصال به ووکامرس برقرار است و کلیدها معتبرند.")
        elif action == "sync_all":
            r = woo_sync.sync_all()
            text = (f"همگام‌سازی انجام شد: {r['products']} محصول، {r['variants_linked']} رنگ/سایز جدید ساخته شد، "
                    f"موجودی {r['stock_sent']} کالا ارسال شد.")
            (messages.warning if r["errors"] else messages.success)(
                request, text + (f" {r['errors']} خطا (جزئیات در گزارش پایین صفحه)." if r["errors"] else ""))
        elif action == "pull":
            r = woo_sync.pull_orders()
            if r["first"]:
                messages.info(request, "دریافت سفارش‌ها از همین لحظه شروع شد؛ سفارش‌های قبلی در انبار اعمال نمی‌شوند.")
            else:
                messages.success(request, f"{r['orders']} سفارش بررسی شد: {r['deducted']} خروج و {r['restored']} برگشت ثبت شد.")
    except woo_client.WooError as exc:
        messages.error(request, str(exc))


@admin_only
def woo_settings(request):
    settings = WooSettings.load()
    if request.method == "POST":
        action = request.POST.get("action", "save")
        if action == "save":
            form = WooSettingsForm(request.POST, instance=settings)
            if form.is_valid():
                form.save()
                messages.success(request, "تنظیمات ووکامرس ذخیره شد.")
                return redirect("application:woo_settings")
        else:
            if not settings.configured:
                messages.error(request, "ابتدا آدرس سایت و کلیدهای API را ذخیره کنید.")
            else:
                _run_action(request, action)
            return redirect("application:woo_settings")
    else:
        form = WooSettingsForm(instance=settings)

    return render(request, "settings_woo.html", {
        "section": "woo", "form": form, "s": settings,
        "webhook_url": request.build_absolute_uri(reverse("application:woo_webhook")),
        "stats": {
            "products": WooProductLink.objects.count(),
            "variants": WooVariantLink.objects.count(),
            "unlinked": ProductVariant.objects.filter(is_active=True, woo_link__isnull=True).count(),
        },
        "logs": WooLog.objects.all()[:15],
        "problem_orders": WooOrder.objects.exclude(note="")[:8],
    })


@csrf_exempt
@require_POST
def woo_webhook(request):
    """دریافت وب‌هوک ووکامرس (Order created / Order updated). با امضای HMAC-SHA256 تأیید می‌شود."""
    settings = WooSettings.load()
    if not settings.webhook_secret:
        return HttpResponse(status=403)
    expected = base64.b64encode(
        hmac.new(settings.webhook_secret.encode(), request.body, hashlib.sha256).digest()
    ).decode()
    if not hmac.compare_digest(request.headers.get("X-WC-Webhook-Signature", ""), expected):
        return HttpResponse(status=401)
    if not settings.enabled:
        return JsonResponse({"ignored": "disabled"})
    topic = request.headers.get("X-WC-Webhook-Topic", "")
    if not topic.startswith("order."):
        return JsonResponse({"ignored": topic})
    try:
        order = json.loads(request.body)
        order_id = order["id"]
    except (ValueError, KeyError, TypeError):
        return JsonResponse({"ignored": "ping"})  # پیام آزمایشی هنگام ساخت وب‌هوک
    try:
        outcome = woo_sync.apply_order(order, settings)
    except Exception as exc:  # noqa: BLE001
        woo_sync.log(False, f"سفارش #{order_id} (وب‌هوک): {exc}")
        return HttpResponse(status=500)  # ووکامرس دوباره تلاش می‌کند
    return JsonResponse({"ok": True, "outcome": outcome})
