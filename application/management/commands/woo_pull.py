from django.core.management.base import BaseCommand, CommandError

from ... import woo_client, woo_sync


class Command(BaseCommand):
    help = "سفارش‌های جدید/تغییریافته‌ی ووکامرس را می‌گیرد و خروج آن‌ها را در انبار ثبت می‌کند (برای اجرای زمان‌بندی‌شده)."

    def handle(self, *args, **options):
        try:
            r = woo_sync.pull_orders()
        except woo_client.WooError as exc:
            raise CommandError(str(exc))
        self.stdout.write(f"{r['orders']} سفارش بررسی شد؛ {r['deducted']} خروج، {r['restored']} برگشت.")
