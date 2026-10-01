import logging
import random
import secrets
import time
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session
from app.sync_utils import (
    build_sync_update_set,
    fill_sync_columns_for_insert,
)
from app.deps import get_current_parent, get_db
from app.models import Parent, ParentDevice
from app.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.utils import ok

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Auth"])


# ============================================================
# نماذج الطلب
# ============================================================
class LoginRequest(BaseModel):
    phone: str
    password: str
    device_token: str | None = None
    device_type: str | None = None
    app_version: str | None = None


class RefreshRequest(BaseModel):
    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    phone: str


class VerifyOtpRequest(BaseModel):
    phone: str
    otp: str


class ResetPasswordRequest(BaseModel):
    reset_token: str
    new_password: str


class DeviceRegisterRequest(BaseModel):
    device_token: str
    device_type: str | None = None
    app_version: str | None = None
    device_model: str | None = None
    os_version: str | None = None


# ============================================================
# تخزين OTP مؤقتاً
# ============================================================
_otp_store: dict[str, tuple[str, float]] = {}
_reset_tokens: dict[str, tuple[int, float]] = {}
OTP_TTL_SECONDS = 600
RESET_TOKEN_TTL_SECONDS = 900


def _cleanup_expired() -> None:
    now = time.time()
    for k in [k for k, (_, exp) in _otp_store.items() if exp < now]:
        _otp_store.pop(k, None)
    for k in [k for k, (_, exp) in _reset_tokens.items() if exp < now]:
        _reset_tokens.pop(k, None)


# ============================================================
# ✨ دالة إدخال آمنة تتكيف مع أعمدة sync_* تلقائياً
# ============================================================
def _register_device_safe(
    db: Session,
    parent_id: int,
    device_token: str,
    device_type: str | None,
    app_version: str | None,
) -> None:
    """تسجيل الجهاز بأمان — لا يفشل تسجيل الدخول أبداً."""
    try:
        now = datetime.utcnow()
        token = (device_token or "")[:255]

        # 1) هل الجهاز موجود مسبقاً؟
        existing_id = db.execute(
            text(
                "SELECT id FROM parent_devices "
                "WHERE parent_id = :pid AND device_token = :tok LIMIT 1"
            ),
            {"pid": parent_id, "tok": token},
        ).scalar()

        if existing_id:
            sets, extra = build_sync_update_set(db, "parent_devices")
            set_clause = ", ".join(["last_login = :now", "is_active = TRUE",
                                     "app_version = :ver", *sets])
            sql = f"UPDATE parent_devices SET {set_clause} WHERE id = :id"
            db.execute(text(sql), {
                "now": now, "ver": app_version, "id": existing_id, **extra
            })
            db.commit()
            logger.info("Device updated: id=%s parent=%s", existing_id, parent_id)
            return

        # 2) جهاز جديد — جهّز القيم مع أعمدة sync
        values = {
            "parent_id": parent_id,
            "device_token": token,
            "device_type": device_type,
            "app_version": app_version,
            "last_login": now,
            "is_active": True,
        }
        values = fill_sync_columns_for_insert(db, "parent_devices", values)

        cols_str = ", ".join(values.keys())
        placeholders = ", ".join(f":{k}" for k in values.keys())

        db.execute(
            text(f"INSERT INTO parent_devices ({cols_str}) VALUES ({placeholders})"),
            values,
        )
        db.commit()
        logger.info("Device registered: parent=%s cols=%s",
                    parent_id, list(values.keys()))

    except Exception as exc:
        db.rollback()
        logger.warning("Device registration failed (non-fatal): %s", exc)


# ============================================================
# Login
# ============================================================
@router.post("/login")
def login(body: LoginRequest, db: Session = Depends(get_db)):
    parent = db.execute(
        select(Parent).where(Parent.primary_phone == body.phone.strip())
    ).scalar_one_or_none()

    if not parent:
        raise HTTPException(status_code=401, detail="رقم الهاتف غير مسجل")

    if not verify_password(body.password, parent.password_hash):
        raise HTTPException(status_code=401, detail="كلمة المرور غير صحيحة")

    access_token, expires_in = create_access_token(parent.id, parent.full_name)
    refresh_token = create_refresh_token(parent.id)

    # ✅ تسجيل الجهاز (اختياري، لا يوقف تسجيل الدخول)
    if body.device_token:
        _register_device_safe(
            db=db,
            parent_id=parent.id,
            device_token=body.device_token,
            device_type=body.device_type,
            app_version=body.app_version,
        )

    return ok(
        {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_in": expires_in,
            "parent_id": parent.id,
            "full_name": parent.full_name,
        },
        "تم تسجيل الدخول بنجاح",
    )


