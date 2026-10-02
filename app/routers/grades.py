from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.deps import get_db, get_owned_student
from app.models import MonthlyEvaluation, Student, Subject, TermExamScore
from app.utils import ok, to_float

router = APIRouter(prefix="/students", tags=["Grades"])


# ============================================================
# Helpers
# ============================================================

def _student_ids_in_section(db: Session, student: Student) -> list[int]:
    """معرّفات طلاب نفس الشعبة + السنة."""
    if not student.section_id or not student.academic_year_id:
        return [student.id]
    rows = db.execute(
        select(Student.id).where(
            Student.section_id == student.section_id,
            Student.academic_year_id == student.academic_year_id,
        )
    ).scalars().all()
    return list(rows) or [student.id]


def _student_ids_in_grade(db: Session, student: Student) -> list[int]:
    """معرّفات طلاب نفس الصف (كل الشعب)."""
    if not student.grade_id or not student.academic_year_id:
        return [student.id]
    rows = db.execute(
        select(Student.id).where(
            Student.grade_id == student.grade_id,
            Student.academic_year_id == student.academic_year_id,
        )
    ).scalars().all()
    return list(rows) or [student.id]


def _calculate_rank(scores: dict[int, float], target_id: int) -> tuple[int | None, int]:
    """يحسب ترتيب الطالب (تنازلياً)."""
    if not scores:
        return None, 0
    sorted_items = sorted(scores.items(), key=lambda x: -x[1])
    for idx, (sid, _) in enumerate(sorted_items, start=1):
        if sid == target_id:
            return idx, len(scores)
    return None, len(scores)


def _monthly_scores_in_section(
    db: Session, student: Student, term: int, month: int
) -> dict[int, float]:
    """مجموع كل المواد لكل طالب في الشعبة، لشهر معين."""
    ids = _student_ids_in_section(db, student)
    total_expr = (
        func.coalesce(MonthlyEvaluation.written_score, 0)
        + func.coalesce(MonthlyEvaluation.oral_score, 0)
        + func.coalesce(MonthlyEvaluation.homework_score, 0)
        + func.coalesce(MonthlyEvaluation.attendance_score, 0)
    )
    rows = db.execute(
        select(
            MonthlyEvaluation.student_id,
            func.sum(total_expr).label("total"),
        )
        .where(
            MonthlyEvaluation.student_id.in_(ids),
            MonthlyEvaluation.term == term,
            MonthlyEvaluation.month == month,
        )
        .group_by(MonthlyEvaluation.student_id)
    ).all()
    return {r.student_id: float(r.total or 0) for r in rows}


def _subject_term_total(
    db: Session, student_id: int, subject_id: int, term: int
) -> float:
    """مجموع مادة واحدة في فصل (محصلة 20 + نهاية فصل 30)."""
    monthly_rows = db.execute(
        select(MonthlyEvaluation).where(
            MonthlyEvaluation.student_id == student_id,
            MonthlyEvaluation.subject_id == subject_id,
            MonthlyEvaluation.term == term,
        )
    ).scalars().all()

    monthly_total = sum(float(r.total_month_score) for r in monthly_rows)
    months_count = len(monthly_rows)
    coursework = (monthly_total / months_count / 5.0) if months_count > 0 else 0.0

    exam = db.execute(
        select(TermExamScore.exam_score).where(
            TermExamScore.student_id == student_id,
            TermExamScore.subject_id == subject_id,
            TermExamScore.term == term,
        )
    ).scalar() or 0

    return coursework + float(exam)


def _student_term_total(db: Session, student_id: int, term: int) -> float:
    """مجموع كل المواد للطالب في فصل."""
    monthly_ids = db.execute(
        select(MonthlyEvaluation.subject_id)
        .where(
            MonthlyEvaluation.student_id == student_id,
            MonthlyEvaluation.term == term,
        )
        .distinct()
    ).scalars().all()
    exam_ids = db.execute(
        select(TermExamScore.subject_id)
        .where(
            TermExamScore.student_id == student_id,
            TermExamScore.term == term,
        )
        .distinct()
    ).scalars().all()
    subject_ids = set(monthly_ids) | set(exam_ids)

    return sum(_subject_term_total(db, student_id, sid, term) for sid in subject_ids)


def _student_final_total(db: Session, student_id: int) -> float:
    """المجموع النهائي (فصل1 + فصل2)."""
    return _student_term_total(db, student_id, 1) + _student_term_total(db, student_id, 2)


