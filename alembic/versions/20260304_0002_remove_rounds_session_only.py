"""Remove rounds model and migrate QA to session scope

Revision ID: 202603040002
Revises: 202603040001
Create Date: 2026-03-04 16:35:00
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "202603040002"
down_revision: Union[str, None] = "202603040001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(inspector: sa.Inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _has_column(inspector: sa.Inspector, table_name: str, column_name: str) -> bool:
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def _has_index(inspector: sa.Inspector, table_name: str, index_name: str) -> bool:
    return any(idx.get("name") == index_name for idx in inspector.get_indexes(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # 1) 先把 question_answers 从 round_id 迁移到 session_id。
    if _has_table(inspector, "question_answers"):
        has_round_id = _has_column(inspector, "question_answers", "round_id")
        has_session_id = _has_column(inspector, "question_answers", "session_id")

        if has_round_id:
            op.create_table(
                "question_answers_new",
                sa.Column("id", sa.String(), nullable=False),
                sa.Column("session_id", sa.String(), nullable=False),
                sa.Column("question_index", sa.Integer(), nullable=False),
                sa.Column("question_text", sa.Text(), nullable=False),
                sa.Column("answer_text", sa.Text(), nullable=True),
                sa.Column("question_category", sa.String(), nullable=True),
                sa.Column("is_answered", sa.Boolean(), nullable=False),
                sa.Column("created_at", sa.DateTime(), nullable=False),
                sa.Column("updated_at", sa.DateTime(), nullable=False),
                sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
                sa.PrimaryKeyConstraint("id"),
            )

            if _has_table(inspector, "rounds"):
                if has_session_id:
                    op.execute(
                        sa.text(
                            """
                            INSERT INTO question_answers_new (
                                id, session_id, question_index, question_text,
                                answer_text, question_category, is_answered,
                                created_at, updated_at
                            )
                            SELECT
                                qa.id,
                                COALESCE(qa.session_id, r.session_id) AS session_id,
                                qa.question_index,
                                qa.question_text,
                                qa.answer_text,
                                qa.question_category,
                                qa.is_answered,
                                qa.created_at,
                                qa.updated_at
                            FROM question_answers qa
                            LEFT JOIN rounds r ON r.id = qa.round_id
                            WHERE COALESCE(qa.session_id, r.session_id) IS NOT NULL
                            """
                        )
                    )
                else:
                    op.execute(
                        sa.text(
                            """
                            INSERT INTO question_answers_new (
                                id, session_id, question_index, question_text,
                                answer_text, question_category, is_answered,
                                created_at, updated_at
                            )
                            SELECT
                                qa.id,
                                r.session_id,
                                qa.question_index,
                                qa.question_text,
                                qa.answer_text,
                                qa.question_category,
                                qa.is_answered,
                                qa.created_at,
                                qa.updated_at
                            FROM question_answers qa
                            JOIN rounds r ON r.id = qa.round_id
                            """
                        )
                    )
            elif has_session_id:
                op.execute(
                    sa.text(
                        """
                        INSERT INTO question_answers_new (
                            id, session_id, question_index, question_text,
                            answer_text, question_category, is_answered,
                            created_at, updated_at
                        )
                        SELECT
                            id, session_id, question_index, question_text,
                            answer_text, question_category, is_answered,
                            created_at, updated_at
                        FROM question_answers
                        WHERE session_id IS NOT NULL
                        """
                    )
                )

            op.drop_table("question_answers")
            op.rename_table("question_answers_new", "question_answers")
            op.create_index("ix_question_answers_session_id", "question_answers", ["session_id"], unique=False)

        elif has_session_id and not _has_index(inspector, "question_answers", "ix_question_answers_session_id"):
            op.create_index("ix_question_answers_session_id", "question_answers", ["session_id"], unique=False)

    # 2) 删除 sessions.current_round 列。
    inspector = sa.inspect(bind)
    if _has_table(inspector, "sessions") and _has_column(inspector, "sessions", "current_round"):
        with op.batch_alter_table("sessions", recreate="always") as batch_op:
            batch_op.drop_column("current_round")

    # 3) 删除 round_completions / rounds 表。
    inspector = sa.inspect(bind)
    if _has_table(inspector, "round_completions"):
        op.drop_table("round_completions")

    inspector = sa.inspect(bind)
    if _has_table(inspector, "rounds"):
        op.drop_table("rounds")


def downgrade() -> None:
    raise NotImplementedError("Downgrade is not supported for rounds -> session-only migration")
