from django import template
from django.conf import settings

register = template.Library()


@register.filter
def currency(value):
    """Format a numeric value as currency, e.g. £1,234,567.89 or -£1,234.00"""
    try:
        value = float(value)
    except TypeError, ValueError:
        return value
    symbol = getattr(settings, "CURRENCY_SYMBOL", "£")
    if value < 0:
        return f"-{symbol}{-value:,.2f}"
    return f"{symbol}{value:,.2f}"
