import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('application', '0004_invoice_storesettings_stocktransaction_invoice'),
    ]

    operations = [
        migrations.CreateModel(
            name='ActivityLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('username', models.CharField(blank=True, max_length=150, verbose_name='نام کاربری')),
                ('action', models.CharField(choices=[('login', 'ورود به برنامه'), ('logout', 'خروج از برنامه'), ('invoice_out', 'ثبت فاکتور خروج'), ('invoice_in', 'ثبت فاکتور ورود'), ('stock_out', 'ثبت خروج کالا'), ('stock_in', 'ثبت ورود کالا'), ('product_create', 'افزودن کالا'), ('product_edit', 'ویرایش کالا'), ('product_delete', 'حذف کالا'), ('category', 'مدیریت دسته‌بندی'), ('settings', 'تغییر تنظیمات'), ('user_manage', 'مدیریت کاربران')], db_index=True, max_length=20, verbose_name='فعالیت')),
                ('detail', models.CharField(blank=True, max_length=500, verbose_name='توضیح')),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True, verbose_name='آدرس IP')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='زمان')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='activity_logs', to=settings.AUTH_USER_MODEL, verbose_name='کاربر')),
            ],
            options={
                'verbose_name': 'فعالیت کاربر',
                'verbose_name_plural': 'فعالیت‌های کاربران',
                'ordering': ['-created_at', '-pk'],
            },
        ),
    ]
