"""
أدوات مساعدة للتعامل مع أعمدة التزامن (sync_*) في قاعدة البيانات.
كل جدول يحتوي على: sync_uuid, sync_version, sync_updated_at, sync_source
"""
import logging
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import inspect
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

SYNC_UUID = "sync_uuid"
SYNC_VERSION = "sync_version"
SYNC_UPDATED_AT = "sync_updated_at"
SYNC_SOURCE = "sync_source"
DEFAULT_SOURCE = "parent-api"


def _get_columns(db: Session, table: str) -> dict[str, dict]:
    """يُرجع dict: {column_name: column_info}."""
    inspector = inspect(db.bind)
    return {c["name"]: c for c in inspector.get_columns(table)}


def fill_sync_columns_for_insert(
    db: Session,
    table: str,
    values: dict[str, Any],
) -> dict[str, Any]:
    """
    يعبّئ أعمدة sync_* الإلزامية في dict قبل INSERT.
    - sync_uuid → UUID جديد
    - sync_version → 1
    - sync_updated_at → now
    - sync_source → 'parent-api'
    """
    cols = _get_columns(db, table)
    now = datetime.utcnow()

    for name, info in cols.items():
        if name in values:
            continue

        nullable = info.get("nullable", True)
        has_default = info.get("default") is not None

        # تجاهل الأعمدة nullable أو التي لها default
        if nullable or has_default:
            continue

        # أعمدة NOT NULL بدون default → نعبّئها
        if name == SYNC_UUID or name.endswith("_uuid"):
            values[name] = str(uuid.uuid4())
        elif name == SYNC_VERSION:
            values[name] = 1
        elif name == SYNC_UPDATED_AT or name == SYNC_SOURCE:
            # لن تُحتسب NOT NULL عادة، لكن احتياطاً
            values[name] = now if "at" in name else DEFAULT_SOURCE
        elif name in ("created_at", "updated_at"):
            values[name] = now
        else:
            logger.warning("Unknown NOT NULL column %s.%s — filling with None", table, name)

    return values


def build_sync_update_set(
    db: Session,
    table: str,
    prefix: str = "",
) -> tuple[list[str], dict[str, Any]]:
    """
    يبني جملة SET لأعمدة sync_* أثناء UPDATE.
    يرجّع (list_of_set_clauses, extra_params).

    الاستخدام:
        sets, extra = build_sync_update_set(db, "parents")
        sql = f"UPDATE parents SET password_hash = :ph, {', '.join(sets)} WHERE id = :id"
        db.execute(text(sql), {"ph": new_hash, "id": 1, **extra})
    """
    cols = _get_columns(db, table)
    sets: list[str] = []
    params: dict[str, Any] = {}
    now = datetime.utcnow()

    if SYNC_UPDATED_AT in cols:
        sets.append(f"{SYNC_UPDATED_AT} = :{prefix}sync_updated_at")
        params[f"{prefix}sync_updated_at"] = now

    if SYNC_VERSION in cols:
        sets.append(f"{SYNC_VERSION} = COALESCE({SYNC_VERSION}, 0) + 1")

    if SYNC_SOURCE in cols:
        sets.append(f"{SYNC_SOURCE} = :{prefix}sync_source")
        params[f"{prefix}sync_source"] = DEFAULT_SOURCE

    return sets, params
