"""错题收藏模型。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import BaseModel


class MistakeItem(BaseModel):
    """用户错题收藏项。"""

    __tablename__ = "mistake_items"
    __table_args__ = (UniqueConstraint("owner_address", "qa_id", name="uq_mistake_owner_qa"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    owner_address: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    qa_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    session_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    session_name: Mapped[str | None] = mapped_column(String, nullable=True)
    room_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    room_name: Mapped[str | None] = mapped_column(String, nullable=True)
    question_text_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    answer_text_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    question_category: Mapped[str | None] = mapped_column(String, nullable=True)
    answer_score_snapshot: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(32), default="manual_favorite", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="new", nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
