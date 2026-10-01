from datetime import date, datetime, time
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, Time,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Parent(Base):
    __tablename__ = "parents"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(150))
    primary_phone: Mapped[str] = mapped_column(String(20), unique=True)
    secondary_phone: Mapped[Optional[str]] = mapped_column(String(20))
    address: Mapped[Optional[str]] = mapped_column(Text)
    job: Mapped[Optional[str]] = mapped_column(String(100))
    category: Mapped[Optional[str]] = mapped_column(String(20), default="عادي")
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    students: Mapped[list["Student"]] = relationship(
        "Student", back_populates="parent", lazy="selectin"
    )


class ParentDevice(Base):
    __tablename__ = "parent_devices"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    parent_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("parents.id", ondelete="CASCADE")
    )
    device_token: Mapped[str] = mapped_column(String(255))
    device_type: Mapped[Optional[str]] = mapped_column(String(20))
    app_version: Mapped[Optional[str]] = mapped_column(String(30))
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class AcademicYear(Base):
    __tablename__ = "academic_years"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    year_name_gregorian: Mapped[str] = mapped_column(String(20))
    year_name_hijri: Mapped[str] = mapped_column(String(20))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[Optional[str]] = mapped_column(String(20))
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False)


class Grade(Base):
    __tablename__ = "grades"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    grade_name: Mapped[str] = mapped_column(String(50))
    stage_name: Mapped[str] = mapped_column(String(50))


class Section(Base):
    __tablename__ = "sections"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    grade_id: Mapped[int] = mapped_column(Integer, ForeignKey("grades.id"))
    section_name: Mapped[str] = mapped_column(String(10))
    capacity: Mapped[int] = mapped_column(Integer, default=30)


class Subject(Base):
    __tablename__ = "subjects"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subject_name: Mapped[str] = mapped_column(String(100))
    min_pass_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    max_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))


class Employee(Base):
    __tablename__ = "employees"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(150))
    job_title: Mapped[str] = mapped_column(String(100))


class Student(Base):
    __tablename__ = "students"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_number: Mapped[str] = mapped_column(String(30), unique=True)
    full_name: Mapped[str] = mapped_column(String(150))
    mother_name: Mapped[Optional[str]] = mapped_column(String(150))
    gender: Mapped[Optional[str]] = mapped_column(String(10))
    nationality: Mapped[Optional[str]] = mapped_column(String(50))
    status: Mapped[Optional[str]] = mapped_column(String(20))
    enrollment_type: Mapped[Optional[str]] = mapped_column(String(20))
    birth_date: Mapped[Optional[date]] = mapped_column(Date)
    birth_village: Mapped[Optional[str]] = mapped_column(String(50))
    birth_district: Mapped[Optional[str]] = mapped_column(String(50))
    birth_governorate: Mapped[Optional[str]] = mapped_column(String(50))
    academic_year_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("academic_years.id")
    )
    grade_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("grades.id"))
    section_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("sections.id")
    )
    parent_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("parents.id")
    )
    photo_url: Mapped[Optional[str]] = mapped_column(String(255))

    parent: Mapped[Optional[Parent]] = relationship("Parent", back_populates="students")
    grade: Mapped[Optional[Grade]] = relationship("Grade", lazy="selectin")
    section: Mapped[Optional[Section]] = relationship("Section", lazy="selectin")


class StudentAcademicHistory(Base):
    __tablename__ = "student_academic_history"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(Integer, ForeignKey("students.id"))
    academic_year_id: Mapped[int] = mapped_column(Integer, ForeignKey("academic_years.id"))
    grade_id: Mapped[int] = mapped_column(Integer, ForeignKey("grades.id"))
    section_id: Mapped[int] = mapped_column(Integer, ForeignKey("sections.id"))
    final_result: Mapped[Optional[str]] = mapped_column(String(20))
    promotion_status: Mapped[Optional[str]] = mapped_column(String(20))


