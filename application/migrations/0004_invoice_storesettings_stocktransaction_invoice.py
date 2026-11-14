import re

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

# نمونه‌ی note فاکتورهای قبلی: «فاکتور خروج F261114-AB12C — توضیح اختیاری»
_NOTE_RE = re.compile(r"^فاکتور (?:خروج|ورود) (F\d{6}-[0-9A-F]{5})(?: — (.*))?$", re.S)


def backfill_invoices(apps, schema_editor):
    """فاکتورهای ثبت‌شده‌ی قبلی (که فقط در note تراکنش‌ها کد داشتند) را به رکورد Invoice وصل می‌کند."""
    StockTransaction = apps.get_model("application", "StockTransaction")
    Invoice = apps.get_model("application", "Invoice")

    by_code = {}
    qs = (
        StockTransaction.objects
        .filter(invoice__isnull=True, note__startswith="فاکتور ")
        .order_by("created_at", "pk")
    )
    for tx in qs.iterator():
        match = _NOTE_RE.match(tx.note or "")
        if not match:
            continue
        code = match.group(1)
        invoice_id = by_code.get(code)
        if invoice_id is None:
            invoice = Invoice.objects.create(
                code=code, type=tx.type, warehouse_id=tx.warehouse_id,
                note=(match.group(2) or "")[:255], created_by_id=tx.created_by_id,
            )
            # created_at با auto_now_add ساخته می‌شود؛ تاریخ واقعی فاکتور را جایگزین می‌کنیم
            Invoice.objects.filter(pk=invoice.pk).update(created_at=tx.created_at)
            invoice_id = by_code[code] = invoice.pk
        StockTransaction.objects.filter(pk=tx.pk).update(invoice_id=invoice_id)


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('application', '0003_stocktransaction_unit_price'),
    ]

    operations = [
        migrations.CreateModel(
            name='StoreSettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('store_name', models.CharField(blank=True, max_length=120, verbose_name='نام فروشگاه')),
            ],
            options={
                'verbose_name': 'تنظیمات فروشگاه',
                'verbose_name_plural': 'تنظیمات فروشگاه',
            },
        ),
        migrations.CreateModel(
            name='Invoice',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(max_length=30, unique=True, verbose_name='شماره فاکتور')),
                ('type', models.CharField(choices=[('in', 'ورود'), ('out', 'خروج')], max_length=3, verbose_name='نوع')),
                ('buyer_name', models.CharField(blank=True, max_length=120, verbose_name='نام خریدار')),
                ('buyer_phone', models.CharField(blank=True, db_index=True, max_length=20, verbose_name='شماره موبایل خریدار')),
                ('note', models.CharField(blank=True, max_length=255, verbose_name='توضیحات')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='تاریخ')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='invoices', to=settings.AUTH_USER_MODEL, verbose_name='ثبت‌کننده')),
                ('warehouse', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='invoices', to='application.warehouse', verbose_name='انبار')),
            ],
            options={
                'verbose_name': 'فاکتور',
                'verbose_name_plural': 'فاکتورها',
                'ordering': ['-created_at', '-pk'],
            },
        ),
        migrations.AddField(
            model_name='stocktransaction',
            name='invoice',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='transactions', to='application.invoice', verbose_name='فاکتور'),
        ),
        migrations.RunPython(backfill_invoices, migrations.RunPython.noop),
    ]
