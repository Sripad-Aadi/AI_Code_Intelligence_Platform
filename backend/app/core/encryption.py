"""Fernet encryption for sensitive data at rest (Step 18).

Provides encrypt/decrypt helpers using a key from ENCRYPTION_KEY env var.
The key must be a 32-byte URL-safe base64-encoded string (Fernet format).
Generate with:

`python -c "from cryptography.fernet import Fernet;`
`print(Fernet.generate_key().decode())"`
"""

import logging
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings

log = logging.getLogger(__name__)

_fernet: Optional[Fernet] = None


def _get_fernet() -> Optional[Fernet]:
    """Get or create the Fernet cipher instance."""
    global _fernet
    if _fernet is None:
        key = settings.ENCRYPTION_KEY
        if not key:
            log.warning("ENCRYPTION_KEY not set — encryption disabled")
            return None
        try:
            _fernet = Fernet(key.encode())
        except Exception as e:
            log.error("Invalid ENCRYPTION_KEY: %s", e)
            return None
    return _fernet


def encrypt_value(plaintext: str) -> Optional[str]:
    """
    Encrypt a plaintext string.

    Returns the Fernet token (URL-safe base64) or None if encryption is disabled.
    """
    f = _get_fernet()
    if f is None:
        return None
    try:
        return f.encrypt(plaintext.encode()).decode()
    except Exception as e:
        log.error("Encryption failed: %s", e)
        return None


def decrypt_value(token: str) -> Optional[str]:
    """
    Decrypt a Fernet token back to plaintext.

    Returns the plaintext or None if decryption fails or encryption is disabled.
    """
    f = _get_fernet()
    if f is None:
        return None
    try:
        return f.decrypt(token.encode()).decode()
    except InvalidToken:
        log.warning("Decryption failed: invalid token or wrong key")
        return None
    except Exception as e:
        log.error("Decryption failed: %s", e)
        return None
