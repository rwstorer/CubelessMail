"""
SMTP Email Client
Simple SMTP client for sending emails via mail servers.
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import os
import logging

logger = logging.getLogger(__name__)


class SMTPEmailClient:
    """Manages SMTP connection and email sending."""

    def __init__(self, host, username, password, port=587, timeout=30, use_tls=True):
        """
        Initialize SMTP client with server credentials.
        
        Args:
            host: SMTP server hostname (e.g., smtp.gmail.com)
            username: Email address or username
            password: Password or app-specific password
            port: SMTP port (default 587 for TLS, 25 for unencrypted, 465 for SSL)
            timeout: Connection timeout in seconds
            use_tls: Whether to use STARTTLS (default True for port 587)
        """
        self.host = host
        self.username = username
        self.password = password
        self.port = port
        self.timeout = timeout
        self.use_tls = use_tls
        self.client = None

    def connect(self):
        """Connect and authenticate to SMTP server."""
        try:
            if self.port == 465:
                # Use SMTP_SSL for port 465
                self.client = smtplib.SMTP_SSL(
                    self.host,
                    self.port,
                    timeout=self.timeout
                )
            else:
                # Use SMTP with STARTTLS for port 587 (or 25)
                self.client = smtplib.SMTP(
                    self.host,
                    self.port,
                    timeout=self.timeout
                )
                if self.use_tls:
                    self.client.starttls()
            
            self.client.login(self.username, self.password)
            return True
        except Exception as e:
            logger.error(f"SMTP connection failed to {self.host}:{self.port}: {str(e)}")
            raise ConnectionError("Failed to connect to SMTP server. Check your host, port, and credentials.")

    def disconnect(self):
        """Close SMTP connection."""
        if self.client:
            try:
                self.client.quit()
            except Exception:
                pass
            self.client = None

    def __enter__(self):
        """Context manager entry for SMTP lifecycle management."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit that always tears down SMTP connection."""
        self.disconnect()

    def send_email(
        self,
        to_address,
        subject,
        body,
        html_body=None,
        attachments=None,
        cc_addresses=None,
        bcc_addresses=None,
        reply_to=None,
        in_reply_to=None,
        references=None,
    ):
        """
        Send an email.
        
        Args:
            to_address: Recipient email address (string) or list of addresses
            subject: Email subject
            body: Plain text body
            html_body: Optional HTML body (if provided, multipart alternative will be used)
            attachments: Optional list of file paths to attach
            cc_addresses: Optional CC recipient string or list
            bcc_addresses: Optional BCC recipient string or list
            reply_to: Optional Reply-To header value
            in_reply_to: Optional In-Reply-To header value
            references: Optional References header value
        
        Returns:
            True if sent successfully
        
        Raises:
            RuntimeError: If not connected or send fails
        """
        if not self.client:
            raise RuntimeError("Not connected. Call connect() first.")
        
        # Normalize recipients to lists
        if isinstance(to_address, str):
            to_address = [to_address]
        cc_addresses = cc_addresses or []
        bcc_addresses = bcc_addresses or []
        if isinstance(cc_addresses, str):
            cc_addresses = [cc_addresses]
        if isinstance(bcc_addresses, str):
            bcc_addresses = [bcc_addresses]
        all_recipients = list(to_address) + list(cc_addresses) + list(bcc_addresses)
        
        try:
            # Create message
            if html_body:
                msg = MIMEMultipart('alternative')
            else:
                msg = MIMEMultipart() if attachments else MIMEText(body, 'plain')
            
            msg['From'] = self.username
            msg['To'] = ', '.join(to_address)
            if cc_addresses:
                msg['Cc'] = ', '.join(cc_addresses)
            if reply_to:
                msg['Reply-To'] = reply_to
            if in_reply_to:
                msg['In-Reply-To'] = in_reply_to
            if references:
                msg['References'] = references
            msg['Subject'] = subject
            
            # Attach bodies
            if html_body:
                # Attach plain text first, then HTML (per RFC 2046)
                part_text = MIMEText(body, 'plain')
                msg.attach(part_text)
                part_html = MIMEText(html_body, 'html')
                msg.attach(part_html)
            elif attachments:
                # No HTML, but has attachments: need to wrap the text in multipart
                part_text = MIMEText(body, 'plain')
                msg.attach(part_text)
            
            # Attach files
            if attachments:
                for filepath in attachments:
                    self._attach_file(msg, filepath)
            
            # Send
            raw_bytes = msg.as_bytes()
            self.client.sendmail(self.username, all_recipients, raw_bytes)
            return raw_bytes
        
        except FileNotFoundError as e:
            logger.error(f"Attachment file not found: {str(e)}")
            raise RuntimeError("One or more attachment files could not be found.")
        except Exception as e:
            logger.error(f"Failed to send email: {str(e)}")
            raise RuntimeError("Failed to send email. Please check your message and try again.")

    def _attach_file(self, msg, filepath):
        """
        Attach a file to the message.
        
        Args:
            msg: MIMEMultipart message object
            filepath: Path to file to attach
        
        Raises:
            FileNotFoundError: If file doesn't exist
        """
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"File not found: {filepath}")
        
        try:
            filename = os.path.basename(filepath)
            
            # Determine MIME type based on file extension
            with open(filepath, 'rb') as attachment:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(attachment.read())
            
            encoders.encode_base64(part)
            part.add_header(
                'Content-Disposition',
                'attachment',
                filename=filename
            )
            msg.attach(part)
        except FileNotFoundError:
            raise
        except Exception as e:
            logger.error(f"Failed to attach file: {str(e)}")
            raise RuntimeError(f"Failed to attach file: {os.path.basename(filepath)}")

    def send_email_batch(self, recipients, subject, body, html_body=None):
        """
        Send the same email to multiple recipients.
        
        Args:
            recipients: List of email addresses
            subject: Email subject
            body: Plain text body
            html_body: Optional HTML body
        
        Returns:
            Dict with 'sent' (list of successful addresses) and 'failed' (dict of address: error)
        
        Raises:
            RuntimeError: If not connected
        """
        if not self.client:
            raise RuntimeError("Not connected. Call connect() first.")
        
        results = {
            'sent': [],
            'failed': {}
        }
        
        for recipient in recipients:
            try:
                self.send_email(recipient, subject, body, html_body=html_body)
                results['sent'].append(recipient)
            except Exception as e:
                # Log the full error but store a generic message
                logger.error(f"Failed to send email to {recipient}: {str(e)}")
                results['failed'][recipient] = "Failed to send email"
        
        return results
