"""
Encryption/decryption utilities for sensitive fields.
Uses Fernet (symmetric encryption) with a key from settings.
"""

from django.conf import settings
from cryptography.fernet import Fernet, InvalidToken
import logging

logger = logging.getLogger(__name__)


def get_cipher():
    """Get the Fernet cipher instance using the encryption key from settings."""
    key = settings.MAIL_ENCRYPTION_KEY
    if not key:
        raise ValueError(
            "MAIL_ENCRYPTION_KEY is not set. "
            "Generate one with: python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\""
        )
    try:
        return Fernet(key.encode())
    except Exception as e:
        raise ValueError(f"Invalid MAIL_ENCRYPTION_KEY: {str(e)}")


def encrypt_value(plaintext):
    """
    Encrypt a plaintext string.
    
    Args:
        plaintext: String to encrypt
        
    Returns:
        Encrypted bytes as a string (safe for database storage)
    """
    if not plaintext:
        return ''
    
    try:
        cipher = get_cipher()
        encrypted = cipher.encrypt(plaintext.encode())
        return encrypted.decode()
    except Exception as e:
        logger.error(f"Encryption failed: {str(e)}")
        raise


def decrypt_value(ciphertext):
    """
    Decrypt a ciphertext string.
    
    Args:
        ciphertext: Encrypted string from database
        
    Returns:
        Decrypted plaintext string, or empty string if decryption fails
    """
    if not ciphertext:
        return ''
    
    try:
        cipher = get_cipher()
        decrypted = cipher.decrypt(ciphertext.encode())
        return decrypted.decode()
    except InvalidToken:
        logger.warning("Decryption failed: Invalid token. Key may have changed.")
        return ''
    except Exception as e:
        logger.error(f"Decryption failed: {str(e)}")
        return ''
