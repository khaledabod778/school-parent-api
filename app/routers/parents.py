from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.deps import get_current_parent, get_db
from app.models import Parent
from app.security import hash_password, verify_password
from app.utils import to_str, ok

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
    if body.secondary_phone is not None:
        parent.secondary_phone = body.secondary_phone.strip() or None
    if body.address is not None:
        parent.address = body.address.strip() or None
    if body.job is not None:
        parent.job = body.job.strip() or None
    db.commit()
    db.refresh(parent)
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

    parent.password_hash = hash_password(body.new_password)
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