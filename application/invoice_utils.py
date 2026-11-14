"""کمک‌های مشترک مربوط به مشخصات خریدار در فاکتور (نام و شماره موبایل)."""
import re

from django.db.models import Q

# ارقام فارسی و عربی -> انگلیسی
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
# «ي» و «ك» عربی -> «ی» و «ک» فارسی تا جستجوی نام به نوع کیبورد وابسته نباشد
_LETTERS = str.maketrans({"ي": "ی", "ك": "ک"})

_MOBILE_RE = re.compile(r"^09\d{9}$")
_DIGITS_ONLY_RE = re.compile(r"^[\d\s+\-]+$")

BUYER_NAME_MAX = 120


def latin_digits(text):
    return str(text or "").translate(_DIGITS)


def clean_buyer_name(text):
    """فاصله‌های اضافه حذف و حروف عربی به فارسی تبدیل می‌شود."""
    return " ".join(str(text or "").translate(_LETTERS).split())


def normalize_phone(text):
    """
    شماره موبایل را به شکل استاندارد 09xxxxxxxxx درمی‌آورد
    (ارقام فارسی، فاصله، خط تیره، +98 و 0098 پذیرفته می‌شود).
    اگر شکل استاندارد نشد، فقط ارقام را برمی‌گرداند.
    """
    digits = re.sub(r"\D", "", latin_digits(text))
    if digits.startswith("0098"):
        digits = "0" + digits[4:]
    elif digits.startswith("98") and len(digits) == 12:
        digits = "0" + digits[2:]
    elif len(digits) == 10 and digits.startswith("9"):
        digits = "0" + digits
    return digits


def is_valid_mobile(phone):
    return bool(_MOBILE_RE.match(phone or ""))


def looks_like_phone_query(text):
    """آیا عبارت جستجو فقط از رقم (و فاصله، + و -) تشکیل شده است؟"""
    return bool(_DIGITS_ONLY_RE.match(latin_digits(text).strip()))


def invoice_search_q(query):
    """
    شرط جستجوی فاکتور بر اساس شماره فاکتور، شماره موبایل یا نام خریدار.
    هر کلمه‌ی عبارت جستجو باید در یکی از این سه فیلد پیدا شود.
    """
    cond = Q()
    for token in clean_buyer_name(latin_digits(query)).split()[:5]:
        one = Q(code__icontains=token) | Q(buyer_name__icontains=token)
        if looks_like_phone_query(token):
            digits = re.sub(r"\D", "", token)
            if digits:
                one |= Q(buyer_phone__contains=digits)
        cond &= one
    return cond
