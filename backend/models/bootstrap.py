"""数据库初始化（迁移优先）。"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import inspect

from backend.common.logger import get_logger
from backend.models.base import Base, DATABASE_URL, engine

logger = get_logger(__name__)

BUSINESS_TABLES = {
    "auth_challenges",
    "resumes",
    "rooms",
    "sessions",
    "rounds",
    "question_answers",
    "round_completions",
}


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _should_stamp_head(table_names: set[str]) -> bool:
    # 历史数据库可能由程序直接建表初始化，没有迁移版本表；这种场景先打基线标签。
    return "alembic_version" not in table_names and BUSINESS_TABLES.issubset(table_names)


def _run_alembic_upgrade() -> None:
    from alembic import command
    from alembic.config import Config

    root = _project_root()
    alembic_ini = root / "alembic.ini"
    alembic_dir = root / "alembic"

    if not alembic_ini.exists() or not alembic_dir.exists():
        raise RuntimeError("Alembic 配置缺失，请检查 alembic.ini 和 alembic/ 目录")

    cfg = Config(str(alembic_ini))
    cfg.set_main_option("script_location", str(alembic_dir))
    cfg.set_main_option("sqlalchemy.url", DATABASE_URL)

    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if _should_stamp_head(table_names):
        logger.warning("Detected legacy schema without alembic_version, stamping to head")
        command.stamp(cfg, "head")

    command.upgrade(cfg, "head")


def init_database() -> None:
    """初始化数据库：优先 Alembic，缺失时回退 create_all。"""
    try:
        _run_alembic_upgrade()
        logger.info("Database initialized with Alembic migrations")
        return
    except (ModuleNotFoundError, ImportError):
        logger.warning("Alembic not installed, fallback to Base.metadata.create_all")
    except Exception as exc:
        logger.error("Failed to run Alembic migrations: %s", exc, exc_info=True)
        raise

    Base.metadata.create_all(bind=engine)
    logger.info("Database initialized with SQLAlchemy create_all fallback")
