"""خدمة إرسال الإشعارات الفورية عبر Firebase Cloud Messaging.

معطّلة افتراضياً. لتفعيلها:
  1. ضع ملف Service Account JSON باسم firebase-credentials.json في جذر المشروع.
  2. ارفع FCM_ENABLED=true في متغيرات البيئة.
"""
import logging
from pathlib import Path

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_initialized = False


def init_fcm() -> None:
    global _initialized
    if _initialized or not settings.fcm_enabled:
        return
    try:
        import firebase_admin
        from firebase_admin import credentials

        cred_path = settings.fcm_credentials_path or "firebase-credentials.json"
        if not Path(cred_path).exists():
            logger.warning("FCM credentials not found at %s. Skipping.", cred_path)
            return

        if not firebase_admin._apps:
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred)
        _initialized = True
        logger.info("FCM initialized successfully")
    except Exception as exc:
        logger.exception("Failed to initialize FCM: %s", exc)


def send_to_tokens(
    tokens: list[str],
    title: str,
    body: str,
    data: dict[str, str] | None = None,
) -> None:
    """يرسل إشعاراً لمجموعة توكنات."""
    if not settings.fcm_enabled or not _initialized or not tokens:
        return
    try:
        from firebase_admin import messaging

        message = messaging.MulticastMessage(
            notification=messaging.Notification(title=title, body=body),
            data=data or {},
            tokens=tokens,
        )
        response = messaging.send_each_for_multicast(message)
        logger.info(
            "FCM sent: %d success, %d failure",
            response.success_count,
            response.failure_count,
        )
    except Exception as exc:
        logger.exception("FCM send failed: %s", exc)