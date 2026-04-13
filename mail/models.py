from django.db import models


class EmailAccount(models.Model):
    """Stores IMAP/SMTP credentials for email accounts."""
    
    email = models.EmailField(unique=True)
    imap_host = models.CharField(max_length=255)
    imap_port = models.IntegerField(default=993)
    imap_username = models.CharField(max_length=255)
    imap_password = models.CharField(max_length=255)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Email Account'
        verbose_name_plural = 'Email Accounts'
    
    def __str__(self):
        return self.email


class Folder(models.Model):
    """Caches folder information to avoid repeated IMAP LIST commands."""
    
    account = models.ForeignKey(EmailAccount, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    last_updated = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        unique_together = ['account', 'name']
        verbose_name = 'Cached Folder'
        verbose_name_plural = 'Cached Folders'
    
    def __str__(self):
        return f"{self.account.email}: {self.name}"


class CachedMessage(models.Model):
    """Caches message headers/metadata for fast message list display."""
    
    account = models.ForeignKey(EmailAccount, on_delete=models.CASCADE)
    folder = models.ForeignKey(Folder, on_delete=models.CASCADE)
    uid = models.CharField(max_length=50)  # IMAP UID
    subject = models.CharField(max_length=500, blank=True)
    sender = models.CharField(max_length=255, blank=True)
    sender_name = models.CharField(max_length=255, blank=True)
    date = models.DateTimeField(null=True, blank=True)
    size = models.IntegerField(default=0)
    has_attachments = models.BooleanField(default=False)
    flags = models.JSONField(default=list)  # ['SEEN', 'FLAGGED', etc.]
    last_updated = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['account', 'folder', 'uid']
        verbose_name = 'Cached Message'
        verbose_name_plural = 'Cached Messages'
        indexes = [
            models.Index(fields=['account', 'folder', 'last_updated']),
            models.Index(fields=['account', 'folder', 'uid']),
        ]
    
    def __str__(self):
        return f"{self.folder.name}: {self.subject[:50]}"
