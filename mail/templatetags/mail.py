from django import template

register = template.Library()

_FOLDER_ICONS = {
    'inbox': '📥',
    'sent': '📤',
    'drafts': '✏️',
    'draft': '✏️',
    'trash': '🗑️',
    'deleted': '🗑️',
    'junk': '🚫',
    'spam': '🚫',
    'archive': '📦',
    'archives': '📦',
    'starred': '⭐',
    'flagged': '⭐',
}


@register.filter
def folder_icon(folder_name):
    """Return an emoji icon for well-known IMAP folder names."""
    return _FOLDER_ICONS.get(str(folder_name).lower(), '📁')


@register.filter
def get_item(dictionary, key):
    """Get item from dictionary by key - for use in templates."""
    if isinstance(dictionary, dict):
        return dictionary.get(key, 0)
    return 0


@register.filter
def has_imap_flag(flags, flag_name):
    """
    Check whether an IMAP flag is present in a flags list.
    Pass the flag name WITHOUT the leading backslash, e.g. "Flagged" or "Seen".
    Usage: {{ message.flags|has_imap_flag:"Flagged" }}
    """
    if not flags:
        return False
    return f'\\{flag_name}' in flags
