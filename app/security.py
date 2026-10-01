"""
طبقة الأمان — تدعم تنسيق تطبيق سطح المكتب (salt$sha256) و bcrypt للأمان المستقبلي.
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


# ============================================================
# كلمات المرور
# ============================================================
def _verify_custom_sha256(plain: str, hashed: str) -> bool:
    """
    يتحقق من صيغة تطبيق سطح المكتب: salt(32 hex)$sha256(64 hex)
    يجرب 4 صيغ محتملة لترتيب الـ salt والـ password.
    """
    try:
        salt_hex, stored_hash = hashed.split("$", 1)
    except ValueError:
        return False

    if len(salt_hex) != 32 or len(stored_hash) != 64:
        return False

    # الصيغ الأربع المحتملة (نجربها بالترتيب)
    candidates: list[str] = []

    # 1) sha256(salt_hex + password)
    candidates.append(
        hashlib.sha256((salt_hex + plain).encode("utf-8")).hexdigest()
    )
    # 2) sha256(password + salt_hex)
    candidates.append(
        hashlib.sha256((plain + salt_hex).encode("utf-8")).hexdigest()
    )

    # 3) sha256(salt_bytes + password)
    try:
        salt_bytes = bytes.fromhex(salt_hex)
        candidates.append(
            hashlib.sha256(salt_bytes + plain.encode("utf-8")).hexdigest()
        )
        # 4) sha256(password + salt_bytes)
        candidates.append(
            hashlib.sha256(plain.encode("utf-8") + salt_bytes).hexdigest()
        )
    except ValueError:
        pass

    # استخدام compare_digest لمقاومة timing attacks
    return any(
        hmac.compare_digest(candidate, stored_hash) for candidate in candidates
    )


def verify_password(plain: str, hashed: str) -> bool:
    """
    يتحقق من كلمة المرور مقابل الـ hash.
    يدعم:
      - الصيغة المخصصة: salt(32hex)$sha256(64hex)  ← تطبيق سطح المكتب
      - bcrypt: $2a$ / $2b$ / $2y$
    """
    if not plain or not hashed:
        return False

    # 1) bcrypt
    if hashed.startswith("$2a$") or hashed.startswith("$2b$") or hashed.startswith("$2y$"):
        try:
            return pwd_context.verify(plain, hashed)
        except Exception:
            return False

    # 2) الصيغة المخصصة (salt$sha256)
    if "$" in hashed and len(hashed) == 97:
        return _verify_custom_sha256(plain, hashed)

    # 3) صيغ أخرى غير معروفة
    return False


def hash_password(plain: str) -> str:
    """
    ينشئ hash بصيغة تطبيق سطح المكتب: salt$sha256
    هذه الصيغة متوافقة مع كل من API وتطبيق سطح المكتب.
    """
    salt_hex = secrets.token_hex(16)  # 16 bytes → 32 hex chars
    digest = hashlib.sha256((salt_hex + plain).encode("utf-8")).hexdigest()
    return f"{salt_hex}${digest}"


# ============================================================
# JWT
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
