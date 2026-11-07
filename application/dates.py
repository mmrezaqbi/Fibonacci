"""
کمک‌های تاریخ شمسی بر پایه‌ی ماژول jalali.py خود پروژه (بدون وابستگی به جنگو).
"""
import datetime
import re

from . import jalali

# ارقام فارسی و عربی → لاتین
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

_DATE_RE = re.compile(r"^(\d{4})\D(\d{1,2})\D(\d{1,2})$")


def to_jalali_tuple(value):
    """date یا datetime میلادی → (سال, ماه, روز) شمسی"""
    return jalali.Gregorian(value.year, value.month, value.day).persian_tuple()


def to_jalali_string(value):
    """date یا datetime میلادی → «1405/08/16» (ارقام لاتین، مناسب فیلتر و Excel)"""
    y, m, d = to_jalali_tuple(value)
    return f"{y}/{m:02d}/{d:02d}"


def parse_user_date(text):
    """
    تاریخ واردشده توسط کاربر را به datetime.date میلادی تبدیل می‌کند.
    شمسی (1405/08/16 یا ۱۴۰۵-۸-۱۶) و میلادی (2026-11-07) هر دو پذیرفته می‌شوند.
    ورودی خالی یا نامعتبر None می‌دهد.
    """
    text = (text or "").strip().translate(_DIGITS)
    match = _DATE_RE.match(text)
    if not match:
        return None
    year, month, day = (int(g) for g in match.groups())
    try:
        if year < 1700:  # سال شمسی
            return jalali.Persian(year, month, day).gregorian_datetime()
        return datetime.date(year, month, day)
    except Exception:  # jalali.Persian خطای عمومی Exception می‌دهد
        return None
