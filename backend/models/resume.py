"""简历域模型。"""

from __future__ import annotations

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import BaseModel


class Resume(BaseModel):
    """用户简历模型。"""

    __tablename__ = "resumes"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    owner_address: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    file_name: Mapped[str | None] = mapped_column(String, nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    company: Mapped[str | None] = mapped_column(String, nullable=True)
    position: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    parse_status: Mapped[str] = mapped_column(String(32), default="parsed", nullable=False)
    parse_error: Mapped[str | None] = mapped_column(Text, nullable=True)

