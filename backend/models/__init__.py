"""数据库模型统一导出。"""

from backend.models.auth import AuthChallenge
from backend.models.base import DATABASE_PATH, Base, BaseModel, SessionLocal, db_session, engine
from backend.models.bootstrap import init_database
from backend.models.interview import QuestionAnswer, Room, Session
from backend.models.mistake import MistakeItem
from backend.models.resume import Resume

__all__ = [
    "DATABASE_PATH",
    "engine",
    "SessionLocal",
    "db_session",
    "Base",
    "BaseModel",
    "AuthChallenge",
    "Resume",
    "Room",
    "Session",
    "QuestionAnswer",
    "MistakeItem",
    "init_database",
]
