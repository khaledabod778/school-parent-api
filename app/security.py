from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import get_settings

settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain: str, hashed: str) -> bool:
    """التحقق من كلمة المرور مقابل hash."""
    try:
        return pwd_context.verify(plain, hashed)
    except Exception:
        return False


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def create_access_token(parent_id: int, full_name: str = "") -> tuple[str, int]:
    """ينشئ access token. يرجع (token, expires_in_seconds)."""
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
    """يفك التوكن. يرجع payload أو None."""
    try:
        return jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
    except JWTError:
        return None