class StudentDocument(Base):
    __tablename__ = "student_documents"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(Integer, ForeignKey("students.id"))
    document_type: Mapped[str] = mapped_column(String(50))
    file_path: Mapped[str] = mapped_column(String(255))
    uploaded_at: Mapped[Optional[datetime]] = mapped_column(DateTime)


class DailyAttendance(Base):
    __tablename__ = "daily_attendance"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(Integer, ForeignKey("students.id"))
    academic_year_id: Mapped[int] = mapped_column(Integer)
    grade_id: Mapped[int] = mapped_column(Integer)
    section_id: Mapped[int] = mapped_column(Integer)
    attendance_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20))
    notes: Mapped[Optional[str]] = mapped_column(Text)


class MonthlyEvaluation(Base):
    __tablename__ = "monthly_evaluations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(Integer)
    academic_year_id: Mapped[int] = mapped_column(Integer)
    grade_id: Mapped[int] = mapped_column(Integer)
    section_id: Mapped[int] = mapped_column(Integer)
    subject_id: Mapped[int] = mapped_column(Integer, ForeignKey("subjects.id"))
    term: Mapped[int] = mapped_column(Integer)
    month: Mapped[int] = mapped_column(Integer)
    written_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    oral_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    homework_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    attendance_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    total_month_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))


class TermExamScore(Base):
    __tablename__ = "term_exam_scores"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(Integer)
    academic_year_id: Mapped[int] = mapped_column(Integer)
    grade_id: Mapped[int] = mapped_column(Integer)
    section_id: Mapped[int] = mapped_column(Integer)
    subject_id: Mapped[int] = mapped_column(Integer, ForeignKey("subjects.id"))
    term: Mapped[int] = mapped_column(Integer)
    exam_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))


class Homework(Base):
    __tablename__ = "homeworks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    academic_year_id: Mapped[int] = mapped_column(Integer)
    grade_id: Mapped[int] = mapped_column(Integer)
    section_id: Mapped[int] = mapped_column(Integer)
    subject_id: Mapped[int] = mapped_column(Integer, ForeignKey("subjects.id"))
    homework_date: Mapped[date] = mapped_column(Date)
    title: Mapped[str] = mapped_column(String(150))
    description: Mapped[Optional[str]] = mapped_column(Text)
    due_date: Mapped[date] = mapped_column(Date)


class BehavioralRecord(Base):
    __tablename__ = "behavioral_records"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(Integer)
    academic_year_id: Mapped[int] = mapped_column(Integer)
    behavior_type: Mapped[str] = mapped_column(String(30))
    title: Mapped[str] = mapped_column(String(150))
    details: Mapped[Optional[str]] = mapped_column(Text)
    action_taken: Mapped[Optional[str]] = mapped_column(Text)
    record_date: Mapped[date] = mapped_column(Date)


class WeeklySchedule(Base):
    __tablename__ = "weekly_schedules"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    academic_year_id: Mapped[int] = mapped_column(Integer)
    term: Mapped[int] = mapped_column(Integer)
    grade_id: Mapped[int] = mapped_column(Integer)
    section_id: Mapped[int] = mapped_column(Integer)
    day_of_week: Mapped[str] = mapped_column(String(20))
    period_number: Mapped[int] = mapped_column(Integer)
    subject_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("subjects.id"))
    teacher_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("employees.id"))


class MonthlyExamSchedule(Base):
    __tablename__ = "monthly_exam_schedules"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    academic_year_id: Mapped[int] = mapped_column(Integer)
    term: Mapped[int] = mapped_column(Integer)
    month: Mapped[int] = mapped_column(Integer)
    grade_id: Mapped[int] = mapped_column(Integer)
    section_id: Mapped[Optional[int]] = mapped_column(Integer)
    subject_id: Mapped[int] = mapped_column(Integer, ForeignKey("subjects.id"))
    exam_date: Mapped[date] = mapped_column(Date)
    day_name: Mapped[str] = mapped_column(String(20))
    period_number: Mapped[int] = mapped_column(Integer)


