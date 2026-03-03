"""面试域模型。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import BaseModel


class Room(BaseModel):
    """面试间模型。"""

    __tablename__ = "rooms"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    memory_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String, default="面试间", nullable=False)
    jd_id: Mapped[str | None] = mapped_column(String, nullable=True)
    owner_address: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    resume_id: Mapped[str | None] = mapped_column(String, nullable=True)

    sessions: Mapped[list["Session"]] = relationship(
        back_populates="room",
        cascade="all, delete-orphan",
    )


class Session(BaseModel):
    """面试会话模型。"""

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="initialized", nullable=False)
    current_round: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    room: Mapped[Room] = relationship(back_populates="sessions")
    rounds: Mapped[list["Round"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
    )
    round_completions: Mapped[list["RoundCompletion"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
    )


class Round(BaseModel):
    """面试轮次模型。"""

    __tablename__ = "rounds"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"), index=True, nullable=False)
    round_index: Mapped[int] = mapped_column(Integer, nullable=False)
    questions_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    questions_file_path: Mapped[str] = mapped_column(String, nullable=False)
    round_type: Mapped[str] = mapped_column(String(32), default="ai_generated", nullable=False)
    current_question_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)

    session: Mapped[Session] = relationship(back_populates="rounds")
    question_answers: Mapped[list["QuestionAnswer"]] = relationship(
        back_populates="round",
        cascade="all, delete-orphan",
    )


class QuestionAnswer(BaseModel):
    """轮次问答记录模型。"""

    __tablename__ = "question_answers"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    round_id: Mapped[str] = mapped_column(ForeignKey("rounds.id", ondelete="CASCADE"), index=True, nullable=False)
    question_index: Mapped[int] = mapped_column(Integer, nullable=False)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    answer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    question_category: Mapped[str | None] = mapped_column(String, nullable=True)
    is_answered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    round: Mapped[Round] = relationship(back_populates="question_answers")


class RoundCompletion(BaseModel):
    """轮次完成幂等记录模型。"""

    __tablename__ = "round_completions"
    __table_args__ = (UniqueConstraint("session_id", "round_index", name="uq_round_completion_session_round"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"), index=True, nullable=False)
    round_index: Mapped[int] = mapped_column(Integer, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    session: Mapped[Session] = relationship(back_populates="round_completions")

