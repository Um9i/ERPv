from django import template

register = template.Library()


@register.simple_tag
def url_replace(request, field, value):
    """Return encoded query string with given field replaced by value.

    Preserves other GET parameters; useful for pagination links.
    """
    qd = request.GET.copy()
    qd[field] = value
    return qd.urlencode()
