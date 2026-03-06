"""Alembic 运行环境配置。"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from backend.models.base import Base, DATABASE_URL
from backend.models.auth import AuthChallenge
from backend.models.interview import QuestionAnswer, Room, Session
from backend.models.mistake import MistakeItem
from backend.models.resume import Resume

# 引用模型以确保 metadata 注册（避免被优化器裁剪）
_ = (AuthChallenge, Resume, Room, Session, QuestionAnswer, MistakeItem)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

db_url = os.getenv("DATABASE_URL", DATABASE_URL)
config.set_main_option("sqlalchemy.url", db_url)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """离线模式运行迁移。"""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        render_as_batch=url.startswith("sqlite"),
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式运行迁移。"""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            render_as_batch=str(connection.engine.url).startswith("sqlite"),
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
