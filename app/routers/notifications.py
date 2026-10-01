from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.deps import get_current_parent, get_db
from app.models import Notification, NotificationLog, Parent
from app.utils import ok, to_str

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
    log = db.execute(
        select(NotificationLog).where(
            NotificationLog.notification_id == notification_id,
            NotificationLog.parent_id == parent.id,
        )
    ).scalar_one_or_none()

    if not log:
        raise HTTPException(status_code=404, detail="الإشعار غير موجود")

    log.read_at = datetime.utcnow()
    log.delivery_status = "read"
    db.commit()
    return ok(True)


@router.put("/read-all")
def mark_all_read(
    parent: Parent = Depends(get_current_parent),
    db: Session = Depends(get_db),
):
    now = datetime.utcnow()
    db.query(NotificationLog).filter(
        NotificationLog.parent_id == parent.id,
        NotificationLog.read_at.is_(None),
    ).update({"read_at": now, "delivery_status": "read"})
    db.commit()
    return ok(True)