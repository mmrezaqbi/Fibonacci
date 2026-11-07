"""
فیلترهای تاریخ شمسی برای قالب‌ها. تبدیل اصلی را اکستنشن خود پروژه (utils.jalali_converter) انجام می‌دهد.

    {% load jalali_tags %}
    {{ t.created_at|jdatetime }}   →  ۱۶ آبان ۱۴۰۵، ساعت ۱۱:۱۷
    {{ t.created_at|jdate }}       →  ۱۶ آبان ۱۴۰۵
    {% jtoday %}                   →  تاریخ امروز به شمسی
"""
import datetime

from django import template
from django.utils import timezone

from .. import dates
from ..utils import jalali_converter, persian_numbers_converter

register = template.Library()

JMONTHS = [
    "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند",
]


@register.filter
def jdatetime(value):
    """datetime → «۱۶ آبان ۱۴۰۵، ساعت ۱۱:۱۷» (با jalali_converter پروژه)"""
    if not value:
        return ""
    if not isinstance(value, datetime.datetime):
        return jdate(value)
    if timezone.is_naive(value):
        value = timezone.make_aware(value)  # jalali_converter ورودی aware می‌خواهد
    return jalali_converter(value)


@register.filter
def jdate(value):
    """date یا datetime → «۱۶ آبان ۱۴۰۵» (فقط تاریخ، با ارقام فارسی)"""
    if not value:
        return ""
    if isinstance(value, datetime.datetime) and timezone.is_aware(value):
        value = timezone.localtime(value)
    year, month, day = dates.to_jalali_tuple(value)
    return persian_numbers_converter(f"{day} {JMONTHS[month - 1]} {year}")


@register.simple_tag
def jtoday():
    """تاریخ امروز به شمسی"""
    return jdate(timezone.now())
