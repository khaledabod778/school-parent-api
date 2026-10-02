from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import get_db, get_owned_student
from app.models import (
    AcademicYear, MonthlyEvaluation, Student, Subject, TermExamScore,
)
from app.utils import ok, to_float

router = APIRouter(prefix="/students", tags=["Grades"])


# ============================================================
# Monthly Grades
# ============================================================
@router.get("/{student_id}/grades/monthly")
def monthly_grades(
    student: Student = Depends(get_owned_student),
    db: Session = Depends(get_db),
    term: int | None = Query(None),
    month: int | None = Query(None),
    latest: bool = Query(False),
):
    stmt = (
        select(MonthlyEvaluation, Subject)
        .join(Subject, MonthlyEvaluation.subject_id == Subject.id)
        .where(MonthlyEvaluation.student_id == student.id)
    )
    if term is not None:
        stmt = stmt.where(MonthlyEvaluation.term == term)
    if month is not None:
        stmt = stmt.where(MonthlyEvaluation.month == month)

    if latest:
        stmt = stmt.order_by(
            MonthlyEvaluation.term.desc(),
            MonthlyEvaluation.month.desc(),
        ).limit(1)
        row = db.execute(stmt).first()
        if not row:
            return ok(None)
        eval_, subj = row
        return ok(
            {
                "subject_name": subj.subject_name,
                "total_month_score": to_float(eval_.total_month_score),
                "max_score": to_float(subj.max_score or 100),
                "month": eval_.month,
                "term": eval_.term,
                "grade": _grade_label(
                    to_float(eval_.total_month_score),
                    to_float(subj.max_score or 100),
                ),
            }
        )

    stmt = stmt.order_by(MonthlyEvaluation.subject_id, MonthlyEvaluation.month)
    rows = db.execute(stmt).all()

    return ok(
        [
            {
                "subject_id": e.subject_id,
                "subject_name": s.subject_name,
                "written_score": to_float(e.written_score),
                "oral_score": to_float(e.oral_score),
                "homework_score": to_float(e.homework_score),
                "attendance_score": to_float(e.attendance_score),
                "total_month_score": to_float(e.total_month_score),
                "max_score": to_float(s.max_score or 100),
                "month": e.month,
                "term": e.term,
            }
            for e, s in rows
        ]
    )


# ============================================================
# Term Grades
# ============================================================
@router.get("/{student_id}/grades/term")
@router.get("/{student_id}/grades/term")
def term_grades(
    student: Student = Depends(get_owned_student),
    db: Session = Depends(get_db),
    term: int = Query(...),
):
    subjects = db.execute(select(Subject).order_by(Subject.id)).scalars().all()

    result = []
    for subj in subjects:
        # ✅ احسب محصلة الأعمال من Python
        monthly_rows = db.execute(
            select(MonthlyEvaluation).where(
                MonthlyEvaluation.student_id == student.id,
                MonthlyEvaluation.subject_id == subj.id,
                MonthlyEvaluation.term == term,
            )
        ).scalars().all()

        monthly_total = sum(float(r.total_month_score) for r in monthly_rows)
        coursework_score = monthly_total / 3.0 if monthly_rows else 0.0

        # نهاية الفصل
        exam_score = db.execute(
            select(TermExamScore.exam_score).where(
                TermExamScore.student_id == student.id,
                TermExamScore.subject_id == subj.id,
                TermExamScore.term == term,
            )
        ).scalar() or 0

        coursework_max = 20.0
        exam_max = 30.0
        total = coursework_score + float(exam_score)
        total_max = 50.0

        result.append(
            {
                "subject_id": subj.id,
                "subject_name": subj.subject_name,
                "coursework_score": round(coursework_score, 2),
                "coursework_max": coursework_max,
                "exam_score": float(exam_score),
                "exam_max": exam_max,
                "total_score": round(total, 2),
                "total_max": total_max,
                "term": term,
            }
        )
    return ok(result)


# ============================================================
# Final Grades
# ============================================================
@router.get("/{student_id}/grades/final")
def final_grades(
    student: Student = Depends(get_owned_student),
    db: Session = Depends(get_db),
):
    subjects = db.execute(select(Subject).order_by(Subject.id)).scalars().all()

    subject_rows = []
    total_score = 0.0
    total_max = 0.0

    for subj in subjects:
        t1 = _term_total(db, student.id, subj.id, term=1)
        t2 = _term_total(db, student.id, subj.id, term=2)
        final = t1 + t2
        max_score = 100.0

        subject_rows.append(
            {
                "subject_id": subj.id,
                "subject_name": subj.subject_name,
                "term1_total": round(t1, 2),
                "term2_total": round(t2, 2),
                "final_total": round(final, 2),
                "max_score": max_score,
                "grade": _grade_label(final, max_score),
            }
        )
        total_score += final
        total_max += max_score

    percentage = (total_score / total_max * 100) if total_max else 0.0
    overall = _overall_grade(percentage)
    final_result = (
        "ناجح" if percentage >= 50 else "راسب"
    )

    return ok(
        {
            "subjects": subject_rows,
            "total_score": round(total_score, 2),
            "total_max": round(total_max, 2),
            "percentage": round(percentage, 2),
            "overall_grade": overall,
            "class_rank": None,
            "class_size": None,
            "final_result": final_result,
        }
    )


# ============================================================
# Helpers
# ============================================================


def _term_total(db: Session, student_id: int, subject_id: int, term: int) -> float:
    """
    يحسب مجموع الفصل (محصلة الأعمال + نهاية الفصل).
    يحسب total_month_score في Python بدل الاعتماد على DB.
    """
    from sqlalchemy import select as sa_select

    rows = db.execute(
        sa_select(MonthlyEvaluation).where(
            MonthlyEvaluation.student_id == student_id,
            MonthlyEvaluation.subject_id == subject_id,
            MonthlyEvaluation.term == term,
        )
    ).scalars().all()

    # مجموع كل التقييمات الشهرية (3 أشهر) ثم نقسم على 3 لمتوسط المحصلة
    monthly_total = sum(float(r.total_month_score) for r in rows)
    coursework = monthly_total / 3.0 if rows else 0.0

    exam = db.execute(
        sa_select(TermExamScore.exam_score).where(
            TermExamScore.student_id == student_id,
            TermExamScore.subject_id == subject_id,
            TermExamScore.term == term,
        )
    ).scalar() or 0

    return coursework + float(exam)


def _grade_label(score: float, max_score: float) -> str:
    if max_score <= 0:
        return "—"
    p = score / max_score * 100
    if p >= 90:
        return "ممتاز"
    if p >= 80:
        return "جيد جداً"
    if p >= 70:
        return "جيد"
    if p >= 50:
        return "مقبول"
    return "راسب"


def _overall_grade(percentage: float) -> str:
    if percentage >= 90:
        return "ممتاز"
    if percentage >= 80:
        return "جيد جداً"
    if percentage >= 70:
        return "جيد"
    if percentage >= 50:
        return "مقبول"
    return "راسب"
