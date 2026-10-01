from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.deps import get_current_parent, get_db
from app.models import Notification, NotificationLog, Parent
from app.utils import ok, to_str
from sqlalchemy import func, inspect, select, text
router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("")
def list_notifications(
    parent: Parent = Depends(get_current_parent),
    db: Session = Depends(get_db),
    type: str | None = Query(None),
    read: bool | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, le=100),
):
    stmt = (
        select(NotificationLog, Notification)
        .join(Notification, NotificationLog.notification_id == Notification.id)
        .where(NotificationLog.parent_id == parent.id)
    )

    if type and type != "all":
        # map: financial → payment/fee_due, academic → attendance/homework/behavior/grades_*, etc.
        if type == "financial":
            stmt = stmt.where(Notification.notification_type.in_(["payment", "fee_due"]))
        elif type == "academic":
            stmt = stmt.where(
                Notification.notification_type.in_(
                    ["attendance", "homework", "behavior", "grades_monthly", "grades_term"]
                )
            )
        elif type == "admin":
            stmt = stmt.where(Notification.notification_type == "admin")
        elif type == "general":
            stmt = stmt.where(
                Notification.notification_type.in_(["general", "broadcast"])
            )

    if read is True:
        stmt = stmt.where(NotificationLog.read_at.isnot(None))
    elif read is False:
        stmt = stmt.where(NotificationLog.read_at.is_(None))

    stmt = stmt.order_by(Notification.created_at.desc())
    stmt = stmt.offset((page - 1) * limit).limit(limit)

    rows = db.execute(stmt).all()

    return ok(
        [
            {
                "id": n.id,
                "title": n.title,
                "message": n.message,
                "notification_type": n.notification_type,
                "created_at": to_str(n.created_at),
                "sent_at": to_str(n.sent_at),
                "is_read": log.read_at is not None,
                "target_type": n.target_type,
                "payload": None,
            }
            for log, n in rows
        ]
    )


@router.get("/unread-count")
def unread_count(
    parent: Parent = Depends(get_current_parent),
    db: Session = Depends(get_db),
):
    count = db.execute(
        select(func.count(NotificationLog.id)).where(
            NotificationLog.parent_id == parent.id,
            NotificationLog.read_at.is_(None),
        )
    ).scalar() or 0
    return ok({"count": int(count)})


@router.put("/{notification_id}/read")
def mark_read(
    notification_id: int,
    parent: Parent = Depends(get_current_parent),
    db: Session = Depends(get_db),
):
    try:
        now = datetime.utcnow()

        # تحقق أن السجل موجود
        exists = db.execute(
            text(
                "SELECT id FROM notification_logs "
                "WHERE notification_id = :nid AND parent_id = :pid LIMIT 1"
            ),
            {"nid": notification_id, "pid": parent.id},
        ).scalar()

        if not exists:
            raise HTTPException(status_code=404, detail="الإشعار غير موجود")

        # ✅ تحديث ديناميكي — يحدّث أعمدة sync إذا وجدت
        inspector = inspect(db.bind)
        columns = {c["name"] for c in inspector.get_columns("notification_logs")}

        sets = ["read_at = :now", "delivery_status = 'read'"]
        params = {"now": now, "id": exists}

        if "sync_updated_at" in columns:
            sets.append("sync_updated_at = :now")
        if "sync_version" in columns:
            # زيادة العداد
            sets.append("sync_version = COALESCE(sync_version, 0) + 1")
        if "updated_at" in columns:
            sets.append("updated_at = :now")

        sql = f"UPDATE notification_logs SET {', '.join(sets)} WHERE id = :id"
        db.execute(text(sql), params)
        db.commit()
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        logger.warning("Mark read failed: %s", exc)
        # لا نُفشل العملية
    return ok(True)


@router.put("/read-all")
def mark_all_read(
    parent: Parent = Depends(get_current_parent),
    db: Session = Depends(get_db),
):
    try:
        now = datetime.utcnow()
        inspector = inspect(db.bind)
        columns = {c["name"] for c in inspector.get_columns("notification_logs")}

        sets = ["read_at = :now", "delivery_status = 'read'"]
        if "sync_updated_at" in columns:
            sets.append("sync_updated_at = :now")
        if "sync_version" in columns:
            sets.append("sync_version = COALESCE(sync_version, 0) + 1")
        if "updated_at" in columns:
            sets.append("updated_at = :now")

        sql = (
            f"UPDATE notification_logs SET {', '.join(sets)} "
            "WHERE parent_id = :pid AND read_at IS NULL"
        )
        db.execute(text(sql), {"now": now, "pid": parent.id})
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.warning("Read-all failed: %s", exc)
    return ok(True)
