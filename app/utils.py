from datetime import date, datetime
from decimal import Decimal
from typing import Any


def to_str(value: date | datetime | None) -> str | None:
    """يحوّل التاريخ/الوقت إلى ISO string."""
    if value is None:
        return None
    return value.isoformat()


def to_float(value: Decimal | float | int | None) -> float:
    if value is None:
        return 0.0
    return float(value)


def ok(data: Any, message: str = "") -> dict:
    return {"success": True, "data": data, "message": message}


def fail(message: str) -> dict:
    return {"success": False, "data": None, "message": message}