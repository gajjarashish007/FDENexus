"""TOTP (RFC 6238), secret encryption at rest, token hashing. Standard library + cryptography."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time

from cryptography.fernet import Fernet


def _fernet(master: str) -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(("fde-m07|" + master).encode()).digest())
    return Fernet(key)


def encrypt(master: str, text: str) -> str:
    return _fernet(master).encrypt(text.encode()).decode()


def decrypt(master: str, token: str) -> str:
    return _fernet(master).decrypt(token.encode()).decode()


def new_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def totp(secret: str, at: float | None = None, step: int = 30, digits: int = 6) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8))
    counter = int((at if at is not None else time.time()) // step)
    mac = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    off = mac[-1] & 0x0F
    code = (struct.unpack(">I", mac[off:off + 4])[0] & 0x7FFFFFFF) % (10 ** digits)
    return str(code).zfill(digits)


def verify_totp(secret: str, code: str, window: int = 1) -> int | None:
    """Returns the matched time-step counter (for replay protection) or None."""
    code = "".join(ch for ch in str(code or "") if ch.isdigit())
    if len(code) != 6:
        return None
    now = time.time()
    for d in range(-window, window + 1):
        t = now + d * 30
        if hmac.compare_digest(totp(secret, t), code):
            return int(t // 30)
    return None


def otpauth_uri(secret: str, account: str, issuer: str = "FDE Nexus") -> str:
    from urllib.parse import quote
    return f"otpauth://totp/{quote(issuer)}:{quote(account)}?secret={secret}&issuer={quote(issuer)}&algorithm=SHA1&digits=6&period=30"


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def new_recovery_codes(n: int = 10) -> list[str]:
    return ["-".join(secrets.token_hex(2) for _ in range(3)) for _ in range(n)]
