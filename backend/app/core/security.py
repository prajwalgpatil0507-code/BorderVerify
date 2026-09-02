"""Authentication & password hashing (JWT-based, prototype grade)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import jwt, JWTError
from passlib.context import CryptContext


# pbkdf2_sha256 is a pure-Python backend - avoids native bcrypt version
# incompatibilities on the demo environment while still hashing correctly.
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return pwd_context.verify(plain, hashed)
    except Exception:  # noqa: BLE001
        return False


def create_access_token(subject: str, role: str = "officer",
                        expires_minutes: int | None = None) -> str:
    from ..config import settings
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": subject, "role": role, "exp": expire}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    from ..config import settings
    try:
        return jwt.decode(token, settings.SECRET_KEY,
                          algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        return None
