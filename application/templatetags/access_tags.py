from django import template

from .. import permissions

register = template.Library()


@register.filter
def has_role(user, level):
    """{% if request.user|has_role:"keeper" %} ... {% endif %}"""
    return permissions.has_role(user, level)


@register.filter
def role_label(user):
    return permissions.LABELS.get(permissions.get_role(user), "")
