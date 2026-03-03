"""按领域分组的 API 路由。"""

from backend.api.routers.auth import router as auth_router
from backend.api.routers.question import router as question_router
from backend.api.routers.report import router as report_router
from backend.api.routers.resume import router as resume_router
from backend.api.routers.room import router as room_router
from backend.api.routers.session import router as session_router
from backend.api.routers.system import router as system_router

__all__ = [
    "auth_router",
    "room_router",
    "session_router",
    "resume_router",
    "question_router",
    "report_router",
    "system_router",
]
