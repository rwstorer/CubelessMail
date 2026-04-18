"""
Data migration to encrypt existing plaintext passwords.
Encrypts all existing imap_password values to imap_password_encrypted.
"""

from django.db import migrations
from cubelessmail.crypto import encrypt_value


def encrypt_passwords(apps, schema_editor):
    """Encrypt all existing plaintext passwords."""
    EmailAccount = apps.get_model('mail', 'EmailAccount')
    
    for account in EmailAccount.objects.all():
        # If password is plaintext and not yet encrypted
        if account.imap_password and not account.imap_password_encrypted:
            try:
                account.imap_password_encrypted = encrypt_value(account.imap_password)
                account.imap_password = ''  # Clear plaintext
                account.save(update_fields=['imap_password', 'imap_password_encrypted'])
            except Exception as e:
                # Log error but don't fail migration
                print(f"Failed to encrypt password for {account.email}: {str(e)}")


def decrypt_passwords(apps, schema_editor):
    """Reverse migration: not supported. Encrypted data cannot be reversed."""
    # This migration is one-way. If you need to rollback, restore from backup.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('mail', '0005_emailaccount_imap_password_encrypted_and_more'),
    ]

    operations = [
        migrations.RunPython(encrypt_passwords, decrypt_passwords),
    ]
