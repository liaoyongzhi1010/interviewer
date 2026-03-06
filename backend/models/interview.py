"""面试域模型。"""

from __future__ import annotations

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
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

    room: Mapped[Room] = relationship(back_populates="sessions")
    question_answers: Mapped[list["QuestionAnswer"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
    )


class QuestionAnswer(BaseModel):
    """会话问答记录模型。"""

    __tablename__ = "question_answers"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"), index=True, nullable=False)
    parent_qa_id: Mapped[str | None] = mapped_column(
        ForeignKey("question_answers.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    question_index: Mapped[int] = mapped_column(Integer, nullable=False)
    depth: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    question_type: Mapped[str] = mapped_column(String(32), default="main", nullable=False)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    answer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    answer_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    answer_eval_brief: Mapped[str | None] = mapped_column(Text, nullable=True)
    question_category: Mapped[str | None] = mapped_column(String, nullable=True)
    is_answered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    session: Mapped[Session] = relationship(back_populates="question_answers")
