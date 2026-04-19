import json
import os
import tempfile
from email.utils import parseaddr
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.http import Http404, HttpResponse, JsonResponse
from django.views.decorators.http import require_GET, require_POST
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from urllib.parse import quote, urlencode
from datetime import timedelta
import logging
import nh3
from .models import EmailAccount, Folder, CachedMessage
from .imap_client import IMAPEmailClient
from .smtp_client import SMTPEmailClient


logger = logging.getLogger(__name__)

SPECIAL_FOLDERS = {
    'inbox', 'sent', 'sent items', 'sent mail', 'drafts', 'trash',
    'deleted items', 'junk', 'junk email', 'spam', 'archive',
}

READ_FILTERS = {'all', 'unread', 'read'}
SORT_OPTIONS = {'date_desc', 'date_asc', 'from_asc', 'from_desc'}
MAX_RECIPIENTS = settings.COMPOSE_MAX_RECIPIENTS
MAX_SUBJECT_LEN = settings.COMPOSE_MAX_SUBJECT_LEN
MAX_BODY_LEN = settings.COMPOSE_MAX_BODY_LEN
MAX_ATTACHMENT_SIZE = settings.COMPOSE_MAX_ATTACHMENT_SIZE
MAX_TOTAL_ATTACHMENT_SIZE = settings.COMPOSE_MAX_TOTAL_ATTACHMENT_SIZE


def _parse_recipient_values(raw_value):
    """Parse recipient values from JSON arrays or comma-separated strings."""
    if raw_value is None:
        return []

    values = []
    if isinstance(raw_value, list):
        for item in raw_value:
            if item is None:
                continue
            values.extend(str(item).replace(';', ',').replace('\n', ',').split(','))
    else:
        values = str(raw_value).replace(';', ',').replace('\n', ',').split(',')

    return [v.strip() for v in values if v and v.strip()]


def _validate_recipients(to_values, cc_values, bcc_values):
    """Validate recipient lists and return de-duplicated all-recipient list."""
    errors = {}

    if not to_values:
        errors['to'] = ['At least one recipient is required.']

    combined = to_values + cc_values + bcc_values
    if len(combined) > MAX_RECIPIENTS:
        errors['recipients'] = [f'No more than {MAX_RECIPIENTS} recipients are allowed.']

    invalid = []
    for address in combined:
        try:
            validate_email(address)
        except ValidationError:
            invalid.append(address)

    if invalid:
        errors['recipients'] = ['One or more email addresses are invalid.']

    deduped = []
    seen = set()
    for address in combined:
        lowered = address.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        deduped.append(address)

    return errors, deduped


def _sanitize_outgoing_html(html_body):
    """Sanitize outgoing compose HTML to reduce script/tracking abuse."""
    if not html_body:
        return ''

    allowed_tags = {
        'a', 'abbr', 'b', 'blockquote', 'br', 'code', 'div', 'em', 'h1', 'h2',
        'h3', 'h4', 'h5', 'h6', 'hr', 'i', 'img', 'li', 'ol', 'p', 'pre', 'span',
        'strong', 'table', 'tbody', 'td', 'th', 'thead', 'tr', 'u', 'ul'
    }
    allowed_attributes = {
        'a': {'href', 'title'},
        'img': {'src', 'alt', 'title', 'width', 'height', 'style'},
        'td': {'colspan', 'rowspan'},
        'th': {'colspan', 'rowspan'},
    }

    return nh3.clean(
        html_body,
        tags=allowed_tags,
        attributes=allowed_attributes,
        url_schemes={'http', 'https', 'mailto'},
    )


def _parse_send_payload(request):
    """Parse and validate send payload from JSON or form data."""
    is_json = request.content_type and 'application/json' in request.content_type

    if is_json:
        try:
            payload = json.loads(request.body.decode('utf-8') or '{}')
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None, {'payload': ['Malformed JSON payload.']}

        to_values = _parse_recipient_values(payload.get('to'))
        cc_values = _parse_recipient_values(payload.get('cc'))
        bcc_values = _parse_recipient_values(payload.get('bcc'))
        subject = str(payload.get('subject') or '').strip()
        text_body = str(payload.get('text_body') or '').strip()
        html_body = str(payload.get('html_body') or '').strip()
        reply_to = str(payload.get('reply_to') or '').strip()
        in_reply_to = str(payload.get('in_reply_to') or '').strip()
        references = payload.get('references') or []
    else:
        to_values = _parse_recipient_values(request.POST.getlist('to') or request.POST.get('to'))
        cc_values = _parse_recipient_values(request.POST.getlist('cc') or request.POST.get('cc'))
        bcc_values = _parse_recipient_values(request.POST.getlist('bcc') or request.POST.get('bcc'))
        subject = (request.POST.get('subject') or '').strip()
        text_body = (request.POST.get('text_body') or '').strip()
        html_body = (request.POST.get('html_body') or '').strip()
        reply_to = (request.POST.get('reply_to') or '').strip()
        in_reply_to = (request.POST.get('in_reply_to') or '').strip()
        references = _parse_recipient_values(request.POST.get('references'))

    errors, all_recipients = _validate_recipients(to_values, cc_values, bcc_values)

    if len(subject) > MAX_SUBJECT_LEN:
        errors['subject'] = [f'Subject must be {MAX_SUBJECT_LEN} characters or fewer.']

    if len(text_body) > MAX_BODY_LEN:
        errors['text_body'] = [f'Plain text body must be {MAX_BODY_LEN} characters or fewer.']

    if len(html_body) > MAX_BODY_LEN:
        errors['html_body'] = [f'HTML body must be {MAX_BODY_LEN} characters or fewer.']

    if not text_body and not html_body:
        errors['body'] = ['Either text_body or html_body is required.']

    if reply_to:
        try:
            validate_email(reply_to)
        except ValidationError:
            errors['reply_to'] = ['reply_to must be a valid email address.']

    attachments = request.FILES.getlist('attachments')
    total_bytes = 0
    for uploaded in attachments:
        total_bytes += uploaded.size
        if uploaded.size > MAX_ATTACHMENT_SIZE:
            errors['attachments'] = [
                f'Each attachment must be {MAX_ATTACHMENT_SIZE // (1024 * 1024)}MB or smaller.'
            ]
            break
    if total_bytes > MAX_TOTAL_ATTACHMENT_SIZE:
        errors['attachments_total'] = [
            f'Total attachment size must be {MAX_TOTAL_ATTACHMENT_SIZE // (1024 * 1024)}MB or smaller.'
        ]

    if errors:
        return None, errors

    sanitized_html = _sanitize_outgoing_html(html_body)
    references_header = ''
    if isinstance(references, list):
        references_header = ' '.join([str(v).strip() for v in references if str(v).strip()])
    elif references:
        references_header = str(references).strip()

    return {
        'to': to_values,
        'cc': cc_values,
        'bcc': bcc_values,
        'all_recipients': all_recipients,
        'subject': subject,
        'text_body': text_body,
        'html_body': sanitized_html,
        'reply_to': reply_to,
        'in_reply_to': in_reply_to,
        'references': references_header,
        'attachments': attachments,
    }, None


