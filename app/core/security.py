from __future__ import annotations

import hashlib
import hmac
import secrets
import string

from cryptography.fernet import Fernet
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.core.config import settings
from app.core.exceptions import AuthError


def create_session_cookie(user_id: str, role: str) -> str:
    """Create a signed session value for the cookie."""
    s = URLSafeTimedSerializer(settings.secret_key)
    return s.dumps({"user_id": str(user_id), "role": role})


def decode_session_cookie(cookie_value: str) -> dict:
    """Decode and verify session cookie. Raises AuthError on failure."""
    s = URLSafeTimedSerializer(settings.secret_key)
    try:
        data = s.loads(cookie_value, max_age=604800)  # 7 days in seconds
        return data  # type: ignore
    except SignatureExpired as e:
        raise AuthError("Session expired. Please log in again.") from e
    except BadSignature as e:
        raise AuthError("Invalid session.") from e


def encrypt_field(plaintext: str) -> str:
    """Encrypt a string field. Returns base64-encoded ciphertext."""
    f = Fernet(settings.encryption_key.encode())
    return f.encrypt(plaintext.encode()).decode()


def decrypt_field(ciphertext: str) -> str:
    """Decrypt a previously encrypted field. Raises ValueError on failure."""
    f = Fernet(settings.encryption_key.encode())
    try:
        return f.decrypt(ciphertext.encode()).decode()
    except Exception as exc:
        raise ValueError("Failed to decrypt field — key mismatch or corrupted data.") from exc


def hash_ip(ip_address: str) -> str:
    """One-way hash of an IP address for audit logging."""
    return hashlib.sha256(ip_address.encode()).hexdigest()


def generate_token_secret() -> str:
    """
    Generate a cryptographically secure 6-character alphanumeric token.
    Uppercase only for readability at a pharmacy counter.
    Returns: e.g. "X4K9PL"
    """
    alphabet = string.ascii_uppercase + string.digits
    # Remove ambiguous chars: 0, O, I, 1 — hard to distinguish verbally
    alphabet = alphabet.replace("0", "").replace("O", "").replace("I", "").replace("1", "")
    return "".join(secrets.choice(alphabet) for _ in range(6))


def hash_token(token_secret: str) -> str:
    """
    HMAC-SHA256 hash of a token secret using the app HMAC_SECRET.
    This is what gets stored in the DB — the plaintext token is never stored.
    Returns: 64-char hex string
    """
    return hmac.new(
        settings.hmac_secret.encode(),
        token_secret.encode(),
        hashlib.sha256,
    ).hexdigest()


def verify_token(token_secret: str, stored_hash: str) -> bool:
    """Constant-time comparison to verify a token against its stored hash."""
    expected = hash_token(token_secret)
    return hmac.compare_digest(expected, stored_hash)