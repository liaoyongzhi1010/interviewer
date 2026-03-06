"""Add mistake_items table for question favorites

Revision ID: 202603060004
Revises: 202603040003
Create Date: 2026-03-06 23:10:00
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "202603060004"
down_revision: Union[str, None] = "202603040003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(inspector: sa.Inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, "mistake_items"):
        return

    op.create_table(
        "mistake_items",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("owner_address", sa.String(length=64), nullable=False),
        sa.Column("qa_id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("session_name", sa.String(), nullable=True),
        sa.Column("room_id", sa.String(), nullable=False),
        sa.Column("room_name", sa.String(), nullable=True),
        sa.Column("question_text_snapshot", sa.Text(), nullable=False),
        sa.Column("answer_text_snapshot", sa.Text(), nullable=True),
        sa.Column("question_category", sa.String(), nullable=True),
        sa.Column("answer_score_snapshot", sa.Float(), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("review_count", sa.Integer(), nullable=False),
        sa.Column("last_reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_address", "qa_id", name="uq_mistake_owner_qa"),
    )

    op.create_index("ix_mistake_items_owner_address", "mistake_items", ["owner_address"], unique=False)
    op.create_index("ix_mistake_items_qa_id", "mistake_items", ["qa_id"], unique=False)
    op.create_index("ix_mistake_items_session_id", "mistake_items", ["session_id"], unique=False)
    op.create_index("ix_mistake_items_room_id", "mistake_items", ["room_id"], unique=False)


def downgrade() -> None:
    raise NotImplementedError("Downgrade is not supported for mistake_items migration")
