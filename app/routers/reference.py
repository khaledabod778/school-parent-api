from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import get_db
from app.models import AcademicYear, SchoolInfo
from app.utils import ok, to_str

router = APIRouter(tags=["Reference"])


@router.get("/school-info")
def school_info(db: Session = Depends(get_db)):
    info = db.execute(select(SchoolInfo).limit(1)).scalar_one_or_none()
    if not info:
        return ok(None)
    return ok(
        {
            "school_name_ar": info.school_name_ar,
            "school_name_en": info.school_name_en,
            "principal_name": info.principal_name,
            "license_number": info.license_number,
            "phone_primary": info.phone_primary,
            "phone_secondary": info.phone_secondary,
            "email": info.email,
            "address_detail": info.address_detail,
            "logo_url": info.logo_url,
            "header_footer_url": info.header_footer_url,
            "terms_and_conditions": info.terms_and_conditions,
        }
    )


@router.get("/academic-years/current")
def current_academic_year(db: Session = Depends(get_db)):
    year = db.execute(
        select(AcademicYear).where(AcademicYear.is_current.is_(True)).limit(1)
    ).scalar_one_or_none()

    if not year:
        return ok(None)

    return ok(
        {
            "id": year.id,
            "year_name_gregorian": year.year_name_gregorian,
            "year_name_hijri": year.year_name_hijri,
            "start_date": to_str(year.start_date),
            "end_date": to_str(year.end_date),
            "is_current": year.is_current,
            "status": year.status,
        }
    )