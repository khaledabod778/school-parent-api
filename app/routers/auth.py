import logging
import random
import time

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

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
# تخزين OTP في الذاكرة (يعمل مع instance واحد على Railway)
# ============================================================
_otp_store: dict[str, tuple[str, float]] = {}  # phone -> (otp, expires_at)
_reset_tokens: dict[str, tuple[int, float]] = {}  # token -> (parent_id, expires_at)
OTP_TTL_SECONDS = 600  # 10 دقائق
RESET_TOKEN_TTL_SECONDS = 900  # 15 دقيقة


def _cleanup_expired() -> None:
    now = time.time()
    for k in [k for k, (_, exp) in _otp_store.items() if exp < now]:
        _otp_store.pop(k, None)
    for k in [k for k, (_, exp) in _reset_tokens.items() if exp < now]:
        _reset_tokens.pop(k, None)


# ============================================================
# Login
# ============================================================
@router.post("/login")
def login(body: LoginRequest, db: Session = Depends(get_db)):
    parent = db.execute(
        select(Parent).where(Parent.primary_phone == body.phone.strip())
    ).scalar_one_or_none()

    # ✅ استخدم HTTPException بدل return success=False
    if not parent:
        raise HTTPException(status_code=401, detail="رقم الهاتف غير مسجل")

    if not verify_password(body.password, parent.password_hash):
        raise HTTPException(status_code=401, detail="كلمة المرور غير صحيحة")

    access_token, expires_in = create_access_token(parent.id, parent.full_name)
    refresh_token = create_refresh_token(parent.id)

    # تسجيل الجهاز
    if body.device_token:
        from datetime import datetime
        existing = db.execute(
            select(ParentDevice).where(
                ParentDevice.parent_id == parent.id,
                ParentDevice.device_token == body.device_token,
            )
        ).scalar_one_or_none()

        now = datetime.utcnow()
        if existing:
            existing.last_login = now
            existing.is_active = True
            existing.app_version = body.app_version or existing.app_version
        else:
            db.add(
                ParentDevice(
                    parent_id=parent.id,
                    device_token=body.device_token,
                    device_type=body.device_type,
                    app_version=body.app_version,
                    last_login=now,
                    is_active=True,
                )
            )
        db.commit()

    # ✅ الرد الناجح فقط
    return ok({
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_in": expires_in,
        "parent_id": parent.id,
        "full_name": parent.full_name,
    }, "تم تسجيل الدخول بنجاح")

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
    # تعطيل كل الأجهزة المرتبطة بهذا المستخدم
    db.query(ParentDevice).filter(ParentDevice.parent_id == parent.id).update(
        {"is_active": False}
    )
    db.commit()
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

    # للأمان: لا نكشف وجود الرقم من عدمه
    if parent:
        otp = f"{random.randint(100000, 999999)}"
        _otp_store[body.phone.strip()] = (otp, time.time() + OTP_TTL_SECONDS)
        logger.info("OTP for %s: %s", body.phone, otp)
        # TODO: أرسل OTP عبر SMS هنا (Twilio / Unifonic / ...)

    return ok(True, "سيتم إرسال رمز التحقق إن كان الرقم مسجلاً")


@router.post("/verify-otp")
def verify_otp(body: VerifyOtpRequest):
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

    # نجاح
    _otp_store.pop(body.phone.strip(), None)
    import secrets
    reset_token = secrets.token_urlsafe(32)
    _reset_tokens[reset_token] = (0, time.time() + RESET_TOKEN_TTL_SECONDS)
    # parent_id سيُحدد لاحقاً عند reset-password

    return ok(
        {"reset_token": reset_token, "expires_in": RESET_TOKEN_TTL_SECONDS}
    )


@router.post("/reset-password")
def reset_password(body: ResetPasswordRequest, db: Session = Depends(get_db)):
    _cleanup_expired()

    entry = _reset_tokens.get(body.reset_token)
    if not entry:
        raise HTTPException(status_code=400, detail="Reset token غير صالح")

    _, expires = entry
    if time.time() > expires:
        _reset_tokens.pop(body.reset_token, None)
        raise HTTPException(status_code=400, detail="انتهت صلاحية التوكن")

    if len(body.new_password) < 8:
        raise HTTPException(status_code=400, detail="كلمة المرور قصيرة")

    # نستخدم آخر phone تم التحقق منه — لكن عملياً نحتاج تخزين phone
    # الحل: نبحث عن الـ parent عبر آخر OTP
    # (نسخة مبسطة: نخزّن phone في _reset_tokens مع parent_id)

    # الأفضل: تعديل verify_otp لتخزين parent_id
    # هنا نفترض أن reset_token صالح ونطلب من المستخدم إدخال phone مرة أخرى
    # لتبسيط: نأخذ parent_id من التوكن (لم نخزنه). سنعيد خطأ.
    raise HTTPException(
        status_code=400,
        detail="يرجى إعادة تعيين كلمة المرور من البداية",
    )




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

    import secrets
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
    from datetime import datetime
    existing = db.execute(
        select(ParentDevice).where(
            ParentDevice.parent_id == parent.id,
            ParentDevice.device_token == body.device_token,
        )
    ).scalar_one_or_none()

    now = datetime.utcnow()
    if existing:
        existing.last_login = now
        existing.is_active = True
        existing.app_version = body.app_version or existing.app_version
    else:
        db.add(
            ParentDevice(
                parent_id=parent.id,
                device_token=body.device_token,
                device_type=body.device_type,
                app_version=body.app_version,
                last_login=now,
                is_active=True,
            )
        )
    db.commit()
    return ok(True)


@router.post("/devices/unregister")
def unregister_device(
    body: DeviceRegisterRequest,
    parent: Parent = Depends(get_current_parent),
    db: Session = Depends(get_db),
):
    db.query(ParentDevice).filter(
        ParentDevice.parent_id == parent.id,
        ParentDevice.device_token == body.device_token,
    ).update({"is_active": False})
    db.commit()
    return ok(True)
