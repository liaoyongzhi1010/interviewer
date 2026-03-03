"""鉴权相关持久化模型。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import BaseModel


class AuthChallenge(BaseModel):
    """钱包签名挑战记录。"""

    __tablename__ = "auth_challenges"

    address: Mapped[str] = mapped_column(String(128), primary_key=True)
    challenge: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

