"""接口路由聚合。"""

from fastapi import APIRouter

from backend.api.routers.auth import router as auth_router
from backend.api.routers.question import router as question_router
from backend.api.routers.report import router as report_router
from backend.api.routers.resume import router as resume_router
from backend.api.routers.room import router as room_router
from backend.api.routers.session import router as session_router
from backend.api.routers.system import router as system_router

router = APIRouter(tags=["API"])

router.include_router(auth_router)
router.include_router(room_router)
router.include_router(session_router)
router.include_router(resume_router)
router.include_router(question_router)
router.include_router(report_router)
router.include_router(system_router)
