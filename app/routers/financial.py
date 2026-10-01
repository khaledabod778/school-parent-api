from datetime import date, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import get_db, get_owned_student
from app.models import (
    FeeInstallment, Receipt, Student, StudentFee,
)
from app.utils import ok, to_float, to_str

router = APIRouter(prefix="/students", tags=["Financial"])


# ============================================================
# Fees Summary
# ============================================================
@router.get("/{student_id}/fees/summary")
def fees_summary(
    student: Student = Depends(get_owned_student),
    db: Session = Depends(get_db),
):
    fee = db.execute(
        select(StudentFee)
        .where(StudentFee.student_id == student.id)
        .order_by(StudentFee.id.desc())
        .limit(1)
    ).scalar_one_or_none()

    if not fee:
        return ok(
            {
                "current_year_fees": 0,
                "previous_debt": 0,
                "discount_amount": 0,
                "total_required": 0,
                "total_paid": 0,
                "remaining": 0,
                "payment_percentage": 0,
            }
        )

    paid = db.execute(
        select(Receipt).where(
            Receipt.student_id == student.id,
            Receipt.status == "نشط",
        )
    ).scalars().all()
    total_paid = sum(to_float(r.amount_paid) for r in paid)

    net_required = to_float(fee.net_total_required)
    remaining = max(net_required - total_paid, 0)
    pct = (total_paid / net_required * 100) if net_required > 0 else 0.0

    return ok(
        {
            "current_year_fees": to_float(fee.current_year_fees),
            "previous_debt": to_float(fee.previous_debt),
            "discount_amount": to_float(fee.discount_amount),
            "total_required": net_required,
            "total_paid": round(total_paid, 2),
            "remaining": round(remaining, 2),
            "payment_percentage": round(pct, 1),
        }
    )


# ============================================================
# Installments
# ============================================================
@router.get("/{student_id}/fees/installments")
def installments(
    student: Student = Depends(get_owned_student),
    db: Session = Depends(get_db),
):
    fee = db.execute(
        select(StudentFee)
        .where(StudentFee.student_id == student.id)
        .order_by(StudentFee.id.desc())
        .limit(1)
    ).scalar_one_or_none()

    if not fee:
        return ok([])

    rows = db.execute(
        select(FeeInstallment)
        .where(FeeInstallment.student_fee_id == fee.id)
        .order_by(FeeInstallment.installment_number)
    ).scalars().all()

    return ok(
        [
            {
                "id": i.id,
                "installment_type": i.installment_type or "regular",
                "installment_number": i.installment_number,
                "installment_name": i.installment_name,
                "amount": to_float(i.amount),
                "due_date": to_str(i.due_date),
                "is_paid": bool(i.is_paid),
                "paid_amount": to_float(i.paid_amount),
            }
            for i in rows
        ]
    )


# ============================================================
# Nearest Installment
# ============================================================
@router.get("/{student_id}/fees/nearest-installment")
def nearest_installment(
    student: Student = Depends(get_owned_student),
    db: Session = Depends(get_db),
):
    fee = db.execute(
        select(StudentFee)
        .where(StudentFee.student_id == student.id)
        .order_by(StudentFee.id.desc())
        .limit(1)
    ).scalar_one_or_none()

    if not fee:
        return ok(None)

    inst = db.execute(
        select(FeeInstallment)
        .where(
            FeeInstallment.student_fee_id == fee.id,
            FeeInstallment.is_paid.is_(False),
        )
        .order_by(FeeInstallment.due_date)
        .limit(1)
    ).scalar_one_or_none()

    if not inst:
        return ok(None)

    return ok(
        {
            "id": inst.id,
            "name": inst.installment_name,
            "amount": to_float(inst.amount),
            "due_date": to_str(inst.due_date),
            "paid_amount": to_float(inst.paid_amount),
            "is_paid": bool(inst.is_paid),
        }
    )