class FinalExamSchedule(Base):
    __tablename__ = "final_exam_schedules"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    academic_year_id: Mapped[int] = mapped_column(Integer)
    term: Mapped[int] = mapped_column(Integer)
    grade_id: Mapped[int] = mapped_column(Integer)
    subject_id: Mapped[int] = mapped_column(Integer, ForeignKey("subjects.id"))
    exam_date: Mapped[date] = mapped_column(Date)
    day_name: Mapped[str] = mapped_column(String(20))
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)


class StudentFee(Base):
    __tablename__ = "student_fees"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(Integer)
    academic_year_id: Mapped[int] = mapped_column(Integer)
    previous_debt: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    current_year_fees: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    discount_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    net_total_required: Mapped[Decimal] = mapped_column(Numeric(10, 2))


class FeeInstallment(Base):
    __tablename__ = "fee_installments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_fee_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("student_fees.id", ondelete="CASCADE")
    )
    installment_type: Mapped[Optional[str]] = mapped_column(String(20), default="regular")
    installment_number: Mapped[int] = mapped_column(Integer)
    installment_name: Mapped[str] = mapped_column(String(100))
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    due_date: Mapped[date] = mapped_column(Date)
    is_paid: Mapped[bool] = mapped_column(Boolean, default=False)
    paid_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))


class Receipt(Base):
    __tablename__ = "receipts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    receipt_number: Mapped[str] = mapped_column(String(50), unique=True)
    student_id: Mapped[int] = mapped_column(Integer)
    installment_id: Mapped[Optional[int]] = mapped_column(Integer)
    payment_target: Mapped[Optional[str]] = mapped_column(String(30))
    amount_paid: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    payment_date: Mapped[Optional[datetime]] = mapped_column(DateTime)
    payment_method: Mapped[Optional[str]] = mapped_column(String(30))
    reference_number: Mapped[Optional[str]] = mapped_column(String(100))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_by_user_id: Mapped[Optional[int]] = mapped_column(Integer)
    status: Mapped[Optional[str]] = mapped_column(String(20))
    cancellation_reason: Mapped[Optional[str]] = mapped_column(Text)


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(150))
    message: Mapped[str] = mapped_column(Text)
    notification_type: Mapped[str] = mapped_column(String(50))
    sender_user_id: Mapped[Optional[int]] = mapped_column(Integer)
    target_type: Mapped[Optional[str]] = mapped_column(String(30))
    target_grade_id: Mapped[Optional[int]] = mapped_column(Integer)
    target_section_id: Mapped[Optional[int]] = mapped_column(Integer)
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    is_active: Mapped[Optional[bool]] = mapped_column(Boolean, default=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime)


class NotificationLog(Base):
    __tablename__ = "notification_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    notification_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("notifications.id", ondelete="CASCADE")
    )
    parent_id: Mapped[int] = mapped_column(Integer, ForeignKey("parents.id"))
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    delivery_status: Mapped[Optional[str]] = mapped_column(String(20))
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime)


class SchoolInfo(Base):
    __tablename__ = "school_info"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    school_name_ar: Mapped[str] = mapped_column(String(150))
    school_name_en: Mapped[Optional[str]] = mapped_column(String(150))
    principal_name: Mapped[Optional[str]] = mapped_column(String(100))
    license_number: Mapped[Optional[str]] = mapped_column(String(50))
    phone_primary: Mapped[Optional[str]] = mapped_column(String(20))
    phone_secondary: Mapped[Optional[str]] = mapped_column(String(20))
    email: Mapped[Optional[str]] = mapped_column(String(100))
    address_detail: Mapped[Optional[str]] = mapped_column(Text)
    logo_url: Mapped[Optional[str]] = mapped_column(String(255))
    header_footer_url: Mapped[Optional[str]] = mapped_column(String(255))
    terms_and_conditions: Mapped[Optional[str]] = mapped_column(Text)