# ============================================================
# Refresh
# ============================================================
@router.post("/refresh")
def refresh(body: RefreshRequest, db: Session = Depends(get_db)):
    payload = decode_token(body.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Refresh token غير صالح")

    parent_id = payload.get("sub")
    parent = db.get(Parent, int(parent_id)) if parent_id else None
    if not parent:
        raise HTTPException(status_code=401, detail="الحساب غير موجود")

    access_token, expires_in = create_access_token(parent.id, parent.full_name)
    new_refresh = create_refresh_token(parent.id)

    return ok(
        {
            "access_token": access_token,
            "refresh_token": new_refresh,
            "expires_in": expires_in,
        }
    )


# ============================================================
# Logout
# ============================================================
@router.post("/logout")
def logout(
    parent: Parent = Depends(get_current_parent),
    db: Session = Depends(get_db),
):
    try:
        db.execute(
            text("UPDATE parent_devices SET is_active = FALSE WHERE parent_id = :pid"),
            {"pid": parent.id},
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.warning("Logout devices update failed: %s", exc)
    return ok(True, "تم تسجيل الخروج")


# ============================================================
# Forgot Password
# ============================================================
@router.post("/forgot-password")
def forgot_password(body: ForgotPasswordRequest, db: Session = Depends(get_db)):
    _cleanup_expired()

    parent = db.execute(
        select(Parent).where(Parent.primary_phone == body.phone.strip())
    ).scalar_one_or_none()

    if parent:
        otp = f"{random.randint(100000, 999999)}"
        _otp_store[body.phone.strip()] = (otp, time.time() + OTP_TTL_SECONDS)
        logger.info("OTP for %s: %s", body.phone, otp)

    return ok(True, "سيتم إرسال رمز التحقق إن كان الرقم مسجلاً")


@router.post("/verify-otp")
def verify_otp(body: VerifyOtpRequest, db: Session = Depends(get_db)):
    _cleanup_expired()

    entry = _otp_store.get(body.phone.strip())
    if not entry:
        raise HTTPException(status_code=400, detail="لم يُطلب رمز لهذا الرقم")

    stored_otp, expires = entry
    if time.time() > expires:
        _otp_store.pop(body.phone.strip(), None)
        raise HTTPException(status_code=400, detail="انتهت صلاحية الرمز")

    if stored_otp != body.otp.strip():
        raise HTTPException(status_code=400, detail="رمز التحقق غير صحيح")

    parent = db.execute(
        select(Parent).where(Parent.primary_phone == body.phone.strip())
    ).scalar_one_or_none()

    _otp_store.pop(body.phone.strip(), None)

    if not parent:
        raise HTTPException(status_code=400, detail="الحساب غير موجود")

    reset_token = secrets.token_urlsafe(32)
    _reset_tokens[reset_token] = (parent.id, time.time() + RESET_TOKEN_TTL_SECONDS)

    return ok({"reset_token": reset_token, "expires_in": RESET_TOKEN_TTL_SECONDS})


@router.post("/reset-password")
def reset_password(body: ResetPasswordRequest, db: Session = Depends(get_db)):
    _cleanup_expired()

    entry = _reset_tokens.get(body.reset_token)
    if not entry:
        raise HTTPException(status_code=400, detail="Reset token غير صالح")

    parent_id, expires = entry
    if time.time() > expires:
        _reset_tokens.pop(body.reset_token, None)
        raise HTTPException(status_code=400, detail="انتهت صلاحية التوكن")

    if len(body.new_password) < 8:
        raise HTTPException(status_code=400, detail="كلمة المرور قصيرة")

    parent = db.get(Parent, parent_id)
    if not parent:
        raise HTTPException(status_code=400, detail="الحساب غير موجود")

    parent.password_hash = hash_password(body.new_password)
    db.commit()
    _reset_tokens.pop(body.reset_token, None)

    return ok(True, "تم تعيين كلمة المرور بنجاح")


# ============================================================
# Devices
# ============================================================
@router.post("/devices/register")
def register_device(
    body: DeviceRegisterRequest,
    parent: Parent = Depends(get_current_parent),
    db: Session = Depends(get_db),
):
    _register_device_safe(
        db=db,
        parent_id=parent.id,
        device_token=body.device_token,
        device_type=body.device_type,
        app_version=body.app_version,
    )
    return ok(True)


@router.post("/devices/unregister")
def unregister_device(
    body: DeviceRegisterRequest,
    parent: Parent = Depends(get_current_parent),
    db: Session = Depends(get_db),
):
    try:
        db.execute(
            text(
                "UPDATE parent_devices SET is_active = FALSE "
                "WHERE parent_id = :pid AND device_token = :tok"
            ),
            {"pid": parent.id, "tok": body.device_token[:255]},
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.warning("Unregister failed: %s", exc)
    return ok(True)
