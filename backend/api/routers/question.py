"""题目与问答流程 API 路由（无轮次版本）。"""

from fastapi import APIRouter, Request
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.api.deps import ensure_room_owner, ensure_session_owner, is_valid_uuid, require_api_user
from backend.api.response import ApiResponse, ResponseCode
from backend.api.schemas import SaveAnswerRequest, UploadJDRequest
from backend.clients.minio_client import download_qa_analysis, minio_client
from backend.common.config import config
from backend.common.logger import get_logger
from backend.models import QuestionAnswer, Room, Session, SessionLocal, db_session

logger = get_logger(__name__)

router = APIRouter(tags=["Question"])


@router.post("/api/v1/generate_questions/{session_id}")
def generate_questions(request: Request, session_id: str):
    if not is_valid_uuid(session_id):
        return ApiResponse.bad_request("无效的session_id格式")

    current_user, auth_error = require_api_user(request)
    if auth_error:
        return auth_error

    interview_session, owner_error = ensure_session_owner(session_id, current_user)
    if owner_error:
        return owner_error

    previous_status = interview_session.status
    try:
        with db_session() as db:
            persistent_session = db.get(Session, interview_session.id)
            if not persistent_session:
                return ApiResponse.not_found("面试会话")
            persistent_session.status = "generating"

        from backend.services.question import get_question_generation_service

        service = get_question_generation_service()
        result = service.generate_questions(session_id)

        if not result.get("success"):
            with db_session() as db:
                persistent_session = db.get(Session, interview_session.id)
                if persistent_session:
                    persistent_session.status = previous_status
            return ApiResponse.error(result.get("error", "生成面试题失败"))

        target_status = "interviewing"
        if result.get("already_generated") and previous_status == "completed":
            target_status = "completed"

        with db_session() as db:
            persistent_session = db.get(Session, interview_session.id)
            if persistent_session:
                persistent_session.status = target_status

        return ApiResponse.success(data=result)

    except Exception as exc:
        logger.error("Failed to generate questions: %s", exc, exc_info=True)
        try:
            with db_session() as db:
                persistent_session = db.get(Session, interview_session.id)
                if persistent_session:
                    persistent_session.status = previous_status
        except Exception as rollback_error:
            logger.error("Failed to rollback session status: %s", rollback_error)

        return ApiResponse.internal_error(f"生成面试题失败: {exc}")


@router.post("/api/v1/upload_jd/{room_id}")
def upload_jd(request: Request, room_id: str, payload: UploadJDRequest):
    if not is_valid_uuid(room_id):
        return ApiResponse.bad_request("无效的room_id格式")

    current_user, auth_error = require_api_user(request)
    if auth_error:
        return auth_error

    room, owner_error = ensure_room_owner(room_id, current_user)
    if owner_error:
        return owner_error

    if not config.RAG_ENABLED:
        return ApiResponse.bad_request("JD 上传功能未开启，请先在后端配置 RAG_ENABLED=true")

    content = str(payload.content).strip()
    if not content:
        return ApiResponse.bad_request("JD 内容不能为空")

    try:
        from backend.clients.rag_client import get_rag_client

        rag_client = get_rag_client()
        jd_id = rag_client.upload_jd(
            memory_id=room.memory_id,
            company=payload.company,
            position=payload.position,
            content=content,
        )

        with db_session() as db:
            persistent_room = db.get(Room, room.id)
            if not persistent_room:
                return ApiResponse.not_found("面试间")
            persistent_room.jd_id = jd_id

        return ApiResponse.success(
            data={"jd_id": jd_id},
            message="JD 上传成功，本面试间后续出题将优先使用该 JD",
        )
    except Exception as exc:
        logger.error("Failed to upload JD for room %s: %s", room_id, exc, exc_info=True)
        return ApiResponse.internal_error("JD 上传失败，请稍后重试")


