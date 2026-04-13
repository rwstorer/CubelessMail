from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.utils import timezone
from datetime import timedelta
from .models import EmailAccount, Folder, CachedMessage
from .imap_client import IMAPEmailClient


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
                account.imap_password,
                port=account.imap_port
            ) as client:
                folders = client.sync_folders_cache(account, Folder)
        except Exception as e:
            # Fallback to stale cache if server is down
            folders = list(Folder.objects.filter(
                account=account, 
                is_active=True
            ).values_list('name', flat=True))
    
    # Get current folder object
    try:
        folder_obj = Folder.objects.get(account=account, name=current_folder, is_active=True)
    except Folder.DoesNotExist:
        # Folder not in cache, try to refresh cache
        try:
            with IMAPEmailClient(
                account.imap_host,
                account.imap_username,
                account.imap_password,
                port=account.imap_port
            ) as client:
                folders = client.sync_folders_cache(account, Folder)
                folder_obj = Folder.objects.get(account=account, name=current_folder, is_active=True)
        except (Folder.DoesNotExist, Exception):
            raise Http404(f"Folder '{current_folder}' not found")
    
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
                account.imap_password,
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
                    account.imap_password,
                    port=account.imap_port
                ) as client:
                    messages = client.fetch_emails(current_folder, limit=50)
            except Exception as e:
                return render(request, 'mail/error.html', {
                    'error': f'Failed to fetch messages: {str(e)}'
                })
    
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
        {'name': f, 'unread': unread_counts.get(f, 0)} 
        for f in folders
    ]
    
    context = {
        'account': account,
        'folders': folders,
        'folders_with_counts': folders_with_counts,
        'messages': messages,
        'current_folder': current_folder,
        'unread_counts': unread_counts,
    }
    
    return render(request, 'mail/inbox.html', context)


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
                account.imap_password,
                port=account.imap_port
            ) as client:
                folders = client.sync_folders_cache(account, Folder)
        except Exception as e:
            # Fallback to stale cache if server is down
            folders = list(Folder.objects.filter(
                account=account, 
                is_active=True
            ).values_list('name', flat=True))
    
    # Fetch full message (bodies are not cached, only headers)
    message = None
    try:
        with IMAPEmailClient(
            account.imap_host,
            account.imap_username,
            account.imap_password,
            port=account.imap_port
        ) as client:
            message = client.fetch_email_by_uid(
                uid,
                folder=selected_folder,
                allow_remote_images=load_remote_images,
            )

    except Exception as e:
        return render(request, 'mail/error.html', {
            'error': f'Failed to load message: {str(e)}'
        })

    if not message:
        raise Http404('Message not found')

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
        {'name': f, 'unread': unread_counts.get(f, 0)} 
        for f in folders
    ]
    
    return render(request, 'mail/message_detail.html', {
        'account': account,
        'message': message,
        'current_folder': selected_folder,
        'load_remote_images': load_remote_images,
        'folders': folders,
        'folders_with_counts': folders_with_counts,
        'unread_counts': unread_counts,
    })


from django.http import JsonResponse
from django.views.decorators.http import require_GET


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
            account.imap_password,
            port=account.imap_port
        ) as client:
            client.client.select_folder(folder_name)
            actual_count = len(client.client.search('ALL'))
        
        return JsonResponse({
            'cached_count': cached_count,
            'actual_count': actual_count,
            'has_new': actual_count > cached_count
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


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
            account.imap_password,
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
    except Exception as e:
        raise Http404(f'Failed to load inline image: {str(e)}')


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
            account.imap_password,
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
    except Exception as e:
        raise Http404(f'Failed to load attachment: {str(e)}')
