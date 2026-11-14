from django import template

register = template.Library()

# هر صفحه‌ی زیرمجموعه (ویرایش، جزئیات، ...) باید آیتم منوی اصلی خودش را فعال نگه دارد.
_EXACT = {
    "home": "home",
    "product_list": "products", "product_detail": "products",
    "product_create": "product_create",
    "invoice_in": "invoice_in", "invoice_out": "invoice_out",
    "stock_in": "stock_in", "stock_out": "stock_out",
    "category_list": "categories", "category_edit": "categories", "category_delete": "categories",
    "warehouse_list": "warehouses", "warehouse_detail": "warehouses",
    "reports": "reports", "invoice_detail": "reports",
    "settings_index": "settings", "store_settings": "settings", "woo_settings": "settings",
    "warehouse_settings": "settings", "warehouse_edit": "settings", "warehouse_delete": "settings",
}
_PREFIX = (
    ("report_", "reports"),
    ("color_", "settings"), ("size_", "settings"), ("user_", "settings"),
    ("product_manage_", "settings"), ("settings_", "settings"),
)


def section_for(url_name):
    url_name = url_name or ""
    if url_name in _EXACT:
        return _EXACT[url_name]
    for prefix, section in _PREFIX:
        if url_name.startswith(prefix):
            return section
    return ""


@register.simple_tag(takes_context=True)
def nav_section(context):
    """{% nav_section as section %} -> نام بخش فعال منوی کناری."""
    match = getattr(context.get("request"), "resolver_match", None)
    return section_for(getattr(match, "url_name", ""))