# ============================================================
# Monthly grades
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
            MonthlyEvaluation.term.desc(), MonthlyEvaluation.month.desc()
        ).limit(1)
        row = db.execute(stmt).first()
        if not row:
            return ok(None)
        eval_, subj = row
        return ok({
            "subject_name": subj.subject_name,
            "total_month_score": to_float(eval_.total_month_score),
            "max_score": to_float(subj.max_score or 100),
            "month": eval_.month,
            "term": eval_.term,
            "grade": _grade_label(
                to_float(eval_.total_month_score),
                to_float(subj.max_score or 100),
            ),
        })

    stmt = stmt.order_by(MonthlyEvaluation.subject_id, MonthlyEvaluation.month)
    rows = db.execute(stmt).all()

    items = [
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

    # ✅ الترتيب على مستوى الشعبة
    rank, class_size = None, 0
    if term is not None and month is not None:
        scores = _monthly_scores_in_section(db, student, term, month)
        rank, class_size = _calculate_rank(scores, student.id)

    return ok({
        "items": items,
        "rank": rank,
        "class_size": class_size,
    })


# ============================================================
# Term grades
# ============================================================

@router.get("/{student_id}/grades/term")
def term_grades(
    student: Student = Depends(get_owned_student),
    db: Session = Depends(get_db),
    term: int = Query(...),
):
    monthly_ids = db.execute(
        select(MonthlyEvaluation.subject_id)
        .where(
            MonthlyEvaluation.student_id == student.id,
            MonthlyEvaluation.term == term,
        ).distinct()
    ).scalars().all()
    exam_ids = db.execute(
        select(TermExamScore.subject_id)
        .where(
            TermExamScore.student_id == student.id,
            TermExamScore.term == term,
        ).distinct()
    ).scalars().all()
    subject_ids = sorted(set(monthly_ids) | set(exam_ids))

    items: list[dict] = []
    if subject_ids:
        subjects = db.execute(
            select(Subject).where(Subject.id.in_(subject_ids)).order_by(Subject.id)
        ).scalars().all()

        for subj in subjects:
            monthly_rows = db.execute(
                select(MonthlyEvaluation).where(
                    MonthlyEvaluation.student_id == student.id,
                    MonthlyEvaluation.subject_id == subj.id,
                    MonthlyEvaluation.term == term,
                )
            ).scalars().all()

            monthly_total = sum(float(r.total_month_score) for r in monthly_rows)
            months_count = len(monthly_rows)
            coursework = (monthly_total / months_count / 5.0) if months_count > 0 else 0.0

            exam = db.execute(
                select(TermExamScore.exam_score).where(
                    TermExamScore.student_id == student.id,
                    TermExamScore.subject_id == subj.id,
                    TermExamScore.term == term,
                )
            ).scalar() or 0

            items.append({
                "subject_id": subj.id,
                "subject_name": subj.subject_name,
                "coursework_score": round(coursework, 2),
                "coursework_max": 20.0,
                "exam_score": float(exam),
                "exam_max": 30.0,
                "total_score": round(coursework + float(exam), 2),
                "total_max": 50.0,
                "term": term,
            })

    # ✅ الترتيب على مستوى الشعبة
    section_ids = _student_ids_in_section(db, student)
    scores = {sid: _student_term_total(db, sid, term) for sid in section_ids}
    rank, class_size = _calculate_rank(scores, student.id)

    return ok({
        "items": items,
        "rank": rank,
        "class_size": class_size,
    })


# ============================================================
# Final grades
# ============================================================

@router.get("/{student_id}/grades/final")
def final_grades(
    student: Student = Depends(get_owned_student),
    db: Session = Depends(get_db),
):
    monthly_ids = db.execute(
        select(MonthlyEvaluation.subject_id)
        .where(MonthlyEvaluation.student_id == student.id).distinct()
    ).scalars().all()
    exam_ids = db.execute(
        select(TermExamScore.subject_id)
        .where(TermExamScore.student_id == student.id).distinct()
    ).scalars().all()
    subject_ids = sorted(set(monthly_ids) | set(exam_ids))

    subject_rows = []
    total_score = 0.0
    total_max = 0.0

    if subject_ids:
        subjects = db.execute(
            select(Subject).where(Subject.id.in_(subject_ids)).order_by(Subject.id)
        ).scalars().all()

        for subj in subjects:
            t1 = _subject_term_total(db, student.id, subj.id, 1)
            t2 = _subject_term_total(db, student.id, subj.id, 2)
            final = t1 + t2
            subject_rows.append({
                "subject_id": subj.id,
                "subject_name": subj.subject_name,
                "term1_total": round(t1, 2),
                "term2_total": round(t2, 2),
                "final_total": round(final, 2),
                "max_score": 100.0,
                "grade": _grade_label(final, 100.0),
            })
            total_score += final
            total_max += 100.0

    percentage = (total_score / total_max * 100) if total_max else 0.0
    overall = _overall_grade(percentage)
    final_result = "ناجح" if percentage >= 50 else "راسب"

    # ✅ الترتيب على مستوى الصف (كل الشعب)
    grade_ids = _student_ids_in_grade(db, student)
    scores = {sid: _student_final_total(db, sid) for sid in grade_ids}
    rank, class_size = _calculate_rank(scores, student.id)

    return ok({
        "subjects": subject_rows,
        "total_score": round(total_score, 2),
        "total_max": round(total_max, 2),
        "percentage": round(percentage, 2),
        "overall_grade": overall,
        "class_rank": rank,
        "class_size": class_size,
        "final_result": final_result,
    })


# ============================================================
# Labels
# ============================================================

def _grade_label(score: float, max_score: float) -> str:
    if max_score <= 0:
        return "—"
    p = score / max_score * 100
    if p >= 90: return "ممتاز"
    if p >= 80: return "جيد جداً"
    if p >= 70: return "جيد"
    if p >= 50: return "مقبول"
    return "راسب"


def _overall_grade(p: float) -> str:
    if p >= 90: return "ممتاز"
    if p >= 80: return "جيد جداً"
    if p >= 70: return "جيد"
    if p >= 50: return "مقبول"
    return "راسب"
