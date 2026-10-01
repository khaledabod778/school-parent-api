"""
طبقة الأمان — متوافقة تماماً مع تطبيق سطح المكتب (PBKDF2-SHA256).
"""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import get_settings

settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ثابت يستخدمه تطبيق سطح المكتب
PBKDF2_ITERATIONS = 100_000


# ============================================================
# كلمات المرور
# ============================================================
def _verify_pbkdf2(plain: str, hashed: str) -> bool:
    """
    الصيغة: salt_hex(32)$pbkdf2_sha256_hex(64)
    الـ salt يُمرَّر كـ UTF-8 bytes (32 bytes للحروف hex).
    """
    try:
        salt_hex, stored_digest = hashed.split("$", 1)
    except ValueError:
        return False

    if len(salt_hex) != 32 or len(stored_digest) != 64:
        return False

    try:
        computed = hashlib.pbkdf2_hmac(
            "sha256",
            plain.encode("utf-8"),
            salt_hex.encode("utf-8"),
            PBKDF2_ITERATIONS,
        ).hex()
    except Exception:
        return False

    return hmac.compare_digest(computed, stored_digest)


def verify_password(plain: str, hashed: str) -> bool:
    """يتحقق من كلمة المرور — يدعم pbkdf2 (سطح المكتب) و bcrypt (مستقبلي)."""
    if not plain or not hashed:
        return False

    # bcrypt (للحسابات الحديثة إذا استخدمنا hash_password الجديد)
    if hashed.startswith(("$2a$", "$2b$", "$2y$")):
        try:
            return pwd_context.verify(plain, hashed)
        except Exception:
            return False

    # pbkdf2 — تنسيق تطبيق سطح المكتب (salt$digest، 97 حرف)
    if "$" in hashed and len(hashed) == 97:
        return _verify_pbkdf2(plain, hashed)

    return False


def hash_password(plain: str) -> str:
    """
    ينشئ hash بنفس صيغة تطبيق سطح المكتب (pbkdf2_sha256 + salt_hex).
    التوافق كامل مع تطبيق السطح المكتب.
    """
    salt_hex = secrets.token_hex(16)  # 32 hex chars = 16 bytes
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        plain.encode("utf-8"),
        salt_hex.encode("utf-8"),
        PBKDF2_ITERATIONS,
    ).hex()
    return f"{salt_hex}${digest}"


# ============================================================
# JWT (لا تغيير)
# ============================================================
def create_access_token(parent_id: int, full_name: str = "") -> tuple[str, int]:
    expires_delta = timedelta(minutes=settings.access_token_expire_minutes)
    expire = datetime.now(timezone.utc) + expires_delta
    payload = {
        "sub": str(parent_id),
        "type": "access",
        "name": full_name,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, int(expires_delta.total_seconds())


def create_refresh_token(parent_id: int) -> str:
    expires_delta = timedelta(days=settings.refresh_token_expire_days)
    expire = datetime.now(timezone.utc) + expires_delta
    payload = {
        "sub": str(parent_id),
        "type": "refresh",
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
    except JWTError:
        return None
