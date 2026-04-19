"""
IMAP Email Client
Simple IMAP client for fetching emails from mail servers.
"""

from imapclient import IMAPClient
from email.parser import BytesParser
from email.policy import default
from urllib.parse import quote, urlparse
import logging
import re

from django.utils import timezone

import nh3

logger = logging.getLogger(__name__)


class IMAPEmailClient:
    """Manages IMAP connection and email fetching."""

    def __init__(self, host, username, password, port=993, timeout=30):
        """
        Initialize IMAP client with server credentials.
        
        Args:
            host: IMAP server hostname (e.g., imap.gmail.com)
            username: Email address or username
            password: Password or app-specific password
            port: IMAP port (default 993 for IMAPS)
            timeout: Connection timeout in seconds
        """
        self.host = host
        self.username = username
        self.password = password
        self.port = port
        self.timeout = timeout
        self.client = None

    def connect(self):
        """Connect to IMAP server."""
        try:
            self.client = IMAPClient(
                self.host,
                port=self.port,
                timeout=self.timeout,
                use_uid=True,
                ssl=True
            )
            self.client.login(self.username, self.password)
            return True
        except Exception as e:
            logger.error(f"IMAP connection failed to {self.host}:{self.port}: {str(e)}")
            raise ConnectionError("Failed to connect to IMAP server. Check your host, port, and credentials.")

    def _normalize_envelope_date(self, date_value):
        """Return a timezone-aware datetime suitable for Django DateTimeField storage."""
        if date_value is None:
            return None
        if timezone.is_naive(date_value):
            return timezone.make_aware(date_value, timezone.get_default_timezone())
        return date_value

    def disconnect(self):
        """Close IMAP connection."""
        if self.client:
            try:
                self.client.logout()
            except Exception:
                pass
            self.client = None

    def list_folders(self):
        """
        Get list of folders on the server.
        
        Returns:
            List of folder names
        """
        if not self.client:
            raise RuntimeError("Not connected. Call connect() first.")

        try:
            folders = self.client.list_folders()
            return [folder[2] for folder in folders]
        except Exception as e:
            logger.error(f"Failed to list folders: {str(e)}")
            raise RuntimeError("Failed to list folders.")

    def create_folder(self, name):
        """Create a new folder on the IMAP server."""
        if not self.client:
            raise RuntimeError("Not connected. Call connect() first.")
        try:
            self.client.create_folder(name)
        except Exception as e:
            logger.error(f"Failed to create folder '{name}': {str(e)}")
            raise RuntimeError("Failed to create folder.")

    def delete_folder(self, name):
        """Delete a folder from the IMAP server."""
        if not self.client:
            raise RuntimeError("Not connected. Call connect() first.")
        try:
            self.client.delete_folder(name)
        except Exception as e:
            logger.error(f"Failed to delete folder '{name}': {str(e)}")
            raise RuntimeError("Failed to delete folder.")

    def delete_message(self, uid, folder):
        """Move message to Trash, or expunge if already in Trash."""
        if not self.client:
            raise RuntimeError("Not connected. Call connect() first.")
        self.client.select_folder(folder)
        available = {f[2] for f in self.client.list_folders()}
        trash_candidates = ['Trash', 'Deleted Items', 'INBOX.Trash', 'INBOX/Trash']
        trash = next((c for c in trash_candidates if c in available), None)
        if trash and folder.lower() not in {'trash', 'deleted items'}:
            self.client.move([uid], trash)
        else:
            self.client.add_flags([uid], [b'\\Deleted'])
            self.client.expunge()

    def archive_message(self, uid, folder):
        """Move message to Archive folder, creating it if necessary."""
        if not self.client:
            raise RuntimeError("Not connected. Call connect() first.")
        self.client.select_folder(folder)
        available = {f[2] for f in self.client.list_folders()}
        archive_candidates = ['Archive', 'Archives', 'INBOX.Archive', 'INBOX/Archive']
        archive = next((c for c in archive_candidates if c in available), None)
        if archive is None:
            self.client.create_folder('Archive')
            archive = 'Archive'
        self.client.move([uid], archive)

    def move_message(self, uid, from_folder, to_folder):
        """Move message from one folder to another."""
        if not self.client:
            raise RuntimeError("Not connected. Call connect() first.")
        self.client.select_folder(from_folder)
        self.client.move([uid], to_folder)

        def append_to_sent(self, raw_message_bytes):
            """Append a copy of a sent message to the server's Sent folder."""
            if not self.client:
                raise RuntimeError("Not connected. Call connect() first.")

            sent_folder = None
            try:
                sent_folder = self.client.find_special_folder(b'\\Sent')
            except Exception:
                pass

            if sent_folder is None:
                available = {f[2] for f in self.client.list_folders()}
                for candidate in ('Sent', 'Sent Items', 'Sent Messages', 'INBOX.Sent', 'INBOX/Sent'):
                    if candidate in available:
                        sent_folder = candidate
                        break

            if sent_folder is None:
                try:
                    self.client.create_folder('Sent')
                    sent_folder = 'Sent'
                except Exception as e:
                    logger.error(f"Failed to create Sent folder: {str(e)}")
                    raise RuntimeError("Could not find or create a Sent folder.")

            try:
                self.client.append(sent_folder, raw_message_bytes, flags=[b'\\Seen'])
            except Exception as e:
                logger.error(f"Failed to append message to Sent folder '{sent_folder}': {str(e)}")
                raise RuntimeError("Failed to save message to Sent folder.")

    def set_flag(self, uid, folder, flag, add=True):
        """Add or remove an IMAP flag on a message."""
        if not self.client:
            raise RuntimeError("Not connected. Call connect() first.")
        flag_bytes = flag.encode() if isinstance(flag, str) else flag
        self.client.select_folder(folder)
        if add:
            self.client.add_flags([uid], [flag_bytes])
        else:
            self.client.remove_flags([uid], [flag_bytes])

    def search_messages(self, folder, term, search_in='headers'):
        """
        Search for messages in a folder via IMAP SEARCH.

        Args:
            folder: Folder name to search in
            term: Search term string
            search_in: 'headers' searches Subject + From; 'text' searches full message text

        Returns:
            List of message dicts (same shape as sync_messages_cache output),
            sorted newest-first, capped at 200 results.
        """
        if not self.client:
            raise RuntimeError("Not connected. Call connect() first.")

        try:
            self.client.select_folder(folder)

            if search_in == 'text':
                criteria = ['TEXT', term]
            else:
                criteria = ['OR', 'SUBJECT', term, 'FROM', term]

            # Try with UTF-8 charset first; fall back if server rejects it.
            try:
                msg_ids = self.client.search(criteria, charset='UTF-8')
            except Exception:
                msg_ids = self.client.search(criteria)

            if not msg_ids:
                return []

            # Most recent first, cap at 200.
            msg_ids = sorted(msg_ids, reverse=True)[:200]

            response = self.client.fetch(
                msg_ids, ['ENVELOPE', 'RFC822.SIZE', 'FLAGS', 'BODYSTRUCTURE']
            )

            messages = []
            for msg_id, msg_data in response.items():
                try:
                    envelope = msg_data.get(b'ENVELOPE')
                    if not envelope:
                        continue
                    subject = (
                        envelope.subject.decode('utf-8', errors='ignore')
                        if envelope.subject else ''
                    )
                    sender = str(envelope.from_[0]) if envelope.from_ else ''
                    sender_name = self._extract_sender_name(sender)
                    date = self._normalize_envelope_date(envelope.date)
                    size = msg_data.get(b'RFC822.SIZE', 0)
                    bodystructure = msg_data.get(b'BODYSTRUCTURE')
                    has_attachments = self._has_attachments_from_bodystructure(bodystructure)
                    flags = [
                        flag.decode() if isinstance(flag, bytes) else str(flag)
                        for flag in msg_data.get(b'FLAGS', [])
                    ]
                    messages.append({
                        'uid': str(msg_id),
                        'subject': subject,
                        'sender': sender,
                        'sender_name': sender_name,
                        'date': date,
                        'body': '',
                        'flags': flags,
                        'size': size,
                        'has_attachments': has_attachments,
                    })
                except Exception:
                    continue

            messages.sort(
                key=lambda m: m['date'].timestamp() if m['date'] else 0.0,
                reverse=True,
            )
            return messages

        except Exception as e:
            logger.error(f"IMAP search failed: {str(e)}")
            raise RuntimeError("Search failed.")

    def fetch_emails(self, folder='INBOX', limit=None):
        """
        Fetch emails from a folder.
        
        Args:
            folder: Folder name (default 'INBOX')
            limit: Maximum number of emails to fetch (None = all)
        
        Returns:
            List of email dictionaries with keys:
            - uid: Server UID
            - subject: Email subject
            - sender: From address
            - sender_name: Sender display name
            - date: Email date
            - body: Plain text body
            - raw: Full email object
        """
        if not self.client:
            raise RuntimeError("Not connected. Call connect() first.")

        try:
            # Select folder
            self.client.select_folder(folder)

            # Search for all messages
            msg_ids = self.client.search('ALL')

            if not msg_ids:
                return []

            # Limit results if specified
            if limit:
                msg_ids = msg_ids[-limit:]  # Get most recent emails

            # Fetch emails
            response = self.client.fetch(msg_ids, ['RFC822'])

            emails = []
            for msg_id, msg_data in response.items():
                try:
                    email_obj = self._parse_email(msg_data[b'RFC822'])
                    email_dict = {
                        'uid': msg_id,
                        'subject': email_obj.get('subject', '(no subject)'),
                        'sender': email_obj.get('from', ''),
                        'sender_name': self._extract_sender_name(email_obj.get('from', '')),
                        'date': email_obj.get('date', ''),
                        'body': self._extract_body(email_obj),
                        'has_attachments': bool(self._extract_attachments(email_obj)),
                        'raw': email_obj,
                    }
                    emails.append(email_dict)
                except Exception as e:
                    logger.warning(f"Failed to parse email {msg_id}: {str(e)}")
                    continue

            return emails

        except Exception as e:
            logger.error(f"Failed to fetch emails: {str(e)}")
            raise RuntimeError("Failed to fetch emails.")

    def fetch_email_by_uid(self, uid, folder='INBOX', allow_remote_images=False):
        """
        Fetch a single email by UID.

        Args:
            uid: Message UID
            folder: Folder name (default 'INBOX')
            allow_remote_images: Whether to keep externally hosted images

        Returns:
            Email dictionary or None if not found
        """
        if not self.client:
            raise RuntimeError("Not connected. Call connect() first.")

        try:
            self.client.select_folder(folder)
            response = self.client.fetch([uid], ['RFC822', 'FLAGS'])
            if uid not in response:
                return None

            flags = [
                f.decode() if isinstance(f, bytes) else str(f)
                for f in response[uid].get(b'FLAGS', [])
            ]
            email_obj = self._parse_email(response[uid][b'RFC822'])
            bodies = self._extract_bodies(email_obj)
            html_with_cid_urls, inline_cid_count = self._rewrite_cid_sources(
                bodies['html_body'],
                uid=uid,
                folder=folder,
                email_obj=email_obj,
            )
            sanitized = self._sanitize_html(
                html_with_cid_urls,
                allow_remote_images=allow_remote_images,
            )
            attachments = self._extract_attachments(email_obj)
            return {
                'uid': uid,
                'subject': email_obj.get('subject', '(no subject)'),
                'sender': email_obj.get('from', ''),
                'sender_name': self._extract_sender_name(email_obj.get('from', '')),
                'date': email_obj.get('date', ''),
                'body': bodies['text_body'],
                'body_html': sanitized['html'],
                'has_html': bool(sanitized['html']),
                'blocked_remote_images': sanitized['blocked_remote_images'],
                'inline_cid_images': inline_cid_count,
                'attachments': attachments,
                'flags': flags,
                'raw': email_obj,
            }
        except Exception as e:
            logger.error(f"Failed to fetch email UID {uid}: {str(e)}")
            raise RuntimeError("Failed to fetch email.")

    def _parse_email(self, raw_email):
        """
        Parse raw email bytes into an email object.
        
        Args:
            raw_email: Raw email bytes
            
        Returns:
            Email message object
        """
        parser = BytesParser(policy=default)
        return parser.parsebytes(raw_email)

    def _extract_sender_name(self, from_str):
        """
        Extract sender display name from From header.
        
        Args:
            from_str: From header string (e.g., "John Doe <john@example.com>")
            
        Returns:
            Display name or email address
        """
        if '<' in from_str and '>' in from_str:
            return from_str.split('<')[0].strip().strip('"\'')
        return from_str.split('@')[0] if '@' in from_str else from_str

    def _extract_bodies(self, email_obj):
        """
        Extract plain text and HTML bodies from email.

        Args:
            email_obj: Email message object

        Returns:
            Dict with text_body and html_body keys
        """
        text_body = ""
        html_body = ""

        if email_obj.is_multipart():
            for part in email_obj.walk():
                content_type = part.get_content_type()
                disposition = (part.get_content_disposition() or '').lower()

                # Skip file attachments while extracting message bodies.
                if disposition == 'attachment':
                    continue

                try:
                    content = part.get_content()
                except Exception:
                    continue

                if content_type == 'text/plain' and not text_body:
                    text_body = content
                elif content_type == 'text/html' and not html_body:
                    html_body = content
        else:
            try:
                content = email_obj.get_content()
                if email_obj.get_content_type() == 'text/html':
                    html_body = content
                else:
                    text_body = content
            except Exception:
                pass

        return {
            'text_body': (text_body or '').strip(),
            'html_body': (html_body or '').strip(),
        }

    def _extract_body(self, email_obj):
        """Extract plain text body for message list previews."""
        bodies = self._extract_bodies(email_obj)
        return bodies['text_body']

    def _sanitize_html(self, html_body, allow_remote_images=False):
        """
        Sanitize HTML email content with strict allowlists and anti-tracking cleanup.
        """
        if not html_body:
            return {
                'html': '',
                'blocked_remote_images': 0,
            }

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

        cleaned = nh3.clean(
            html_body,
            tags=allowed_tags,
            attributes=allowed_attributes,
            url_schemes={'http', 'https', 'mailto'},
        )

        blocked_remote_images = 0

        if not allow_remote_images:
            remote_img_pattern = re.compile(
                r'<img\b[^>]*\bsrc\s*=\s*["\']https?://[^"\']+["\'][^>]*>',
                flags=re.IGNORECASE,
            )
            blocked_remote_images = len(remote_img_pattern.findall(cleaned))
            cleaned = remote_img_pattern.sub('', cleaned)

        # Remove image tags that are likely tracking pixels.
        tracking_img_pattern = re.compile(r'<img\b[^>]*>', flags=re.IGNORECASE)

        def _is_tracking_pixel(img_tag):
            widths = re.findall(r'\bwidth\s*=\s*["\']?([0-9]+)', img_tag, flags=re.IGNORECASE)
            heights = re.findall(r'\bheight\s*=\s*["\']?([0-9]+)', img_tag, flags=re.IGNORECASE)
            width_is_tiny = any(int(v) <= 1 for v in widths)
            height_is_tiny = any(int(v) <= 1 for v in heights)

            if width_is_tiny or height_is_tiny:
                return True

            style_match = re.search(
                r'\bstyle\s*=\s*["\']([^"\']*)["\']',
                img_tag,
                flags=re.IGNORECASE,
            )
            if style_match:
                style = style_match.group(1).lower().replace(' ', '')
                tracking_style_markers = (
                    'width:1px',
                    'height:1px',
                    'max-width:1px',
                    'max-height:1px',
                    'display:none',
                    'visibility:hidden',
                    'opacity:0',
                )
                if any(marker in style for marker in tracking_style_markers):
                    return True

            return False

        cleaned = tracking_img_pattern.sub(
            lambda m: '' if _is_tracking_pixel(m.group(0)) else m.group(0),
            cleaned,
        )

        # Enforce safe rel on all links and strip disallowed href schemes.
        anchor_pattern = re.compile(r'<a\b([^>]*)>', flags=re.IGNORECASE)

        def _rewrite_anchor(match):
            attrs = match.group(1)
            href_match = re.search(r'\bhref\s*=\s*["\']([^"\']+)["\']', attrs, flags=re.IGNORECASE)
            if href_match:
                href = href_match.group(1)
                parsed = urlparse(href)
                if parsed.scheme and parsed.scheme.lower() not in {'http', 'https', 'mailto'}:
                    attrs = re.sub(r'\s*href\s*=\s*["\'][^"\']+["\']', '', attrs, flags=re.IGNORECASE)

            attrs = re.sub(r'\s*rel\s*=\s*["\'][^"\']*["\']', '', attrs, flags=re.IGNORECASE)
            return f'<a{attrs} rel="noopener noreferrer nofollow">'

        cleaned = anchor_pattern.sub(_rewrite_anchor, cleaned)
        return {
            'html': cleaned,
            'blocked_remote_images': blocked_remote_images,
        }

    def _collect_inline_cid_parts(self, email_obj):
        """Map CID tokens to MIME part indexes for inline image serving."""
        cid_map = {}
        for idx, part in enumerate(email_obj.walk()):
            content_type = part.get_content_type().lower()
            disposition = (part.get_content_disposition() or '').lower()
            content_id = part.get('Content-ID')

            if not content_id or not content_type.startswith('image/'):
                continue

            # Many senders omit inline disposition but still reference the CID from HTML.
            if disposition in {'attachment'}:
                continue

            normalized_cid = content_id.strip().strip('<>')
            if normalized_cid:
                cid_map[normalized_cid.lower()] = idx

        return cid_map

    def _rewrite_cid_sources(self, html_body, uid, folder, email_obj):
        """Rewrite cid: sources in HTML to local inline-image URLs."""
        if not html_body:
            return '', 0

        cid_map = self._collect_inline_cid_parts(email_obj)
        if not cid_map:
            return html_body, 0

        cid_pattern = re.compile(
            r'(<img\b[^>]*\bsrc\s*=\s*["\'])cid:([^"\']+)(["\'][^>]*>)',
            flags=re.IGNORECASE,
        )

        replaced_count = 0
        encoded_folder = quote(str(folder), safe='')

        def _replace_cid(match):
            nonlocal replaced_count
            prefix = match.group(1)
            cid_token = match.group(2).strip().strip('<>')
            suffix = match.group(3)

            part_idx = cid_map.get(cid_token.lower())
            if part_idx is None:
                return match.group(0)

            replaced_count += 1
            local_src = f"/message/{uid}/inline/{part_idx}/?folder={encoded_folder}"
            return f"{prefix}{local_src}{suffix}"

        rewritten_html = cid_pattern.sub(_replace_cid, html_body)
        return rewritten_html, replaced_count

    def _extract_attachments(self, email_obj):
        """Extract non-inline attachment metadata for download links."""
        attachments = []

        for idx, part in enumerate(email_obj.walk()):
            if part.is_multipart():
                continue

            disposition = (part.get_content_disposition() or '').lower()
            filename = part.get_filename()
            content_id = (part.get('Content-ID') or '').strip()
            content_type = part.get_content_type().lower()

            is_inline_cid = bool(content_id) and disposition != 'attachment'
            is_attachment = disposition == 'attachment' or (filename and not is_inline_cid)

            if not is_attachment:
                continue

            payload = part.get_payload(decode=True) or b''
            safe_name = filename or f'attachment-{idx}'

            attachments.append({
                'part_index': idx,
                'filename': safe_name,
                'content_type': content_type,
                'size': len(payload),
            })

        return attachments

    def _has_attachments_from_bodystructure(self, bodystructure):
        """Detect likely attachments from IMAP BODYSTRUCTURE metadata only."""
        if not bodystructure:
            return False

        tokens = []

        def _walk(node):
            if node is None:
                return

            if isinstance(node, bytes):
                token = node.decode('utf-8', errors='ignore').strip().upper()
                if token:
                    tokens.append(token)
                return

            if isinstance(node, str):
                token = node.strip().upper()
                if token:
                    tokens.append(token)
                return

            if isinstance(node, (list, tuple)):
                for child in node:
                    _walk(child)
                return

            try:
                for child in node:
                    _walk(child)
                return
            except TypeError:
                pass

            token = str(node).strip().upper()
            if token:
                tokens.append(token)

        _walk(bodystructure)

        if 'ATTACHMENT' in tokens:
            return True

        # Common fallback: filename/name parameters indicate an attached part.
        if 'FILENAME' in tokens or 'NAME' in tokens:
            return True

        return False

    def sync_folders_cache(self, account, FolderModel):
        """
        Sync folder cache with IMAP server.
        
        Args:
            account: EmailAccount instance
            FolderModel: Django Folder model class
            
        Returns:
            List of folder names
        """
        if not self.client:
            raise RuntimeError("Not connected. Call connect() first.")

        try:
            server_folders = self.list_folders()
            
            # Mark all existing folders as inactive
            FolderModel.objects.filter(account=account).update(is_active=False)
            
            # Add/update folders from server
            for folder_name in server_folders:
                FolderModel.objects.update_or_create(
                    account=account,
                    name=folder_name,
                    defaults={'is_active': True}
                )
            
            return server_folders
        except Exception as e:
            logger.error(f"Failed to sync folder cache: {str(e)}")
            raise RuntimeError("Failed to sync folder cache.")

    def sync_messages_cache(self, account, folder_obj, CachedMessageModel, limit=100):
        """
        Sync message headers cache for a folder.
        
        Args:
            account: EmailAccount instance
            folder_obj: Folder instance
            CachedMessageModel: Django CachedMessage model class
            limit: Maximum messages to cache (default 100)
            
        Returns:
            Number of messages cached
        """
        if not self.client:
            raise RuntimeError("Not connected. Call connect() first.")

        try:
            # Select folder and get message IDs
            self.client.select_folder(folder_obj.name)
            msg_ids = self.client.search('ALL')
            
            if not msg_ids:
                return 0
            
            # Limit to most recent messages
            msg_ids = sorted(msg_ids, reverse=True)[:limit]
            
            # Fetch metadata only; no full message download required.
            response = self.client.fetch(msg_ids, ['ENVELOPE', 'RFC822.SIZE', 'FLAGS', 'BODYSTRUCTURE'])
            
            cached_count = 0
            for msg_id, msg_data in response.items():
                try:
                    envelope = msg_data.get(b'ENVELOPE')
                    if envelope:
                        # Extract message metadata
                        subject = envelope.subject.decode('utf-8', errors='ignore') if envelope.subject else ''
                        sender = str(envelope.from_[0]) if envelope.from_ else ''
                        sender_name = self._extract_sender_name(sender)
                        date = self._normalize_envelope_date(envelope.date)
                        size = msg_data.get(b'RFC822.SIZE', 0)
                        bodystructure = msg_data.get(b'BODYSTRUCTURE')
                        has_attachments = self._has_attachments_from_bodystructure(bodystructure)
                        flags = [flag.decode() if isinstance(flag, bytes) else str(flag) 
                                for flag in msg_data.get(b'FLAGS', [])]
                        
                        # Cache the message
                        CachedMessageModel.objects.update_or_create(
                            account=account,
                            folder=folder_obj,
                            uid=str(msg_id),
                            defaults={
                                'subject': subject[:500],  # Truncate if too long
                                'sender': sender,
                                'sender_name': sender_name,
                                'date': date,
                                'size': size,
                                'has_attachments': has_attachments,
                                'flags': flags,
                            }
                        )
                        cached_count += 1
                        
                except Exception as e:
                    # Skip problematic messages but continue
                    continue
            
            return cached_count
        except Exception as e:
            logger.error(f"Failed to sync message cache: {str(e)}")
            raise RuntimeError("Failed to sync message cache.")

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()
