"""错题收藏相关 API 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Request
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.api.deps import is_valid_uuid, require_api_user
from backend.api.response import ApiResponse
from backend.api.schemas import UpdateMistakeRequest
from backend.models import QuestionAnswer, Session, SessionLocal
from backend.services.mistake_service import MistakeService

router = APIRouter(tags=["Mistake"])


def _load_qa_with_owner(qa_id: str):
    with SessionLocal() as session:
        return session.execute(
            select(QuestionAnswer)
            .where(QuestionAnswer.id == qa_id)
            .options(selectinload(QuestionAnswer.session).selectinload(Session.room))
        ).scalar_one_or_none()


@router.post("/api/v1/mistakes/favorite/{qa_id}")
def favorite_question(request: Request, qa_id: str):
    if not is_valid_uuid(qa_id):
        return ApiResponse.bad_request("无效的qa_id格式")

    current_user, auth_error = require_api_user(request)
    if auth_error:
        return auth_error

    qa = _load_qa_with_owner(qa_id)
    if not qa or not qa.session or not qa.session.room:
        return ApiResponse.not_found("问答记录")

    if qa.session.room.owner_address != current_user:
        return ApiResponse.forbidden()

    item, created = MistakeService.upsert_favorite(
        current_user,
        qa_id=qa.id,
        session_id=qa.session_id,
        session_name=qa.session.name,
        room_id=qa.session.room.id,
        room_name=qa.session.room.name,
        question_text=qa.question_text,
        answer_text=qa.answer_text,
        question_category=qa.question_category,
        answer_score=qa.answer_score,
        source="manual_favorite",
    )

    return ApiResponse.success(
        data={"mistake": MistakeService.to_dict(item), "created": created},
        message="收藏成功" if created else "已在错题集中",
    )


@router.delete("/api/v1/mistakes/favorite/{qa_id}")
def unfavorite_question(request: Request, qa_id: str):
    if not is_valid_uuid(qa_id):
        return ApiResponse.bad_request("无效的qa_id格式")

    current_user, auth_error = require_api_user(request)
    if auth_error:
        return auth_error

    deleted = MistakeService.remove_favorite(current_user, qa_id)
    if deleted:
        return ApiResponse.success(message="已取消收藏")
    return ApiResponse.success(message="该题目未收藏")


@router.get("/api/v1/mistakes/favorite/{qa_id}")
def get_favorite_status(request: Request, qa_id: str):
    if not is_valid_uuid(qa_id):
        return ApiResponse.bad_request("无效的qa_id格式")

    current_user, auth_error = require_api_user(request)
    if auth_error:
        return auth_error

    return ApiResponse.success(
        data={"qa_id": qa_id, "is_favorited": MistakeService.is_favorited(current_user, qa_id)}
    )


@router.get("/api/v1/mistakes")
def list_mistakes(
    request: Request,
    status: str | None = None,
    category: str | None = None,
    keyword: str | None = None,
):
    current_user, auth_error = require_api_user(request)
    if auth_error:
        return auth_error

    items = MistakeService.list_items(
        current_user,
        status=(status or "").strip() or None,
        category=(category or "").strip() or None,
        keyword=(keyword or "").strip() or None,
    )

    return ApiResponse.success(
        data={
            "items": [MistakeService.to_dict(item) for item in items],
            "stats": MistakeService.build_stats(items),
        }
    )


@router.patch("/api/v1/mistakes/{mistake_id}")
def update_mistake(request: Request, mistake_id: str, payload: UpdateMistakeRequest):
    if not is_valid_uuid(mistake_id):
        return ApiResponse.bad_request("无效的mistake_id格式")

    current_user, auth_error = require_api_user(request)
    if auth_error:
        return auth_error

    try:
        item = MistakeService.update_item(
            mistake_id,
            current_user,
            status=payload.status,
            note=payload.note,
        )
    except ValueError as exc:
        return ApiResponse.bad_request(str(exc))

    if not item:
        return ApiResponse.not_found("错题项")

    return ApiResponse.success(data={"item": MistakeService.to_dict(item)}, message="更新成功")


@router.post("/api/v1/mistakes/{mistake_id}/review")
def review_mistake(request: Request, mistake_id: str):
    if not is_valid_uuid(mistake_id):
        return ApiResponse.bad_request("无效的mistake_id格式")

    current_user, auth_error = require_api_user(request)
    if auth_error:
        return auth_error

    item = MistakeService.record_review(mistake_id, current_user)
    if not item:
        return ApiResponse.not_found("错题项")

    return ApiResponse.success(data={"item": MistakeService.to_dict(item)}, message="已记录复习")
