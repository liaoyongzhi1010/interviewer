"""数据库连接与基础模型。"""

from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Generator

from dotenv import load_dotenv
from sqlalchemy import DateTime, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

load_dotenv()

DATABASE_PATH = os.getenv("DATABASE_PATH", "data/yeying_interviewer.db")


def _build_database_url(database_path: str) -> str:
    if "://" in database_path:
        return database_path
    if database_path == ":memory:":
        return "sqlite+pysqlite:///:memory:"
    return f"sqlite+pysqlite:///{database_path}"


def _ensure_database_dir(database_path: str) -> None:
    if "://" in database_path or database_path == ":memory:":
        return
    path = Path(database_path)
    if path.parent != Path("."):
        path.parent.mkdir(parents=True, exist_ok=True)


_ensure_database_dir(DATABASE_PATH)
DATABASE_URL = _build_database_url(DATABASE_PATH)

engine = create_engine(
    DATABASE_URL,
    future=True,
    pool_pre_ping=True,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    future=True,
)


class Base(DeclarativeBase):
    """声明式基类。"""


class BaseModel(Base):
    """统一 created_at / updated_at 字段。"""

    __abstract__ = True

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


@contextmanager
def db_session() -> Generator:
    """事务会话上下文，统一提交/回滚。"""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
