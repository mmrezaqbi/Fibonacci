from decimal import Decimal, InvalidOperation

from django import forms

_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


class MoneyInput(forms.TextInput):
    """
    فیلد مبلغ با جداکننده‌ی سه‌رقمی (1,250,000). جاوااسکریپت صفحه‌ی اصلی هنگام تایپ جداکننده را می‌گذارد؛
    سرور هم جداکننده‌ها و ارقام فارسی را پیش از اعتبارسنجی حذف می‌کند، پس بدون JS هم درست کار می‌کند.
    """

    def __init__(self, attrs=None):
        base = {"data-money": "1", "inputmode": "numeric", "dir": "ltr", "autocomplete": "off"}
        base.update(attrs or {})
        super().__init__(base)

    def format_value(self, value):
        if value is None or value == "":
            return None
        try:
            return f"{int(Decimal(str(value))):,}"
        except (InvalidOperation, ValueError):
            return super().format_value(value)

    def value_from_datadict(self, data, files, name):
        raw = data.get(name)
        if raw is None:
            return None
        text = str(raw).translate(_DIGITS)
        for ch in (",", "،", "٬", " "):
            text = text.replace(ch, "")
        return text
