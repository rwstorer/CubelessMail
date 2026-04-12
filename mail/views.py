from django.http import Http404
from django.shortcuts import render
from .models import EmailAccount
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
    folders = []
    messages = []
    
    try:
        # Connect to IMAP and fetch data
        with IMAPEmailClient(
            account.imap_host,
            account.imap_username,
            account.imap_password,
            port=account.imap_port
        ) as client:
            # Get folders
            folders = client.list_folders()
            
            # Get folder messages (limit to 50 for simplicity)
            messages = client.fetch_emails(current_folder, limit=50)
    
    except Exception as e:
        return render(request, 'mail/error.html', {
            'error': f'Failed to connect to email account: {str(e)}'
        })
    
    context = {
        'account': account,
        'folders': folders,
        'messages': messages,
        'current_folder': current_folder,
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
    folders = []
    message = None

    try:
        with IMAPEmailClient(
            account.imap_host,
            account.imap_username,
            account.imap_password,
            port=account.imap_port
        ) as client:
            folders = client.list_folders()
            message = client.fetch_email_by_uid(uid, folder=selected_folder)

    except Exception as e:
        return render(request, 'mail/error.html', {
            'error': f'Failed to load message: {str(e)}'
        })

    if not message:
        raise Http404('Message not found')

    return render(request, 'mail/message_detail.html', {
        'account': account,
        'message': message,
        'current_folder': selected_folder,
        'folders': folders,
    })
