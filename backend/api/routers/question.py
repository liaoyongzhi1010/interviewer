"""题目与问答流程 API 路由。"""

import os
from datetime import datetime

from fastapi import APIRouter, Request
from sqlalchemy import func, select

from backend.api.deps import ensure_room_owner, ensure_session_owner, is_valid_uuid, require_api_user
from backend.api.response import ApiResponse, ResponseCode
from backend.api.schemas import QACompletionRequest, SaveAnswerRequest, UploadJDRequest
from backend.clients.digitalhub_client import start_llm
from backend.clients.minio_client import download_qa_analysis, minio_client
from backend.common.logger import get_logger
from backend.models import QuestionAnswer, Room, Round, Session, SessionLocal, db_session
from backend.services.interview_service import RoundService, SessionService

logger = get_logger(__name__)

router = APIRouter(tags=["Question"])


def _start_llm_server(session_id: str, room_id: str, result: dict, round_index: int) -> None:
    try:
        llm_info = start_llm(
            room_id=room_id,
            session_id=session_id,
            round_index=int(round_index),
            port=int(os.getenv("LLM_PORT", "8011")),
            minio_endpoint=os.getenv("MINIO_ENDPOINT", "test-minio.yeying.pub"),
            minio_access_key=os.getenv("MINIO_ACCESS_KEY", ""),
            minio_secret_key=os.getenv("MINIO_SECRET_KEY", ""),
            minio_bucket=os.getenv("MINIO_BUCKET", "yeying-interviewer"),
            minio_secure=os.getenv("MINIO_SECURE", "true").lower() == "true",
        )
        result["llm"] = llm_info.get("data", llm_info)
    except Exception as exc:
        logger.warning("Failed to start LLM server: %s", exc)
        result["llm_error"] = str(exc)


@router.post("/api/v1/generate_questions/{session_id}")
def generate_questions(request: Request, session_id: str):
    if not is_valid_uuid(session_id):
        return ApiResponse.bad_request("无效的session_id格式")

    current_user, auth_error = require_api_user(request)
    if auth_error:
        return auth_error

    session, owner_error = ensure_session_owner(session_id, current_user)
    if owner_error:
        return owner_error

    try:
        with db_session() as db:
            rounds_count = db.scalar(select(func.count(Round.id)).where(Round.session_id == session.id)) or 0
            persistent_session = db.get(Session, session.id)
            if not persistent_session:
                return ApiResponse.not_found("面试会话")
            persistent_session.current_round = int(rounds_count) + 1
            persistent_session.status = "generating"
            next_round = persistent_session.current_round

        from backend.services.question import get_question_generation_service

        service = get_question_generation_service()
        result = service.generate_questions(session_id)

        if not result.get("success"):
            with db_session() as db:
                persistent_session = db.get(Session, session.id)
                if persistent_session:
                    persistent_session.current_round = max(0, int(next_round) - 1)
                    persistent_session.status = (
                        "round_completed" if persistent_session.current_round > 0 else "initialized"
                    )
            return ApiResponse.error(result.get("error", "生成面试题失败"))

        with db_session() as db:
            persistent_session = db.get(Session, session.id)
            if persistent_session:
                persistent_session.status = "interviewing"

        _start_llm_server(session_id, session.room.id, result, result.get("round_index", 0))
        return ApiResponse.success(data=result)

    except Exception as exc:
        logger.error("Failed to generate questions: %s", exc, exc_info=True)
        try:
            rollback_session = SessionService.get_session(session_id)
            if rollback_session:
                with db_session() as db:
                    persistent_session = db.get(Session, rollback_session.id)
                    if persistent_session:
                        persistent_session.current_round = max(0, persistent_session.current_round - 1)
                        persistent_session.status = (
                            "round_completed" if persistent_session.current_round > 0 else "initialized"
                        )
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

    content = payload.content
    company = payload.company
    position = payload.position

    try:
        from backend.clients.rag_client import get_rag_client

        rag_client = get_rag_client()
        jd_id = rag_client.upload_jd(
            memory_id=room.memory_id,
            company=company,
            position=position,
            content=content,
        )

        with db_session() as db:
            persistent_room = db.get(Room, room.id)
            if not persistent_room:
                return ApiResponse.not_found("面试间")
            persistent_room.jd_id = jd_id

        return ApiResponse.success(data={"jd_id": jd_id}, message="JD上传成功")
    except Exception as exc:
        logger.error("Failed to upload JD: %s", exc, exc_info=True)
        return ApiResponse.internal_error(f"上传JD失败: {exc}")


