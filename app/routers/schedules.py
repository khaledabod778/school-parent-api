from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import get_db, get_owned_student
from app.models import (
    Employee, FinalExamSchedule, MonthlyExamSchedule, Student, Subject,
    WeeklySchedule,
)
from app.utils import ok, to_str

router = APIRouter(prefix="/students", tags=["Schedules"])


# ============================================================
# Weekly Schedule
# ============================================================
@router.get("/{student_id}/schedule/weekly")
def weekly_schedule(
    student: Student = Depends(get_owned_student),
    db: Session = Depends(get_db),
    term: int = Query(1),
):
    if not student.section_id:
        return ok([])

    rows = db.execute(
        select(WeeklySchedule, Subject.subject_name, Employee.full_name)
        .outerjoin(Subject, WeeklySchedule.subject_id == Subject.id)
        .outerjoin(Employee, WeeklySchedule.teacher_id == Employee.id)
        .where(
            WeeklySchedule.section_id == student.section_id,
            WeeklySchedule.term == term,
        )
        .order_by(WeeklySchedule.day_of_week, WeeklySchedule.period_number)
    ).all()

    return ok(
        [
            {
                "day": r.day_of_week,
                "period_number": r.period_number,
                "subject_name": subject_name,
                "teacher_name": teacher_name,
            }
            for r, subject_name, teacher_name in rows
        ]
    )


# ============================================================
# Monthly Exams
# ============================================================
@router.get("/{student_id}/schedule/exams/monthly")
def monthly_exams(
    student: Student = Depends(get_owned_student),
    db: Session = Depends(get_db),
    term: int = Query(1),
    month: int = Query(1),
):
    if not student.grade_id:
        return ok([])

    stmt = (
        select(MonthlyExamSchedule, Subject.subject_name)
        .join(Subject, MonthlyExamSchedule.subject_id == Subject.id)
        .where(
            MonthlyExamSchedule.grade_id == student.grade_id,
            MonthlyExamSchedule.term == term,
            MonthlyExamSchedule.month == month,
        )
    )
    if student.section_id:
        stmt = stmt.where(
            (MonthlyExamSchedule.section_id == student.section_id)
            | (MonthlyExamSchedule.section_id.is_(None))
        )
    stmt = stmt.order_by(MonthlyExamSchedule.exam_date)

    rows = db.execute(stmt).all()
    return ok(
        [
            {
                "id": e.id,
                "subject_name": s_name,
                "exam_date": to_str(e.exam_date),
                "day_name": e.day_name,
                "period_number": e.period_number,
            }
            for e, s_name in rows
        ]
    )


# ============================================================
# Final Exams
# ============================================================
@router.get("/{student_id}/schedule/exams/final")
def final_exams(
    student: Student = Depends(get_owned_student),
    db: Session = Depends(get_db),
    term: int = Query(1),
):
    if not student.grade_id:
        return ok([])

    rows = db.execute(
        select(FinalExamSchedule, Subject.subject_name)
        .join(Subject, FinalExamSchedule.subject_id == Subject.id)
        .where(
            FinalExamSchedule.grade_id == student.grade_id,
            FinalExamSchedule.term == term,
        )
        .order_by(FinalExamSchedule.exam_date)
    ).all()

    return ok(
        [
            {
                "id": e.id,
                "subject_name": s_name,
                "exam_date": to_str(e.exam_date),
                "day_name": e.day_name,
                "start_time": e.start_time.strftime("%H:%M") if e.start_time else "",
                "end_time": e.end_time.strftime("%H:%M") if e.end_time else "",
            }
            for e, s_name in rows
        ]
    )