"""数据库初始化（迁移优先）。"""

from __future__ import annotations

from pathlib import Path

from backend.common.logger import get_logger
from backend.models.base import DATABASE_URL

logger = get_logger(__name__)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


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

    command.upgrade(cfg, "head")


def init_database() -> None:
    """初始化数据库：通过 Alembic 迁移。"""
    try:
        _run_alembic_upgrade()
        logger.info("Database initialized with Alembic migrations")
    except Exception as exc:
        logger.error("Failed to run Alembic migrations: %s", exc, exc_info=True)
        raise
