import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.database import engine
from app.services.fcm import init_fcm
from app.routers import (
    auth, financial, grades, notifications, parents, reference, schedules, students,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=" * 60)
    logger.info("  School Parent API starting...")
    logger.info("  Version: %s", settings.app_version)
    logger.info("=" * 60)

    # فحص الاتصال بقاعدة البيانات
    try:
        with engine.connect() as conn:
            from sqlalchemy import text
            conn.execute(text("SELECT 1"))
        logger.info("✅ Database connection OK")
    except Exception as exc:
        logger.exception("❌ Database connection FAILED: %s", exc)

    # تهيئة FCM (اختياري)
    init_fcm()

    yield

    logger.info("School Parent API shutting down...")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "API وسيط لتطبيق ولي الأمر — يقرأ من قاعدة بيانات نظام إدارة المدرسة "
        "المنشور على Railway."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# CORS
origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins if origins != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# Root + Health
# ============================================================
@app.get("/")
def root():
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health")
def health():
    try:
        with engine.connect() as conn:
            from sqlalchemy import text
            conn.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception:
        db_status = "error"

    return {"status": "healthy", "database": db_status}


# ============================================================
# Routers
# ============================================================
API_PREFIX = "/api/v1"

app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(parents.router, prefix=API_PREFIX)
app.include_router(students.router, prefix=API_PREFIX)
app.include_router(grades.router, prefix=API_PREFIX)
app.include_router(schedules.router, prefix=API_PREFIX)
app.include_router(financial.router, prefix=API_PREFIX)
app.include_router(notifications.router, prefix=API_PREFIX)
app.include_router(reference.router, prefix=API_PREFIX)


# ============================================================
# Exception handlers
# ============================================================
@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception on %s: %s", request.url.path, exc)
    return JSONResponse(
        status_code=500,
        content={"success": False, "data": None, "message": "حدث خطأ في الخادم"},
    )