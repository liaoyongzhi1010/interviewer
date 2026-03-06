"""Rebuild question_answers for adaptive interview follow-up

Revision ID: 202603040003
Revises: 202603040002
Create Date: 2026-03-04 21:30:00
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "202603040003"
down_revision: Union[str, None] = "202603040002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(inspector: sa.Inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # 预发布阶段允许硬迁移，直接重建 question_answers 表。
    if _has_table(inspector, "question_answers"):
        op.drop_table("question_answers")

    op.create_table(
        "question_answers",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("parent_qa_id", sa.String(), nullable=True),
        sa.Column("question_index", sa.Integer(), nullable=False),
        sa.Column("depth", sa.Integer(), nullable=False),
        sa.Column("question_type", sa.String(length=32), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("answer_text", sa.Text(), nullable=True),
        sa.Column("answer_score", sa.Float(), nullable=True),
        sa.Column("answer_eval_brief", sa.Text(), nullable=True),
        sa.Column("question_category", sa.String(), nullable=True),
        sa.Column("is_answered", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_qa_id"], ["question_answers.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_question_answers_session_id", "question_answers", ["session_id"], unique=False)
    op.create_index("ix_question_answers_parent_qa_id", "question_answers", ["parent_qa_id"], unique=False)


def downgrade() -> None:
    raise NotImplementedError("Downgrade is not supported for adaptive follow-up schema migration")