@router.get("/api/v1/get_current_question/{session_id}")
def get_current_question(request: Request, session_id: str):
    if not is_valid_uuid(session_id):
        return ApiResponse.bad_request("无效的session_id格式")

    current_user, auth_error = require_api_user(request)
    if auth_error:
        return auth_error

    _, owner_error = ensure_session_owner(session_id, current_user)
    if owner_error:
        return owner_error

    try:
        from backend.services.question import get_question_generation_service

        service = get_question_generation_service()
        question_data = service.get_current_question(session_id)

        if question_data:
            return ApiResponse.success(data={"question_data": question_data})
        return ApiResponse.success(data=None, message="没有更多问题了")
    except Exception as exc:
        logger.error("Failed to get question: %s", exc, exc_info=True)
        return ApiResponse.internal_error(f"获取问题失败: {exc}")


@router.post("/api/v1/save_answer")
def save_answer(request: Request, payload: SaveAnswerRequest):
    current_user, auth_error = require_api_user(request)
    if auth_error:
        return auth_error

    qa_id = payload.qa_id
    answer_text = payload.answer_text

    try:
        with SessionLocal() as db:
            qa = db.get(QuestionAnswer, qa_id)
            if not qa:
                return ApiResponse.not_found("问答记录")

            session_obj = db.execute(
                select(Session)
                .where(Session.id == qa.session_id)
                .options(selectinload(Session.room))
            ).scalar_one_or_none()

        if not session_obj:
            return ApiResponse.not_found("面试会话")

        if session_obj.room.owner_address != current_user:
            return ApiResponse.forbidden()

        from backend.services.question import get_question_generation_service

        service = get_question_generation_service()
        result = service.save_answer(qa_id, str(answer_text).strip())
        if not result.get("success"):
            return ApiResponse.error(result.get("error", "保存回答失败"))

        return ApiResponse.success(data=result, message="回答保存成功")
    except Exception as exc:
        logger.error("Failed to save answer: %s", exc, exc_info=True)
        return ApiResponse.internal_error(f"保存回答失败: {exc}")


@router.get("/api/v1/get_qa_analysis/{session_id}")
def get_qa_analysis(request: Request, session_id: str):
    if not is_valid_uuid(session_id):
        return ApiResponse.bad_request("无效的session_id格式")

    current_user, auth_error = require_api_user(request)
    if auth_error:
        return auth_error

    session_obj, owner_error = ensure_session_owner(session_id, current_user)
    if owner_error:
        return owner_error

    try:
        room_id = session_obj.room.id
        analysis_filename = f"rooms/{room_id}/sessions/{session_id}/analysis/qa_complete.json"
        analysis_data = download_qa_analysis(room_id, session_id)

        if analysis_data:
            return ApiResponse.success(
                data={"analysis_data": analysis_data, "file_path": analysis_filename}
            )
        return ApiResponse.not_found("分析数据")
    except Exception as exc:
        logger.error("Failed to get QA analysis: %s", exc, exc_info=True)
        return ApiResponse.internal_error(f"获取分析数据失败: {exc}")


@router.post("/api/v1/qa_completion/{session_id}")
def confirm_qa_completion(
    request: Request,
    session_id: str,
):
    if not is_valid_uuid(session_id):
        return ApiResponse.bad_request("无效的session_id格式")

    current_user, auth_error = require_api_user(request)
    if auth_error:
        return auth_error

    session_obj, owner_error = ensure_session_owner(session_id, current_user)
    if owner_error:
        return owner_error

    room_id = session_obj.room.id
    qa_object_path = f"rooms/{room_id}/sessions/{session_id}/analysis/qa_complete.json"

    if not minio_client.object_exists(qa_object_path):
        logger.warning(
            "QA object missing for session %s at %s",
            session_id,
            qa_object_path,
        )
        return ApiResponse.error(
            message="qa object missing",
            code=ResponseCode.CONFLICT,
            data={"qa_object_path": qa_object_path},
        )

    logger.info(
        "QA completion confirmed for session %s: path=%s",
        session_id,
        qa_object_path,
    )

    return ApiResponse.success(
        data={"is_completed": True, "qa_object_path": qa_object_path},
        message="会话完成确认成功",
    )