@router.get("/api/v1/get_current_question/{round_id}")
def get_current_question(request: Request, round_id: str):
    current_user, auth_error = require_api_user(request)
    if auth_error:
        return auth_error

    round_obj = RoundService.get_round(round_id)
    if not round_obj:
        return ApiResponse.not_found("轮次")

    if round_obj.session.room.owner_address != current_user:
        return ApiResponse.forbidden()

    try:
        from backend.services.question import get_question_generation_service

        service = get_question_generation_service()
        question_data = service.get_current_question(round_id)

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

        qa_round = RoundService.get_round(qa.round_id)
        if not qa_round:
            return ApiResponse.not_found("轮次")

        if qa_round.session.room.owner_address != current_user:
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


@router.get("/api/v1/get_qa_analysis/{session_id}/{round_index}")
def get_qa_analysis(request: Request, session_id: str, round_index: int):
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
        analysis_filename = f"rooms/{room_id}/sessions/{session_id}/analysis/qa_complete_{round_index}.json"
        analysis_data = download_qa_analysis(room_id, session_id, round_index)

        if analysis_data:
            return ApiResponse.success(
                data={"analysis_data": analysis_data, "file_path": analysis_filename}
            )
        return ApiResponse.not_found("分析数据")
    except Exception as exc:
        logger.error("Failed to get QA analysis: %s", exc, exc_info=True)
        return ApiResponse.internal_error(f"获取分析数据失败: {exc}")


@router.post("/api/v1/qa_completion/{session_id}/{round_index}")
def confirm_qa_completion(
    request: Request,
    session_id: str,
    round_index: int,
    payload: QACompletionRequest | None = None,
):
    if not is_valid_uuid(session_id):
        return ApiResponse.bad_request("无效的session_id格式")

    current_user, auth_error = require_api_user(request)
    if auth_error:
        return auth_error

    session_obj, owner_error = ensure_session_owner(session_id, current_user)
    if owner_error:
        return owner_error

    idempotency_key = request.headers.get("Idempotency-Key") or (
        payload.idempotency_key if payload else None
    )
    event_time = datetime.now().isoformat()

    round_obj = RoundService.get_round_by_session_and_index(session_obj.id, round_index)
    if not round_obj:
        return ApiResponse.not_found("轮次")

    room_id = session_obj.room.id
    qa_object_path = f"rooms/{room_id}/sessions/{session_id}/analysis/qa_complete_{round_index}.json"

    if not minio_client.object_exists(qa_object_path):
        logger.warning(
            "QA object missing for session %s round %s at %s (idempotency_key=%s)",
            session_id,
            round_index,
            qa_object_path,
            idempotency_key,
        )
        return ApiResponse.error(
            message="qa object missing",
            code=ResponseCode.CONFLICT,
            data={"qa_object_path": qa_object_path},
        )

    try:
        with db_session() as db:
            persistent_round = db.get(Round, round_obj.id)
            persistent_session = db.get(Session, session_obj.id)
            if not persistent_round or not persistent_session:
                return ApiResponse.not_found("面试会话")

            if persistent_round.status != "completed":
                persistent_round.status = "completed"
                persistent_session.status = "round_completed"
    except Exception as exc:
        logger.error(
            "Failed to update completion status for session %s round %s: %s",
            session_id,
            round_index,
            exc,
            exc_info=True,
        )
        return ApiResponse.internal_error("更新轮次状态失败")

    logger.info(
        "QA completion confirmed for session %s round %s: path=%s, idempotency_key=%s, timestamp=%s",
        session_id,
        round_index,
        qa_object_path,
        idempotency_key,
        event_time,
    )

    return ApiResponse.success(
        data={"is_completed": True, "qa_object_path": qa_object_path},
        message="轮次完成确认成功",
    )