# ============================================================
# Receipts
# ============================================================
@router.get("/{student_id}/receipts")
def receipts(
    student: Student = Depends(get_owned_student),
    db: Session = Depends(get_db),
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    status: str | None = Query(None),
    payment_method: str | None = Query(None),
    limit: int | None = Query(None, le=200),
):
    stmt = select(Receipt).where(Receipt.student_id == student.id)

    if date_from:
        stmt = stmt.where(Receipt.payment_date >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        stmt = stmt.where(Receipt.payment_date <= datetime.combine(date_to, datetime.max.time()))
    if status:
        if status == "active":
            stmt = stmt.where(Receipt.status == "نشط")
        elif status == "cancelled":
            stmt = stmt.where(Receipt.status == "ملغى")
    if payment_method and payment_method != "الكل":
        stmt = stmt.where(Receipt.payment_method == payment_method)

    stmt = stmt.order_by(Receipt.payment_date.desc())
    if limit:
        stmt = stmt.limit(limit)

    rows = db.execute(stmt).scalars().all()

    return ok(
        [
            {
                "id": r.id,
                "receipt_number": r.receipt_number,
                "student_id": r.student_id,
                "installment_id": r.installment_id,
                "payment_target": r.payment_target or "current_fee",
                "amount_paid": to_float(r.amount_paid),
                "payment_date": to_str(r.payment_date),
                "payment_method": r.payment_method,
                "reference_number": r.reference_number,
                "notes": r.notes,
                "status": r.status or "نشط",
                "cancellation_reason": r.cancellation_reason,
                "created_by_name": None,
            }
            for r in rows
        ]
    )


# ============================================================
# Statement
# ============================================================
@router.get("/{student_id}/statement")
def statement(
    student: Student = Depends(get_owned_student),
    db: Session = Depends(get_db),
):
    fee = db.execute(
        select(StudentFee)
        .where(StudentFee.student_id == student.id)
        .order_by(StudentFee.id.desc())
        .limit(1)
    ).scalar_one_or_none()

    # summary
    if fee:
        paid = db.execute(
            select(Receipt).where(
                Receipt.student_id == student.id, Receipt.status == "نشط"
            )
        ).scalars().all()
        total_paid = sum(to_float(r.amount_paid) for r in paid)
        net_required = to_float(fee.net_total_required)
        remaining = max(net_required - total_paid, 0)
        pct = (total_paid / net_required * 100) if net_required > 0 else 0.0
        summary = {
            "current_year_fees": to_float(fee.current_year_fees),
            "previous_debt": to_float(fee.previous_debt),
            "discount_amount": to_float(fee.discount_amount),
            "total_required": net_required,
            "total_paid": round(total_paid, 2),
            "remaining": round(remaining, 2),
            "payment_percentage": round(pct, 1),
        }
    else:
        summary = {
            "current_year_fees": 0,
            "previous_debt": 0,
            "discount_amount": 0,
            "total_required": 0,
            "total_paid": 0,
            "remaining": 0,
            "payment_percentage": 0,
        }

    # installments
    inst_list = []
    if fee:
        insts = db.execute(
            select(FeeInstallment)
            .where(FeeInstallment.student_fee_id == fee.id)
            .order_by(FeeInstallment.installment_number)
        ).scalars().all()
        inst_list = [
            {
                "id": i.id,
                "installment_type": i.installment_type or "regular",
                "installment_number": i.installment_number,
                "installment_name": i.installment_name,
                "amount": to_float(i.amount),
                "due_date": to_str(i.due_date),
                "is_paid": bool(i.is_paid),
                "paid_amount": to_float(i.paid_amount),
            }
            for i in insts
        ]

    # receipts
    receipts_rows = db.execute(
        select(Receipt)
        .where(Receipt.student_id == student.id)
        .order_by(Receipt.payment_date.desc())
    ).scalars().all()

    receipts_list = [
        {
            "id": r.id,
            "receipt_number": r.receipt_number,
            "student_id": r.student_id,
            "installment_id": r.installment_id,
            "payment_target": r.payment_target or "current_fee",
            "amount_paid": to_float(r.amount_paid),
            "payment_date": to_str(r.payment_date),
            "payment_method": r.payment_method,
            "reference_number": r.reference_number,
            "notes": r.notes,
            "status": r.status or "نشط",
            "cancellation_reason": r.cancellation_reason,
            "created_by_name": None,
        }
        for r in receipts_rows
    ]

    return ok(
        {
            "summary": summary,
            "installments": inst_list,
            "receipts": receipts_list,
        }
    )