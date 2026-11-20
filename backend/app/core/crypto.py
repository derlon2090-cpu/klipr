"""Small, intentionally non-logging vault encryption helpers."""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings


def _fernet() -> Fernet:
    """Derive a stable Fernet (AES-128-CBC + HMAC) key from app secret material.

    Fernet's construction provides authenticated encryption and is the intended
    encrypted-at-rest format here.  A dedicated KICK_VAULT_KEY may be supplied;
    otherwise the installation session secret is used.
    """
    settings = get_settings()
    material = settings.kick_vault_key or settings.klipr_session_secret
    if not material:
        raise RuntimeError("KICK_VAULT_KEY or KLIPR_SESSION_SECRET must be configured")
    key = base64.urlsafe_b64encode(hashlib.sha256(material.encode("utf-8")).digest())
    return Fernet(key)


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_secret(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeDecodeError) as error:
        raise ValueError("Stored session cannot be decrypted") from error
