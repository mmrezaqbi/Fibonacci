from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from extensions.utils import jalali_converter
# اگر از DecimalField برای phone_number استفاده کردید، آن را حذف کنید.

# ----------------------------------------------------
# 1. مدل CountryCode (بدون تغییر)
# ----------------------------------------------------
class CountryCode(models.Model):
    name = models.CharField(max_length=50, verbose_name="نام کشور")
    # کد پیش‌شماره (مثلاً +98)
    code = models.CharField(max_length=10, unique=True, verbose_name="کد بین‌المللی") 

    class Meta:
        verbose_name = "کد کشور"
        verbose_name_plural = "کدهای کشور"

    def __str__(self):
        return f'{self.name} ({self.code})'



# ----------------------------------------------------
# مدل CustomUser (به‌روزرسانی شده)
# ----------------------------------------------------

class CustomUser(AbstractUser):
    STATUS_CHOICES = (
        ('m', 'مرد'),
        ('f', "زن"),
        ('a', "نامعلوم"),
        ('p', "ترجیح میدهم نگویم"),
    )
    # تنظیم مجوزها به طور صریح
    is_staff = models.BooleanField(default=False, verbose_name='پرسنل (Staff Status)')
    is_superuser = models.BooleanField(default=False, verbose_name='ابرکاربر (Superuser Status)')
    
    # تنظیمات فیلدهای سفارشی (بر اساس تحلیل قبلی)
    phone_regex = RegexValidator(regex=r'^\d{8,15}$', message="شماره تلفن باید در فرمت 9876543210 (حداقل ۸ و حداکثر ۱۵ رقم) باشد.")
    
    country_code = models.ForeignKey(CountryCode , on_delete=models.SET_NULL , blank=True , null=True , verbose_name='کد کشور', related_name='country')
    
    phone_number = models.CharField(validators=[phone_regex] , max_length=15 , unique=True , blank=True , null=True , verbose_name='شماره تلفن')
    
    avatar = models.ImageField(upload_to='uploads/profiles/' , blank=True , null=True , verbose_name='آواتار')
    
    address = models.TextField(blank=True , null=True , verbose_name='آدرس')

    national_code = models.CharField(max_length=40 , blank=True , null=True , verbose_name="کد ملی")
    birthday = models.DateField(blank=True , null=True , verbose_name='تاریخ تولد')
    father_name = models.CharField(max_length=255 , blank=True , null=True , verbose_name='نام پدر')
    postal_code = models.CharField(max_length=40 , blank=True , null=True , verbose_name="کد پستی")
    gender = models.CharField(max_length=1, choices=STATUS_CHOICES, default='a', verbose_name="جنسیت")
    

    class Meta:
        verbose_name = 'کاربر'
        verbose_name_plural = 'کاربران'

    def jdjoined(self):
        return jalali_converter(self.date_joined)
    jdjoined.short_description = "زمان ثبت نام"

    def jlastlogin(self):
        return jalali_converter(self.last_login)
    jlastlogin.short_description = "زمان آخرین ورود"


    def jbirthday(self):
        return jalali_converter(self.birthday)
    jbirthday.short_description = "تاریخ تولد"