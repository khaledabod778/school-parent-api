from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Parent, Student
from app.security import decode_token

security_scheme = HTTPBearer(auto_error=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_parent(
    credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme),
    db: Session = Depends(get_db),
) -> Parent:
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="مطلوب تسجيل الدخول",
        )
    payload = decode_token(credentials.credentials)
    if not payload or payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="التوكن غير صالح أو منتهي",
        )
    parent_id = payload.get("sub")
    if not parent_id:
        raise HTTPException(status_code=401, detail="توكن غير صالح")

    parent = db.get(Parent, int(parent_id))
    if not parent:
        raise HTTPException(status_code=401, detail="الحساب غير موجود")
    return parent


def get_owned_student(
    student_id: int,
    parent: Parent = Depends(get_current_parent),
    db: Session = Depends(get_db),
) -> Student:
    student = db.get(Student, student_id)
    if not student:
        raise HTTPException(status_code=404, detail="الطالب غير موجود")
    if student.parent_id != parent.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="غير مصرح بالوصول لهذا الطالب",
        )
    return student