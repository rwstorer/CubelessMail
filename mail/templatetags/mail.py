from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """Get item from dictionary by key - for use in templates."""
    if isinstance(dictionary, dict):
        return dictionary.get(key, 0)
    return 0
