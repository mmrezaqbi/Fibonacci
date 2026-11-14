"""نمایش مبلغ با جداکننده‌ی سه‌رقمی:  {{ price|money }}  →  1,250,000"""
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter
def money(value):
    if value is None or value == "":
        return ""
    try:
        number = int(Decimal(str(value)).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError, TypeError):
        return value
    return f"{number:,}"
