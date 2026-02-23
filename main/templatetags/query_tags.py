from urllib.parse import urlencode

from django import template

register = template.Library()


@register.simple_tag
def url_replace(request, field, value):
    """Return a query string with *field* set to *value*.

    The tag preserves other GET parameters and transparently replaces any
    existing value for the given field.  It is useful when rendering
    pagination links, since the view may already have additional query
    parameters (e.g. search keywords or different page names).

    Usage in template:

        {% load query_tags %}
        <a href="?{% url_replace request 'page' page_obj.next_page_number %}">Next</a>

    """
    querydict = request.GET.copy()
    querydict[field] = value
    return querydict.urlencode()
