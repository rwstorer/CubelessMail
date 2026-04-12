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
