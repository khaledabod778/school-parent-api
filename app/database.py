from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings

settings = get_settings()

# Railway قد يعطي رابط postgres:// (بدون ql)
_url = settings.database_url
if _url.startswith("postgres://"):
    _url = _url.replace("postgres://", "postgresql://", 1)

engine = create_engine(
    _url,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    pool_recycle=300,
    echo=settings.debug,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass