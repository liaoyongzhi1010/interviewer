"""面试会话相关 API 路由。"""

from fastapi import APIRouter, Request
from sqlalchemy import select

from backend.api.deps import ensure_room_owner, ensure_session_owner, is_valid_uuid, require_api_user
from backend.api.response import ApiResponse
from backend.models import QuestionAnswer, SessionLocal
from backend.services.interview_service import SessionService

router = APIRouter(tags=["Session"])


@router.get("/api/v1/sessions/{room_id}")
def get_sessions(request: Request, room_id: str):
    if not is_valid_uuid(room_id):
        return ApiResponse.bad_request("无效的room_id格式")

    current_user, auth_error = require_api_user(request)
    if auth_error:
        return auth_error

    _, owner_error = ensure_room_owner(room_id, current_user)
    if owner_error:
        return owner_error

    sessions = SessionService.get_sessions_by_room(room_id)
    return ApiResponse.success(data=[SessionService.to_dict(session) for session in sessions])


@router.delete("/api/v1/sessions/{session_id}")
def delete_session(request: Request, session_id: str):
    if not is_valid_uuid(session_id):
        return ApiResponse.bad_request("无效的session_id格式")

    current_user, auth_error = require_api_user(request)
    if auth_error:
        return auth_error

    _, owner_error = ensure_session_owner(session_id, current_user)
    if owner_error:
        return owner_error

    success = SessionService.delete_session(session_id)
    if success:
        return ApiResponse.success(message="面试会话删除成功")
    return ApiResponse.not_found("面试会话")


@router.get("/api/v1/session/{session_id}/qa")
def get_session_qa(request: Request, session_id: str):
    if not is_valid_uuid(session_id):
        return ApiResponse.bad_request("无效的session_id格式")

    current_user, auth_error = require_api_user(request)
    if auth_error:
        return auth_error

    _, owner_error = ensure_session_owner(session_id, current_user)
    if owner_error:
        return owner_error

    with SessionLocal() as session:
        qa_records = (
            session.execute(
                select(QuestionAnswer)
                .where(QuestionAnswer.session_id == session_id)
                .order_by(QuestionAnswer.question_index)
            )
            .scalars()
            .all()
        )

    qa_list = [
        {
            "qa_id": qa.id,
            "question_index": qa.question_index,
            "question": qa.question_text,
            "answer": qa.answer_text,
            "category": qa.question_category,
            "question_type": qa.question_type,
            "depth": qa.depth,
            "parent_qa_id": qa.parent_qa_id,
            "answer_score": qa.answer_score,
            "answer_eval_brief": qa.answer_eval_brief,
            "is_answered": qa.is_answered,
        }
        for qa in qa_records
    ]
    return ApiResponse.success(
        data={
            "session_id": session_id,
            "questions_count": len(qa_list),
            "answered_count": sum(1 for qa in qa_list if qa["is_answered"]),
            "qa_list": qa_list,
        }
    )


@router.get("/api/v1/session/{session_id}/status")
def get_session_status(request: Request, session_id: str):
    if not is_valid_uuid(session_id):
        return ApiResponse.bad_request("无效的session_id格式")

    current_user, auth_error = require_api_user(request)
    if auth_error:
        return auth_error

    session, owner_error = ensure_session_owner(session_id, current_user)
    if owner_error:
        return owner_error

    status_data = {
        "status": session.status,
        "status_display": SessionService.get_status_display(session),
    }
    return ApiResponse.success(data=status_data)
