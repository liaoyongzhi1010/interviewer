"""Initial SQLAlchemy schema

Revision ID: 202603040001
Revises:
Create Date: 2026-03-04 00:35:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "202603040001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "auth_challenges",
        sa.Column("address", sa.String(length=128), nullable=False),
        sa.Column("challenge", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("address"),
    )

    op.create_table(
        "resumes",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("owner_address", sa.String(length=64), nullable=False),
        sa.Column("file_name", sa.String(), nullable=True),
        sa.Column("file_size", sa.Integer(), nullable=True),
        sa.Column("company", sa.String(), nullable=True),
        sa.Column("position", sa.String(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("parse_status", sa.String(length=32), nullable=False),
        sa.Column("parse_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_resumes_owner_address", "resumes", ["owner_address"], unique=False)

    op.create_table(
        "rooms",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("memory_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("jd_id", sa.String(), nullable=True),
        sa.Column("owner_address", sa.String(length=64), nullable=True),
        sa.Column("resume_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("memory_id"),
    )
    op.create_index("ix_rooms_owner_address", "rooms", ["owner_address"], unique=False)

    op.create_table(
        "sessions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("room_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("current_round", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sessions_room_id", "sessions", ["room_id"], unique=False)

    op.create_table(
        "rounds",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("round_index", sa.Integer(), nullable=False),
        sa.Column("questions_count", sa.Integer(), nullable=False),
        sa.Column("questions_file_path", sa.String(), nullable=False),
        sa.Column("round_type", sa.String(length=32), nullable=False),
        sa.Column("current_question_index", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rounds_session_id", "rounds", ["session_id"], unique=False)

    op.create_table(
        "question_answers",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("round_id", sa.String(), nullable=False),
        sa.Column("question_index", sa.Integer(), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("answer_text", sa.Text(), nullable=True),
        sa.Column("question_category", sa.String(), nullable=True),
        sa.Column("is_answered", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["round_id"], ["rounds.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_question_answers_round_id", "question_answers", ["round_id"], unique=False)

    op.create_table(
        "round_completions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("round_index", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
        sa.UniqueConstraint("session_id", "round_index", name="uq_round_completion_session_round"),
    )
    op.create_index("ix_round_completions_session_id", "round_completions", ["session_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_round_completions_session_id", table_name="round_completions")
    op.drop_table("round_completions")

    op.drop_index("ix_question_answers_round_id", table_name="question_answers")
    op.drop_table("question_answers")

    op.drop_index("ix_rounds_session_id", table_name="rounds")
    op.drop_table("rounds")

    op.drop_index("ix_sessions_room_id", table_name="sessions")
    op.drop_table("sessions")

    op.drop_index("ix_rooms_owner_address", table_name="rooms")
    op.drop_table("rooms")

    op.drop_index("ix_resumes_owner_address", table_name="resumes")
    op.drop_table("resumes")

    op.drop_table("auth_challenges")

