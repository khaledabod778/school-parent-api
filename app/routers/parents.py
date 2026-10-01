from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.deps import get_current_parent, get_db
from app.models import Parent
from app.security import hash_password, verify_password
from app.utils import to_str, ok

from sqlalchemy import text
from app.sync_utils import build_sync_update_set
router = APIRouter(prefix="/parents", tags=["Parents"])


class UpdateProfileRequest(BaseModel):
    secondary_phone: str | None = None
    address: str | None = None
    job: str | None = None


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


@router.get("/me")
def get_me(parent: Parent = Depends(get_current_parent)):
    return ok(
        {
            "id": parent.id,
            "full_name": parent.full_name,
            "primary_phone": parent.primary_phone,
            "secondary_phone": parent.secondary_phone,
            "address": parent.address,
            "job": parent.job,
            "category": parent.category,
        }
    )


@router.put("/me")
def update_me(
    body: UpdateProfileRequest,
    parent: Parent = Depends(get_current_parent),
    db: Session = Depends(get_db),
):
    sets: list[str] = []
    params: dict = {"id": parent.id}

    if body.secondary_phone is not None:
        sets.append("secondary_phone = :sp")
        params["sp"] = body.secondary_phone.strip() or None
    if body.address is not None:
        sets.append("address = :addr")
        params["addr"] = body.address.strip() or None
    if body.job is not None:
        sets.append("job = :job")
        params["job"] = body.job.strip() or None

    if not sets:
        return ok({"id": parent.id}, "لا توجد تغييرات")

    sync_sets, sync_params = build_sync_update_set(db, "parents")
    params.update(sync_params)
    all_sets = sets + sync_sets

    sql = f"UPDATE parents SET {', '.join(all_sets)} WHERE id = :id"
    db.execute(text(sql), params)
    db.commit()
    return ok({"id": parent.id}, "تم حفظ البيانات")


@router.put("/me/change-password")
def change_password(
    body: ChangePasswordRequest,
    parent: Parent = Depends(get_current_parent),
    db: Session = Depends(get_db),
):
    if not verify_password(body.old_password, parent.password_hash):
        raise HTTPException(status_code=400, detail="كلمة المرور الحالية غير صحيحة")

    if len(body.new_password) < 8:
        raise HTTPException(status_code=400, detail="كلمة المرور الجديدة قصيرة")

    new_hash = hash_password(body.new_password)

    sync_sets, sync_params = build_sync_update_set(db, "parents")
    sets = ["password_hash = :ph"] + sync_sets
    params = {"ph": new_hash, "id": parent.id, **sync_params}

    sql = f"UPDATE parents SET {', '.join(sets)} WHERE id = :id"
    db.execute(text(sql), params)
    db.commit()
    return ok(True, "تم تغيير كلمة المرور")
    


@router.get("/me/children")
def get_children(
    parent: Parent = Depends(get_current_parent),
):
    return ok([_student_brief(s) for s in parent.students])


def _student_brief(s):
    return {
        "id": s.id,
        "student_number": s.student_number,
        "full_name": s.full_name,
        "mother_name": s.mother_name,
        "gender": s.gender,
        "nationality": s.nationality,
        "status": s.status,
        "enrollment_type": s.enrollment_type,
        "birth_date": to_str(s.birth_date),
        "grade_id": s.grade_id,
        "grade_name": s.grade.grade_name if s.grade else None,
        "section_id": s.section_id,
        "section_name": s.section.section_name if s.section else None,
        "parent_id": s.parent_id,
        "photo_url": s.photo_url,
        "academic_year_id": s.academic_year_id,
    }
