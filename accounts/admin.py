from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser, CountryCode

# ----------------------------------------------------
# 1. مدیریت مدل CustomUser
# ----------------------------------------------------

# اگر می‌خواهید فیلدهای CustomUser در پنل ادمین نمایش داده شوند، 
# باید از کلاس‌های Form و Admin سفارشی استفاده کنید.
from django.contrib.auth.forms import UserCreationForm, UserChangeForm

class CustomUserCreationForm(UserCreationForm):
    """فرم سفارشی برای ایجاد کاربر جدید در پنل ادمین"""
    class Meta(UserCreationForm.Meta):
        model = CustomUser
        fields = UserCreationForm.Meta.fields + ('country_code', 'phone_number', 'avatar', 'address')

class CustomUserChangeForm(UserChangeForm):
    """فرم سفارشی برای ویرایش کاربر در پنل ادمین"""
    class Meta:
        model = CustomUser
        fields = UserChangeForm.Meta.fields

class CustomUserAdmin(UserAdmin):
    # تنظیم فرم‌ها
    form = CustomUserChangeForm
    add_form = CustomUserCreationForm
    
    # فیلدهایی که در لیست کاربران در پنل ادمین نمایش داده می‌شوند
    list_display = ('username', 'email', 'first_name', 'last_name', 'phone_number', 'is_staff', 'is_active')
    
    # فیلدهایی که برای جستجو استفاده می‌شوند
    search_fields = ('username', 'email', 'phone_number')
    
    # گروه‌بندی فیلدها در صفحه جزئیات کاربر
    fieldsets = UserAdmin.fieldsets + (
        ('اطلاعات تماس و آدرس', {'fields': ('country_code', 'phone_number', 'address', 'avatar')}),
        ('اطلاعات اضافه شده', {'fields': ('father_name', 'postal_code', 'national_code', 'gender' , 'birthday')}),
    )

    add_fieldsets = UserAdmin.add_fieldsets + (
        ('اطلاعات تماس و آدرس', {'fields': ('country_code', 'phone_number', 'address', 'avatar')}),
    )

# ثبت مدل CustomUser در پنل ادمین
admin.site.register(CustomUser, CustomUserAdmin)

# ----------------------------------------------------
# 2. مدیریت مدل CountryCode
# ----------------------------------------------------

@admin.register(CountryCode)
class CountryCodeAdmin(admin.ModelAdmin):
    list_display = ('name', 'code')
    search_fields = ('name', 'code')