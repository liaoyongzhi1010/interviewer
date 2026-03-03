"""系统与诊断相关 API 路由。"""

from fastapi import APIRouter, Request
from sqlalchemy import select

from backend.api.deps import require_api_user
from backend.api.response import ApiResponse
from backend.clients.minio_client import download_resume_data, minio_client
from backend.common.logger import get_logger
from backend.models import Resume, SessionLocal

logger = get_logger(__name__)

router = APIRouter(tags=["System"])


@router.get("/api/v1/minio/test")
def test_minio(request: Request):
    current_user, auth_error = require_api_user(request)
    if auth_error:
        return auth_error

    _ = current_user  # auth guard only

    try:
        objects = minio_client.list_objects(prefix="data/")

        candidate_name = None
        resume_loaded = False
        with SessionLocal() as session:
            sample_resume = session.execute(select(Resume).where(Resume.status == "active").limit(1)).scalar_one_or_none()
        if sample_resume:
            resume_data = download_resume_data(sample_resume.id)
            resume_loaded = resume_data is not None
            if resume_data:
                candidate_name = resume_data.get("name")

        return ApiResponse.success(
            data={
                "minio_objects": objects,
                "resume_loaded": resume_loaded,
                "candidate_name": candidate_name,
            }
        )
    except Exception as exc:
        logger.error("MinIO test failed: %s", exc, exc_info=True)
        return ApiResponse.internal_error(str(exc))
