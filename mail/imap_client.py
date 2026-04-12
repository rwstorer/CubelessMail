"""
IMAP Email Client
Simple IMAP client for fetching emails from mail servers.
"""

from imapclient import IMAPClient
from email.parser import BytesParser
from email.policy import default


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
            raise ConnectionError(f"Failed to connect to {self.host}: {str(e)}")

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
            raise RuntimeError(f"Failed to list folders: {str(e)}")

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
                        'raw': email_obj,
                    }
                    emails.append(email_dict)
                except Exception as e:
                    # Skip emails that fail to parse
                    print(f"Warning: Failed to parse email {msg_id}: {str(e)}")
                    continue

            return emails

        except Exception as e:
            raise RuntimeError(f"Failed to fetch emails from {folder}: {str(e)}")

    def fetch_email_by_uid(self, uid, folder='INBOX'):
        """
        Fetch a single email by UID.

        Args:
            uid: Message UID
            folder: Folder name (default 'INBOX')

        Returns:
            Email dictionary or None if not found
        """
        if not self.client:
            raise RuntimeError("Not connected. Call connect() first.")

        try:
            self.client.select_folder(folder)
            response = self.client.fetch([uid], ['RFC822'])
            if uid not in response:
                return None

            email_obj = self._parse_email(response[uid][b'RFC822'])
            return {
                'uid': uid,
                'subject': email_obj.get('subject', '(no subject)'),
                'sender': email_obj.get('from', ''),
                'sender_name': self._extract_sender_name(email_obj.get('from', '')),
                'date': email_obj.get('date', ''),
                'body': self._extract_body(email_obj),
                'raw': email_obj,
            }
        except Exception as e:
            raise RuntimeError(f"Failed to fetch email UID {uid} from {folder}: {str(e)}")

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

    def _extract_body(self, email_obj):
        """
        Extract plain text body from email.
        
        Args:
            email_obj: Email message object
            
        Returns:
            Plain text body or empty string
        """
        body = ""
        
        # Try to get plain text part
        if email_obj.is_multipart():
            for part in email_obj.walk():
                content_type = part.get_content_type()
                if content_type == 'text/plain':
                    try:
                        body = part.get_content()
                        break
                    except Exception:
                        pass
        else:
            try:
                body = email_obj.get_content()
            except Exception:
                pass

        return body.strip()

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()