def _persist_uploaded_attachments(attachments):
    """Persist uploaded files to temporary paths consumable by SMTP client."""
    file_paths = []
    for uploaded in attachments:
        suffix = os.path.splitext(uploaded.name or '')[1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            for chunk in uploaded.chunks():
                temp_file.write(chunk)
            file_paths.append(temp_file.name)
    return file_paths


def _cleanup_temp_files(file_paths):
    """Delete any temporary files created for outbound attachments."""
    for path in file_paths:
        try:
            os.remove(path)
        except OSError:
            logger.warning('Failed to remove temporary attachment path: %s', path)


def _build_compose_context(request, account):
    """Build compose prefill context from query parameters."""
    return {
        'to': (request.GET.get('to') or '').strip(),
        'cc': (request.GET.get('cc') or '').strip(),
        'bcc': (request.GET.get('bcc') or '').strip(),
        'subject': (request.GET.get('subject') or '').strip()[:MAX_SUBJECT_LEN],
        'text_body': (request.GET.get('text_body') or '').strip()[:MAX_BODY_LEN],
        'html_body': (request.GET.get('html_body') or '').strip()[:MAX_BODY_LEN],
        'reply_to': (request.GET.get('reply_to') or '').strip(),
        'in_reply_to': (request.GET.get('in_reply_to') or '').strip(),
        'references': (request.GET.get('references') or '').strip(),
    }


def _get_sidebar_folder_rows(account):
    """Return folder rows used by sidebar templates."""
    cache_cutoff = timezone.now() - timedelta(minutes=10)
    cached_folders = Folder.objects.filter(
        account=account,
        last_updated__gte=cache_cutoff,
        is_active=True,
    )

    if cached_folders.exists():
        folders = list(cached_folders.values_list('name', flat=True))
    else:
        folders = list(
            Folder.objects.filter(account=account, is_active=True).values_list('name', flat=True)
        )

    folders = _prioritize_primary_inbox(folders)

    unread_counts = {}
    for folder_name in folders:
        try:
            folder_obj = Folder.objects.get(account=account, name=folder_name, is_active=True)
            cached_messages = CachedMessage.objects.filter(account=account, folder=folder_obj)
            unread_count = sum(1 for msg in cached_messages if '\\Seen' not in msg.flags)
            unread_counts[folder_name] = unread_count
        except Folder.DoesNotExist:
            unread_counts[folder_name] = 0

    folders_with_counts = [
        {
            'name': name,
            'unread': unread_counts.get(name, 0),
            'is_special': _is_special_folder(name),
        }
        for name in folders
    ]

    return folders_with_counts, unread_counts


def _prefix_subject(subject, prefix):
    """Return subject with prefix unless already present."""
    base = (subject or '').strip()
    if not base:
        return prefix

    lowered = base.lower()
    if lowered.startswith('re:') or lowered.startswith('fwd:') or lowered.startswith('fw:'):
        return base
    return f'{prefix} {base}'


def _quote_plain_body(text):
    """Return text quoted with leading > markers for replies/forwards."""
    lines = (text or '').splitlines()
    if not lines:
        return ''
    quoted_lines = [f'> {line}' if line else '>' for line in lines]
    return '\n'.join(quoted_lines)


def _build_compose_action_urls(message):
    """Return reply/forward URLs for compose fragment + page fallback."""
    sender_display = (message.get('sender') or '').strip()
    reply_to_header = ''
    raw_message = message.get('raw')
    if raw_message is not None:
        reply_to_header = (raw_message.get('Reply-To') or '').strip()

    reply_to_address = parseaddr(reply_to_header)[1] if reply_to_header else parseaddr(sender_display)[1]

    message_id = ''
    references = ''
    if raw_message is not None:
        message_id = (raw_message.get('Message-ID') or '').strip()
        references = (raw_message.get('References') or '').strip()

    sender_name = sender_display or 'Unknown sender'
    sent_date = message.get('date')
    sent_label = str(sent_date) if sent_date else 'Unknown date'
    subject = (message.get('subject') or '').strip()
    text_body = (message.get('body') or '').strip()
    limited_body = text_body[:4000]

    reply_intro = f'\n\nOn {sent_label}, {sender_name} wrote:\n'
    reply_text = (reply_intro + _quote_plain_body(limited_body)).strip()

    forward_header = (
        '\n\n---------- Forwarded message ---------\n'
        f'From: {sender_name}\n'
        f'Date: {sent_label}\n'
        f'Subject: {subject}\n\n'
    )
    forward_text = (forward_header + limited_body).strip()

    reply_params = {
        'to': reply_to_address,
        'subject': _prefix_subject(subject, 'Re:'),
        'text_body': reply_text,
        'in_reply_to': message_id,
        'references': ' '.join([v for v in [references, message_id] if v]).strip(),
    }
    forward_params = {
        'subject': _prefix_subject(subject, 'Fwd:'),
        'text_body': forward_text,
    }

    reply_query = urlencode({k: v for k, v in reply_params.items() if v})
    forward_query = urlencode({k: v for k, v in forward_params.items() if v})

    return {
        'reply_fragment_url': f"{reverse('compose_fragment')}?{reply_query}" if reply_query else reverse('compose_fragment'),
        'reply_page_url': f"{reverse('compose_page')}?{reply_query}" if reply_query else reverse('compose_page'),
        'forward_fragment_url': f"{reverse('compose_fragment')}?{forward_query}" if forward_query else reverse('compose_fragment'),
        'forward_page_url': f"{reverse('compose_page')}?{forward_query}" if forward_query else reverse('compose_page'),
    }


def _is_special_folder(name):
    normalized = name.strip().lower()
    if normalized in SPECIAL_FOLDERS:
        return True
    # Sub-folder hierarchy variants: INBOX.Spam (Dovecot) or INBOX/Spam (Gmail, Courier, etc.)
    for sep in ('.', '/'):
        prefix = 'inbox' + sep
        if normalized.startswith(prefix):
            suffix = normalized[len(prefix):]
            if suffix in SPECIAL_FOLDERS:
                return True
    return False


def _prioritize_primary_inbox(folders):
    """Return folders with the primary INBOX entry pinned to the top."""
    inbox_names = [f for f in folders if str(f).strip().lower() == 'inbox']
    other_names = [f for f in folders if str(f).strip().lower() != 'inbox']
    return inbox_names + other_names


def _normalize_list_options(request):
    """Normalize read filter + sort options from query params."""
    read_filter = request.GET.get('read', 'all')
    sort_by = request.GET.get('sort', 'date_desc')
    if read_filter not in READ_FILTERS:
        read_filter = 'all'
    if sort_by not in SORT_OPTIONS:
        sort_by = 'date_desc'
    return read_filter, sort_by


def _apply_list_options(messages, read_filter, sort_by):
    """Apply read/unread filtering and sender/date sorting to message list."""
    filtered = messages
    if read_filter == 'unread':
        filtered = [m for m in filtered if '\\Seen' not in (m.get('flags') or [])]
    elif read_filter == 'read':
        filtered = [m for m in filtered if '\\Seen' in (m.get('flags') or [])]

    if sort_by in ('from_asc', 'from_desc'):
        reverse = sort_by == 'from_desc'

        def sender_key(message):
            sender = (message.get('sender_name') or message.get('sender') or '').strip().lower()
            return sender

        filtered = sorted(filtered, key=sender_key, reverse=reverse)
    else:
        reverse = sort_by == 'date_desc'

        def date_key(message):
            # Keep missing dates stable and sorted last.
            dt = message.get('date')
            if dt is None:
                return (1, 0.0)
            return (0, dt.timestamp())

        filtered = sorted(filtered, key=date_key, reverse=reverse)

    return filtered


def _mark_cached_seen(account, folder_name, uid):
    """Ensure the cached message flags include \\Seen after opening a message."""
    try:
        cached = CachedMessage.objects.get(
            account=account,
            folder__name=folder_name,
            uid=str(uid),
        )
    except CachedMessage.DoesNotExist:
        return

    flags = list(cached.flags or [])
    if '\\Seen' not in flags:
        flags.append('\\Seen')
        cached.flags = flags
        cached.save(update_fields=['flags'])


def _render_user_error(request, user_message, *, log_message=None):
    """Render a generic, user-safe error message and log internal details."""
    if log_message:
        logger.exception(log_message)
    return render(request, 'mail/error.html', {'error': user_message})


@login_required
def inbox(request, folder_name='INBOX'):
    """Display inbox with folders and messages."""
    
    # Get the first email account (for now, single account support)
    account = EmailAccount.objects.first()
    
    if not account:
        return render(request, 'mail/no_account.html', {
            'message': 'No email account configured. Please add one in the admin.'
        })
    
    current_folder = folder_name or 'INBOX'
    force_refresh = request.GET.get('refresh') == '1'
    search_query = request.GET.get('q', '').strip()[:200]
    search_in = request.GET.get('search_in', 'headers')
    read_filter, sort_by = _normalize_list_options(request)
    if search_in not in ('headers', 'text'):
        search_in = 'headers'

    # Try to get cached folders first (10 minute cache)
    cache_cutoff = timezone.now() - timedelta(minutes=10)
    cached_folders = Folder.objects.filter(
        account=account,
        last_updated__gte=cache_cutoff,
        is_active=True
    )
    
    if cached_folders.exists():
        # Use cached folders
        folders = list(cached_folders.values_list('name', flat=True))
    else:
        # Cache miss - fetch from server and update cache
        try:
            with IMAPEmailClient(
                account.imap_host,
                account.imap_username,
                account.imap_password_decrypted,
                port=account.imap_port
            ) as client:
                folders = client.sync_folders_cache(account, Folder)
        except Exception as e:
            # Fallback to stale cache if server is down
            folders = list(Folder.objects.filter(
                account=account, 
                is_active=True
            ).values_list('name', flat=True))

    folders = _prioritize_primary_inbox(folders)
    
    # Get current folder object
    try:
        folder_obj = Folder.objects.get(account=account, name=current_folder, is_active=True)
    except Folder.DoesNotExist:
        # Folder not in cache, try to refresh cache
        try:
            with IMAPEmailClient(
                account.imap_host,
                account.imap_username,
                account.imap_password_decrypted,
                port=account.imap_port
            ) as client:
                folders = client.sync_folders_cache(account, Folder)
                folders = _prioritize_primary_inbox(folders)
                folder_obj = Folder.objects.get(account=account, name=current_folder, is_active=True)
        except (Folder.DoesNotExist, Exception):
            raise Http404(f"Folder '{current_folder}' not found")
    
    is_search = bool(search_query)

    if is_search:
        # Live IMAP search — bypass message cache
        try:
            with IMAPEmailClient(
                account.imap_host,
                account.imap_username,
                account.imap_password_decrypted,
                port=account.imap_port,
            ) as client:
                messages = client.search_messages(current_folder, search_query, search_in)
        except Exception:
            return _render_user_error(
                request,
                'Search failed. Please try again in a moment.',
                log_message='IMAP search failed.',
            )
    else:
        # Try to get cached messages first (5 minute cache for message headers)
        msg_cache_cutoff = timezone.now() - timedelta(minutes=5)
        cached_messages = CachedMessage.objects.filter(
            account=account,
            folder=folder_obj,
            last_updated__gte=msg_cache_cutoff
        ).order_by('-date')[:50]  # Limit to 50 most recent

        if cached_messages.exists() and not force_refresh:
            # Use cached message headers
            messages = []
            for cached_msg in cached_messages:
                messages.append({
                    'uid': cached_msg.uid,
                    'subject': cached_msg.subject,
                    'sender': cached_msg.sender,
                    'sender_name': cached_msg.sender_name,
                    'date': cached_msg.date,
                    'flags': cached_msg.flags,
                    'size': cached_msg.size,
                    'has_attachments': cached_msg.has_attachments,
                })
        else:
            # Cache miss - fetch from server and update cache
            try:
                with IMAPEmailClient(
                    account.imap_host,
                    account.imap_username,
                    account.imap_password_decrypted,
                    port=account.imap_port
                ) as client:
                    # Sync message cache
                    client.sync_messages_cache(account, folder_obj, CachedMessage, limit=50)

                    # Now get the cached messages
                    cached_messages = CachedMessage.objects.filter(
                        account=account,
                        folder=folder_obj
                    ).order_by('-date')[:50]

                    messages = []
                    for cached_msg in cached_messages:
                        messages.append({
                            'uid': cached_msg.uid,
                            'subject': cached_msg.subject,
                            'sender': cached_msg.sender,
                            'sender_name': cached_msg.sender_name,
                            'date': cached_msg.date,
                            'flags': cached_msg.flags,
                            'size': cached_msg.size,
                            'has_attachments': cached_msg.has_attachments,
                        })
            except Exception as e:
                # Fallback to direct IMAP fetch if caching fails
                try:
                    with IMAPEmailClient(
                        account.imap_host,
                        account.imap_username,
                        account.imap_password_decrypted,
                        port=account.imap_port
                    ) as client:
                        messages = client.fetch_emails(current_folder, limit=50)
                except Exception:
                    return _render_user_error(
                        request,
                        'Failed to fetch messages. Please try again later.',
                        log_message='Failed to fetch messages from IMAP after cache fallback.',
                    )

    messages = _apply_list_options(messages, read_filter, sort_by)
    
    # Calculate unread message counts for each folder
    unread_counts = {}
    for folder_name in folders:
        try:
            folder_obj = Folder.objects.get(account=account, name=folder_name, is_active=True)
            # Get all cached messages for this folder and count unread in Python
            # (SQLite doesn't support contains lookup on JSON fields)
            # In IMAP, messages are unread if they DON'T have the \\Seen flag
            cached_messages = CachedMessage.objects.filter(
                account=account,
                folder=folder_obj
            )
            unread_count = sum(1 for msg in cached_messages if '\\Seen' not in msg.flags)
            unread_counts[folder_name] = unread_count
        except Folder.DoesNotExist:
            unread_counts[folder_name] = 0
    
    # Build folders_with_counts for template iteration
    folders_with_counts = [
        {'name': f, 'unread': unread_counts.get(f, 0), 'is_special': _is_special_folder(f)}
        for f in folders
    ]
    
    context = {
        'account': account,
        'folders': folders,
        'folders_with_counts': folders_with_counts,
        'messages': messages,
        'current_folder': current_folder,
        'unread_counts': unread_counts,
        'search_query': search_query,
        'search_in': search_in,
        'is_search': is_search,
        'read_filter': read_filter,
        'sort_by': sort_by,
    }

    return render(request, 'mail/inbox.html', context)


@login_required
def message_detail(request, uid):
    """Display the selected email message."""
    account = EmailAccount.objects.first()

    if not account:
        return render(request, 'mail/no_account.html', {
            'message': 'No email account configured. Please add one in the admin.'
        })

    selected_folder = request.GET.get('folder', 'INBOX')
    load_remote_images = request.GET.get('load_remote') == '1'
    
    # Try to get cached folders first (10 minute cache)
    cache_cutoff = timezone.now() - timedelta(minutes=10)
    cached_folders = Folder.objects.filter(
        account=account,
        last_updated__gte=cache_cutoff,
        is_active=True
    )
    
    if cached_folders.exists():
        # Use cached folders
        folders = list(cached_folders.values_list('name', flat=True))
    else:
        # Cache miss - fetch from server and update cache
        try:
            with IMAPEmailClient(
                account.imap_host,
                account.imap_username,
                account.imap_password_decrypted,
                port=account.imap_port
            ) as client:
                folders = client.sync_folders_cache(account, Folder)
        except Exception as e:
            # Fallback to stale cache if server is down
            folders = list(Folder.objects.filter(
                account=account, 
                is_active=True
            ).values_list('name', flat=True))

    folders = _prioritize_primary_inbox(folders)
    
    # Fetch full message (bodies are not cached, only headers)
    message = None
    try:
        with IMAPEmailClient(
            account.imap_host,
            account.imap_username,
            account.imap_password_decrypted,
            port=account.imap_port
        ) as client:
            message = client.fetch_email_by_uid(
                uid,
                folder=selected_folder,
                allow_remote_images=load_remote_images,
            )
            if message:
                try:
                    client.set_flag(uid, selected_folder, '\\Seen', add=True)
                except Exception:
                    pass

    except Exception:
        return _render_user_error(
            request,
            'Failed to load message. Please try again.',
            log_message='Failed to load message detail from IMAP.',
        )

    if not message:
        raise Http404('Message not found')

    _mark_cached_seen(account, selected_folder, uid)

    # Calculate unread message counts for each folder
    unread_counts = {}
    for folder_name in folders:
        try:
            folder_obj = Folder.objects.get(account=account, name=folder_name, is_active=True)
            # Get all cached messages for this folder and count unread in Python
            # (SQLite doesn't support contains lookup on JSON fields)
            # In IMAP, messages are unread if they DON'T have the \Seen flag
            cached_messages = CachedMessage.objects.filter(
                account=account,
                folder=folder_obj
            )
            unread_count = sum(1 for msg in cached_messages if '\\Seen' not in msg.flags)
            unread_counts[folder_name] = unread_count
        except Folder.DoesNotExist:
            unread_counts[folder_name] = 0
    
    # Build folders_with_counts for template iteration
    folders_with_counts = [
        {'name': f, 'unread': unread_counts.get(f, 0), 'is_special': _is_special_folder(f)}
        for f in folders
    ]
    
    compose_actions = _build_compose_action_urls(message)

    return render(request, 'mail/message_detail.html', {
        'account': account,
        'message': message,
        'current_folder': selected_folder,
        'load_remote_images': load_remote_images,
        'folders': folders,
        'folders_with_counts': folders_with_counts,
        'unread_counts': unread_counts,
        'reply_fragment_url': compose_actions['reply_fragment_url'],
        'reply_page_url': compose_actions['reply_page_url'],
        'forward_fragment_url': compose_actions['forward_fragment_url'],
        'forward_page_url': compose_actions['forward_page_url'],
    })


@login_required
@require_GET
def message_detail_fragment(request, uid):
    """Returns message detail as an HTML fragment for the inbox split pane."""
    account = EmailAccount.objects.first()
    if not account:
        return HttpResponse(
            '<p class="text-muted p-4">No email account configured.</p>',
            status=400,
            content_type='text/html',
        )

    selected_folder = request.GET.get('folder', 'INBOX')
    load_remote_images = request.GET.get('load_remote') == '1'

    try:
        with IMAPEmailClient(
            account.imap_host,
            account.imap_username,
            account.imap_password_decrypted,
            port=account.imap_port,
        ) as client:
            message = client.fetch_email_by_uid(
                uid,
                folder=selected_folder,
                allow_remote_images=load_remote_images,
            )
            if message:
                try:
                    client.set_flag(uid, selected_folder, '\\Seen', add=True)
                except Exception:
                    pass
    except Exception:
        return HttpResponse(
            '<p class="text-muted p-4">Failed to load message.</p>',
            status=500,
            content_type='text/html',
        )

    if not message:
        return HttpResponse(
            '<p class="text-muted p-4">Message not found.</p>',
            status=404,
            content_type='text/html',
        )

    _mark_cached_seen(account, selected_folder, uid)

    # Build folders_with_counts for the Move dropdown in the action toolbar.
    cache_cutoff = timezone.now() - timedelta(minutes=10)
    folders = list(
        Folder.objects.filter(
            account=account,
            last_updated__gte=cache_cutoff,
            is_active=True,
        ).values_list('name', flat=True)
    ) or list(
        Folder.objects.filter(account=account, is_active=True).values_list('name', flat=True)
    )
    folders = _prioritize_primary_inbox(folders)
    folders_with_counts = [
        {'name': f, 'unread': 0, 'is_special': _is_special_folder(f)}
        for f in folders
    ]

    compose_actions = _build_compose_action_urls(message)

    return render(request, 'mail/partials/message_detail_body.html', {
        'message': message,
        'current_folder': selected_folder,
        'load_remote_images': load_remote_images,
        'folders_with_counts': folders_with_counts,
        'reply_fragment_url': compose_actions['reply_fragment_url'],
        'reply_page_url': compose_actions['reply_page_url'],
        'forward_fragment_url': compose_actions['forward_fragment_url'],
        'forward_page_url': compose_actions['forward_page_url'],
    })

VIRTUAL_STARRED = '__starred__'


@login_required
def starred_inbox(request):
    """Virtual folder showing all flagged/starred messages across all folders."""
    account = EmailAccount.objects.first()
    if not account:
        return render(request, 'mail/no_account.html', {
            'message': 'No email account configured. Please add one in the admin.'
        })

    read_filter, sort_by = _normalize_list_options(request)

    # Collect all cached flagged messages across every folder.
    flagged_cached = CachedMessage.objects.filter(
        account=account,
    ).select_related('folder').order_by('-date')[:200]

    messages = []
    for cached_msg in flagged_cached:
        if '\\Flagged' not in cached_msg.flags:
            continue
        messages.append({
            'uid': cached_msg.uid,
            'subject': cached_msg.subject,
            'sender': cached_msg.sender,
            'sender_name': cached_msg.sender_name,
            'date': cached_msg.date,
            'flags': cached_msg.flags,
            'size': cached_msg.size,
            'has_attachments': cached_msg.has_attachments,
            'message_folder': cached_msg.folder.name,
        })

    messages = _apply_list_options(messages, read_filter, sort_by)

    # Folder list for sidebar.
    cache_cutoff = timezone.now() - timedelta(minutes=10)
    cached_folders = Folder.objects.filter(
        account=account, last_updated__gte=cache_cutoff, is_active=True
    )
    folders = list(
        cached_folders.values_list('name', flat=True)
    ) or list(
        Folder.objects.filter(account=account, is_active=True).values_list('name', flat=True)
    )
    folders = _prioritize_primary_inbox(folders)

    unread_counts = {}
    for folder_name in folders:
        try:
            folder_obj = Folder.objects.get(account=account, name=folder_name, is_active=True)
            cached = CachedMessage.objects.filter(account=account, folder=folder_obj)
            unread_counts[folder_name] = sum(1 for m in cached if '\\Seen' not in m.flags)
        except Folder.DoesNotExist:
            unread_counts[folder_name] = 0

    folders_with_counts = [
        {'name': f, 'unread': unread_counts.get(f, 0), 'is_special': _is_special_folder(f)}
        for f in folders
    ]

    return render(request, 'mail/inbox.html', {
        'account': account,
        'folders': folders,
        'folders_with_counts': folders_with_counts,
        'messages': messages,
        'current_folder': VIRTUAL_STARRED,
        'unread_counts': unread_counts,
        'search_query': '',
        'search_in': 'headers',
        'is_search': False,
        'read_filter': read_filter,
        'sort_by': sort_by,
    })


def _folder_redirect(folder_name):
    """Redirect to the appropriate inbox URL for a folder."""
    if folder_name == 'INBOX':
        return redirect('inbox')
    return redirect('folder_inbox', folder_name=folder_name)


@login_required
@require_POST
def message_delete(request, uid):
    """Move message to Trash (or expunge if already in Trash)."""
    account = EmailAccount.objects.first()
    if not account:
        return redirect('inbox')
    folder = request.POST.get('folder', 'INBOX').strip()
    try:
        with IMAPEmailClient(
            account.imap_host, account.imap_username, account.imap_password_decrypted,
            port=account.imap_port,
        ) as client:
            client.delete_message(uid, folder)
    except Exception:
        pass
    CachedMessage.objects.filter(
        account=account, folder__name=folder, uid=str(uid)
    ).delete()
    if request.POST.get('next') == 'pane':
        return HttpResponse(status=204)
    return _folder_redirect(folder)


@login_required
@require_POST
def message_archive(request, uid):
    """Move message to Archive folder."""
    account = EmailAccount.objects.first()
    if not account:
        return redirect('inbox')
    folder = request.POST.get('folder', 'INBOX').strip()
    try:
        with IMAPEmailClient(
            account.imap_host, account.imap_username, account.imap_password_decrypted,
            port=account.imap_port,
        ) as client:
            client.archive_message(uid, folder)
            # Ensure Archive folder is in our cache.
            client.sync_folders_cache(account, Folder)
    except Exception:
        pass
    CachedMessage.objects.filter(
        account=account, folder__name=folder, uid=str(uid)
    ).delete()
    if request.POST.get('next') == 'pane':
        return HttpResponse(status=204)
    return _folder_redirect(folder)


@login_required
@require_POST
def message_move(request, uid):
    """Move message to a different folder."""
    account = EmailAccount.objects.first()
    if not account:
        return redirect('inbox')
    folder = request.POST.get('folder', 'INBOX').strip()
    to_folder = request.POST.get('to_folder', '').strip()
    if not to_folder:
        if request.POST.get('next') == 'pane':
            return HttpResponse(status=204)
        return _folder_redirect(folder)
    try:
        with IMAPEmailClient(
            account.imap_host, account.imap_username, account.imap_password_decrypted,
            port=account.imap_port,
        ) as client:
            client.move_message(uid, folder, to_folder)
    except Exception:
        pass
    CachedMessage.objects.filter(
        account=account, folder__name=folder, uid=str(uid)
    ).delete()
    if request.POST.get('next') == 'pane':
        return HttpResponse(status=204)
    return _folder_redirect(folder)


@login_required
@require_POST
def message_mark_unread(request, uid):
    """Remove the \\Seen flag from a message."""
    account = EmailAccount.objects.first()
    if not account:
        return redirect('inbox')
    folder = request.POST.get('folder', 'INBOX').strip()
    try:
        with IMAPEmailClient(
            account.imap_host, account.imap_username, account.imap_password_decrypted,
            port=account.imap_port,
        ) as client:
            client.set_flag(uid, folder, '\\Seen', add=False)
    except Exception:
        pass
    # Patch the cached flags so the unread badge updates immediately.
    try:
        cached = CachedMessage.objects.get(
            account=account, folder__name=folder, uid=str(uid)
        )
        flags = [f for f in (cached.flags or []) if f != '\\Seen']
        cached.flags = flags
        cached.save(update_fields=['flags'])
    except CachedMessage.DoesNotExist:
        pass
    if request.POST.get('next') == 'mark-unread':
        return JsonResponse({'marked_unread': True})
    if request.POST.get('next') == 'fragment':
        url = reverse('message_detail_fragment', args=[uid]) + f'?folder={quote(folder, safe="")}'
        return redirect(url)
    return _folder_redirect(folder)


@login_required
@require_POST
def message_flag(request, uid):
    """Toggle the \\Flagged flag on a message."""
    account = EmailAccount.objects.first()
    if not account:
        return redirect('inbox')
    folder = request.POST.get('folder', 'INBOX').strip()
    add_flag = request.POST.get('flagged') == '1'
    try:
        with IMAPEmailClient(
            account.imap_host, account.imap_username, account.imap_password_decrypted,
            port=account.imap_port,
        ) as client:
            client.set_flag(uid, folder, '\\Flagged', add=add_flag)
    except Exception:
        pass
    # Patch the cached flags.
    try:
        cached = CachedMessage.objects.get(
            account=account, folder__name=folder, uid=str(uid)
        )
        flags = [f for f in (cached.flags or []) if f != '\\Flagged']
        if add_flag:
            flags.append('\\Flagged')
        cached.flags = flags
        cached.save(update_fields=['flags'])
    except CachedMessage.DoesNotExist:
        pass
    if request.POST.get('next') == 'toggle':
        return JsonResponse({'flagged': add_flag})
    if request.POST.get('next') == 'fragment':
        url = reverse('message_detail_fragment', args=[uid]) + f'?folder={quote(folder, safe="")}'
        return redirect(url)
    if request.POST.get('next') == 'detail':
        url = reverse('message_detail', args=[uid]) + f'?folder={quote(folder, safe="")}'
        return redirect(url)
    return _folder_redirect(folder)


@login_required
@require_POST
def create_folder(request):
    """Create a new IMAP folder."""
    account = EmailAccount.objects.first()
    if not account:
        return redirect('inbox')
    folder_name = request.POST.get('folder_name', '').strip()
    if not folder_name or _is_special_folder(folder_name):
        return redirect('inbox')
    try:
        with IMAPEmailClient(
            account.imap_host,
            account.imap_username,
            account.imap_password_decrypted,
            port=account.imap_port,
        ) as client:
            client.create_folder(folder_name)
            client.sync_folders_cache(account, Folder)
    except Exception:
        pass
    return redirect('folder_inbox', folder_name=folder_name)


@login_required
@require_POST
def delete_folder(request):
    """Delete an IMAP folder."""
    account = EmailAccount.objects.first()
    if not account:
        return redirect('inbox')
    folder_name = request.POST.get('folder_name', '').strip()
    if not folder_name or _is_special_folder(folder_name):
        return redirect('inbox')
    try:
        with IMAPEmailClient(
            account.imap_host,
            account.imap_username,
            account.imap_password_decrypted,
            port=account.imap_port,
        ) as client:
            client.delete_folder(folder_name)
        Folder.objects.filter(account=account, name=folder_name).delete()
    except Exception:
        pass
    return redirect('inbox')


@login_required
@require_GET
def check_new_messages(request):
    """AJAX endpoint to check for new messages in current folder."""
    account = EmailAccount.objects.first()
    if not account:
        return JsonResponse({'error': 'No account configured'}, status=400)
    
    folder_name = request.GET.get('folder', 'INBOX')
    
    try:
        # Get current cached message count
        folder_obj = Folder.objects.get(account=account, name=folder_name, is_active=True)
        cached_count = CachedMessage.objects.filter(
            account=account,
            folder=folder_obj
        ).count()
        
        # Quick IMAP check for actual count
        with IMAPEmailClient(
            account.imap_host,
            account.imap_username,
            account.imap_password_decrypted,
            port=account.imap_port
        ) as client:
            client.client.select_folder(folder_name)
            actual_count = len(client.client.search('ALL'))
        
        return JsonResponse({
            'cached_count': cached_count,
            'actual_count': actual_count,
            'has_new': actual_count > cached_count
        })
        
    except Exception:
        logger.exception('Failed to check new messages for folder: %s', folder_name)
        return JsonResponse({'error': 'Unable to check for new messages right now.'}, status=500)


@login_required
@require_GET
def compose_fragment(request):
    """Render compose form fragment for split-pane usage."""
    account = EmailAccount.objects.first()
    if not account:
        return render(request, 'mail/partials/compose_fragment.html', {
            'compose_error': 'No email account configured. Please add one in the admin.',
            'account': None,
            'compose': {},
            'mobile_fallback': False,
        })

    compose = _build_compose_context(request, account)

    return render(request, 'mail/partials/compose_fragment.html', {
        'account': account,
        'compose': compose,
        'compose_error': '',
        'mobile_fallback': False,
    })


@login_required
@require_GET
def compose_page(request):
    """Render full compose page (mobile fallback and direct navigation)."""
    account = EmailAccount.objects.first()
    if not account:
        return render(request, 'mail/no_account.html', {
            'message': 'No email account configured. Please add one in the admin.'
        })

    folders_with_counts, unread_counts = _get_sidebar_folder_rows(account)

    return render(request, 'mail/compose.html', {
        'account': account,
        'current_folder': 'INBOX',
        'folders_with_counts': folders_with_counts,
        'unread_counts': unread_counts,
        'compose': _build_compose_context(request, account),
        'compose_error': '',
        'mobile_fallback': True,
    })


@login_required
@require_POST
def send_message_api(request):
    """Send an outbound email through configured SMTP account settings."""
    account = EmailAccount.objects.first()
    if not account:
        return JsonResponse(
            {'ok': False, 'errors': {'account': ['No email account configured.']}},
            status=400,
        )

    missing_config = []
    if not account.smtp_host:
        missing_config.append('smtp_host')
    if not account.smtp_username:
        missing_config.append('smtp_username')
    if not account.smtp_password_encrypted:
        missing_config.append('smtp_password_encrypted')

    if missing_config:
        return JsonResponse(
            {
                'ok': False,
                'errors': {
                    'smtp': ['SMTP account settings are incomplete. Configure SMTP before sending.']
                },
            },
            status=422,
        )

    payload, errors = _parse_send_payload(request)
    if errors:
        return JsonResponse({'ok': False, 'errors': errors}, status=400)
    if payload is None:
        return JsonResponse({'ok': False, 'errors': {'payload': ['Invalid send payload.']}}, status=400)

    temp_paths = []
    try:
        temp_paths = _persist_uploaded_attachments(payload['attachments'])

        smtp_port = int(account.smtp_port or 587)
        use_tls = smtp_port != 465
        client = SMTPEmailClient(
            account.smtp_host,
            account.smtp_username,
            account.smtp_password_decrypted,
            port=smtp_port,
            use_tls=use_tls,
        )
        client.connect()
        try:
            client.send_email(
                to_address=payload['to'],
                cc_addresses=payload['cc'],
                bcc_addresses=payload['bcc'],
                subject=payload['subject'],
                body=payload['text_body'],
                html_body=payload['html_body'],
                attachments=temp_paths,
                reply_to=payload['reply_to'],
                in_reply_to=payload['in_reply_to'],
                references=payload['references'],
            )
        finally:
            client.disconnect()
    except ConnectionError:
        logger.exception('SMTP connection failure while sending message.')
        return JsonResponse(
            {'ok': False, 'errors': {'smtp': ['Unable to connect to SMTP server right now.']}},
            status=502,
        )
    except RuntimeError:
        logger.exception('SMTP send failure.')
        return JsonResponse(
            {'ok': False, 'errors': {'send': ['Unable to send email right now. Please try again.']}},
            status=502,
        )
    except Exception:
        logger.exception('Unexpected send_message_api failure.')
        return JsonResponse(
            {'ok': False, 'errors': {'send': ['Unexpected error while sending email.']}},
            status=500,
        )
    finally:
        _cleanup_temp_files(temp_paths)

    return JsonResponse({'ok': True, 'message': 'Email sent successfully.'}, status=200)


@login_required
def inline_image(request, uid, part_index):
    """Serve inline CID image bytes for a specific message MIME part."""
    account = EmailAccount.objects.first()
    if not account:
        raise Http404('No email account configured')

    selected_folder = request.GET.get('folder', 'INBOX')

    try:
        with IMAPEmailClient(
            account.imap_host,
            account.imap_username,
            account.imap_password_decrypted,
            port=account.imap_port
        ) as client:
            client.client.select_folder(selected_folder)
            response = client.client.fetch([uid], ['RFC822'])
            if uid not in response:
                raise Http404('Message not found')

            email_obj = client._parse_email(response[uid][b'RFC822'])
            parts = list(email_obj.walk())

            if part_index < 0 or part_index >= len(parts):
                raise Http404('Inline image part not found')

            part = parts[part_index]
            content_type = part.get_content_type().lower()
            disposition = (part.get_content_disposition() or '').lower()

            if not content_type.startswith('image/'):
                raise Http404('Requested part is not an image')

            # Inline images generally have Content-ID and are not attachments.
            if disposition == 'attachment' or not part.get('Content-ID'):
                raise Http404('Requested image is not an inline CID part')

            payload = part.get_payload(decode=True)
            if payload is None:
                raise Http404('Inline image data not available')

            response_obj = HttpResponse(payload, content_type=content_type)
            response_obj['Cache-Control'] = 'private, max-age=300'
            response_obj['X-Content-Type-Options'] = 'nosniff'
            return response_obj

    except Http404:
        raise
    except Exception:
        logger.exception('Failed to load inline image. uid=%s, folder=%s, part_index=%s', uid, selected_folder, part_index)
        raise Http404('Inline image is unavailable')


@login_required
def download_attachment(request, uid, part_index):
    """Serve non-inline attachment bytes for download."""
    account = EmailAccount.objects.first()
    if not account:
        raise Http404('No email account configured')

    selected_folder = request.GET.get('folder', 'INBOX')

    try:
        with IMAPEmailClient(
            account.imap_host,
            account.imap_username,
            account.imap_password_decrypted,
            port=account.imap_port
        ) as client:
            client.client.select_folder(selected_folder)
            response = client.client.fetch([uid], ['RFC822'])
            if uid not in response:
                raise Http404('Message not found')

            email_obj = client._parse_email(response[uid][b'RFC822'])
            parts = list(email_obj.walk())

            if part_index < 0 or part_index >= len(parts):
                raise Http404('Attachment part not found')

            part = parts[part_index]
            if part.is_multipart():
                raise Http404('Requested part is not a downloadable attachment')

            disposition = (part.get_content_disposition() or '').lower()
            filename = part.get_filename()
            content_id = (part.get('Content-ID') or '').strip()

            is_inline_cid = bool(content_id) and disposition != 'attachment'
            is_attachment = disposition == 'attachment' or (filename and not is_inline_cid)
            if not is_attachment:
                raise Http404('Requested part is not a non-inline attachment')

            payload = part.get_payload(decode=True)
            if payload is None:
                raise Http404('Attachment data not available')

            content_type = part.get_content_type().lower()
            safe_name = filename or f'attachment-{part_index}'

            response_obj = HttpResponse(payload, content_type=content_type)
            response_obj['Content-Disposition'] = f'attachment; filename="{safe_name}"'
            response_obj['Cache-Control'] = 'private, max-age=300'
            response_obj['X-Content-Type-Options'] = 'nosniff'
            return response_obj

    except Http404:
        raise
    except Exception:
        logger.exception('Failed to load attachment. uid=%s, folder=%s, part_index=%s', uid, selected_folder, part_index)
        raise Http404('Attachment is unavailable')
