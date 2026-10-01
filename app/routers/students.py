from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.deps import get_current_parent, get_db, get_owned_student
from app.models import (
    AcademicYear, BehavioralRecord, DailyAttendance, Grade, Homework,
    Section, Student, StudentAcademicHistory, StudentDocument, Subject,
)
from app.utils import ok, to_float, to_str

router = APIRouter(prefix="/students", tags=["Students"])


# ============================================================
# Profile
# ============================================================
@router.get("/{student_id}/profile")
def profile(
    student: Student = Depends(get_owned_student),
):
    return ok(_student_full(student))


# ============================================================
# Attendance
# ============================================================
@router.get("/{student_id}/attendance")
def attendance(
    student: Student = Depends(get_owned_student),
    db: Session = Depends(get_db),
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    status: str | None = Query(None),
):
    stmt = select(DailyAttendance).where(DailyAttendance.student_id == student.id)
    if date_from:
        stmt = stmt.where(DailyAttendance.attendance_date >= date_from)
    if date_to:
        stmt = stmt.where(DailyAttendance.attendance_date <= date_to)
    if status and status not in ("الكل", "all"):
        stmt = stmt.where(DailyAttendance.status == status)
    stmt = stmt.order_by(DailyAttendance.attendance_date.desc())

    rows = db.execute(stmt).scalars().all()
    return ok(
        [
            {
                "id": r.id,
                "attendance_date": to_str(r.attendance_date),
                "status": r.status,
                "notes": r.notes,
            }
            for r in rows
        ]
    )


@router.get("/{student_id}/attendance/summary")
def attendance_summary(
    student: Student = Depends(get_owned_student),
    db: Session = Depends(get_db),
    month: int = Query(...),
    year: int = Query(...),
):
    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)

    rows = db.execute(
        select(DailyAttendance).where(
            DailyAttendance.student_id == student.id,
            DailyAttendance.attendance_date >= start,
            DailyAttendance.attendance_date < end,
        )
    ).scalars().all()

    total = len(rows)
    present = sum(1 for r in rows if r.status == "حاضر")
    absent = sum(1 for r in rows if r.status == "غائب")
    late = sum(1 for r in rows if r.status == "متأخر")
    excused = sum(1 for r in rows if r.status == "غائب بمبرر")
    percentage = (present / total * 100) if total > 0 else 0.0

    return ok(
        {
            "total": total,
            "present": present,
            "absent": absent,
            "late": late,
            "excused": excused,
            "percentage": round(percentage, 1),
            "attendance_percentage": round(percentage, 1),
        }
    )


# ============================================================
# Homeworks
# ============================================================
@router.get("/{student_id}/homeworks")
def homeworks(
    student: Student = Depends(get_owned_student),
    db: Session = Depends(get_db),
    subject_id: int | None = Query(None),
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    upcoming: bool = Query(False),
):
    if not student.grade_id or not student.section_id:
        return ok([])

    stmt = (
        select(Homework, Subject.subject_name)
        .join(Subject, Homework.subject_id == Subject.id)
        .where(
            Homework.grade_id == student.grade_id,
            Homework.section_id == student.section_id,
        )
    )
    if subject_id:
        stmt = stmt.where(Homework.subject_id == subject_id)
    if date_from:
        stmt = stmt.where(Homework.homework_date >= date_from)
    if date_to:
        stmt = stmt.where(Homework.homework_date <= date_to)
    if upcoming:
        stmt = stmt.where(Homework.due_date >= date.today())
    stmt = stmt.order_by(Homework.homework_date.desc()).limit(100)

    rows = db.execute(stmt).all()
    return ok(
        [
            {
                "id": h.id,
                "title": h.title,
                "description": h.description,
                "subject_id": h.subject_id,
                "subject_name": subject_name,
                "homework_date": to_str(h.homework_date),
                "due_date": to_str(h.due_date),
            }
            for h, subject_name in rows
        ]
    )


# ============================================================
# Behavior
# ============================================================
@router.get("/{student_id}/behavior")
def behavior(
    student: Student = Depends(get_owned_student),
    db: Session = Depends(get_db),
    type: str | None = Query(None),
    limit: int = Query(100, le=200),
):
    stmt = select(BehavioralRecord).where(BehavioralRecord.student_id == student.id)
    if type and type not in ("الكل", "all"):
        stmt = stmt.where(BehavioralRecord.behavior_type == type)
    stmt = stmt.order_by(BehavioralRecord.record_date.desc()).limit(limit)

    rows = db.execute(stmt).scalars().all()
    return ok(
        [
            {
                "id": r.id,
                "behavior_type": r.behavior_type,
                "title": r.title,
                "details": r.details,
                "action_taken": r.action_taken,
                "record_date": to_str(r.record_date),
            }
            for r in rows
        ]
    )


# ============================================================
# Documents
# ============================================================
@router.get("/{student_id}/documents")
def documents(
    student: Student = Depends(get_owned_student),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(StudentDocument).where(StudentDocument.student_id == student.id)
    ).scalars().all()
    return ok(
        [
            {
                "id": d.id,
                "student_id": d.student_id,
                "document_type": d.document_type,
                "file_path": d.file_path,
                "uploaded_at": to_str(d.uploaded_at),
            }
            for d in rows
        ]
    )


# ============================================================
# Academic History
# ============================================================
@router.get("/{student_id}/academic-history")
def academic_history(
    student: Student = Depends(get_owned_student),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(StudentAcademicHistory, AcademicYear, Grade, Section)
        .join(AcademicYear, StudentAcademicHistory.academic_year_id == AcademicYear.id)
        .join(Grade, StudentAcademicHistory.grade_id == Grade.id)
        .join(Section, StudentAcademicHistory.section_id == Section.id)
        .where(StudentAcademicHistory.student_id == student.id)
        .order_by(AcademicYear.id.desc())
    ).all()

    result = []
    for h, year, grade, section in rows:
        result.append(
            {
                "id": h.id,
                "academic_year_id": h.academic_year_id,
                "year_name_gregorian": year.year_name_gregorian,
                "year_name_hijri": year.year_name_hijri,
                "grade_name": grade.grade_name,
                "section_name": section.section_name,
                "final_result": h.final_result,
                "promotion_status": h.promotion_status,
                "percentage": None,
                "rank": None,
            }
        )
    return ok(result)


# ============================================================
# Helper
# ============================================================
def _student_full(s: Student):
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
        "birth_village": s.birth_village,
        "birth_district": s.birth_district,
        "birth_governorate": s.birth_governorate,
        "grade_id": s.grade_id,
        "grade_name": s.grade.grade_name if s.grade else None,
        "section_id": s.section_id,
        "section_name": s.section.section_name if s.section else None,
        "parent_id": s.parent_id,
        "photo_url": s.photo_url,
        "academic_year_id": s.academic_year_id,
    }