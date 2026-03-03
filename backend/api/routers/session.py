"""面试会话相关 API 路由。"""

import hashlib
import hmac
import os
from datetime import datetime
from urllib.parse import urlparse, urlunparse

from fastapi import APIRouter, Request
from sqlalchemy import select

from backend.api.deps import ensure_room_owner, ensure_session_owner, is_valid_uuid, require_api_user
from backend.api.response import ApiResponse, ResponseCode
from backend.clients.digitalhub_client import boot_dh
from backend.common.logger import get_logger
from backend.models import QuestionAnswer, SessionLocal
from backend.services.interview_service import (
    RoundCompletionService,
    RoundService,
    SessionService,
)

logger = get_logger(__name__)

router = APIRouter(tags=["Session"])

DEFAULT_PUBLIC_HOST = "vtuber.yeying.pub"
PLACEHOLDER_HOSTS = {"your_public_host_here", "your-public-host"}


def _resolve_public_host() -> str:
    env_host = os.getenv("PUBLIC_HOST")
    if env_host and env_host.lower() not in PLACEHOLDER_HOSTS:
        return env_host
    return DEFAULT_PUBLIC_HOST


def _normalize_connect_url(connect_url: str | None, public_host: str) -> str | None:
    if not connect_url:
        return None

    parsed = urlparse(connect_url)
    if parsed.netloc and parsed.netloc.lower() not in PLACEHOLDER_HOSTS:
        return connect_url

    scheme = parsed.scheme or "https"
    path = parsed.path or ""
    return urlunparse((scheme, public_host, path, "", "", ""))


def _normalize_dh_message(
    message: str | None,
    raw_connect_url: str | None,
    normalized_connect_url: str | None,
    public_host: str,
) -> str | None:
    if not message:
        return None

    updated_message = message

    if raw_connect_url and normalized_connect_url and raw_connect_url != normalized_connect_url:
        updated_message = updated_message.replace(raw_connect_url, normalized_connect_url)

    for placeholder in PLACEHOLDER_HOSTS:
        if placeholder in updated_message:
            updated_message = updated_message.replace(placeholder, public_host)

    return updated_message


def _boot_digital_human(session) -> tuple[str | None, str | None]:
    try:
        public_host = _resolve_public_host()
        resp = boot_dh(session.room_id, session.id, public_host=public_host)
        data = resp.get("data") or {}

        raw_connect_url = data.get("connect_url")
        dh_connect_url = _normalize_connect_url(raw_connect_url, public_host)
        dh_message = _normalize_dh_message(data.get("message"), raw_connect_url, dh_connect_url, public_host)
        return dh_message, dh_connect_url
    except Exception as exc:
        logger.warning("Failed to boot digital human for session %s: %s", session.id, exc)
        return None, None


def _load_round_questions(session_id: str, round_index: int):
    round_obj = RoundService.get_round_by_session_and_index(session_id, round_index)
    if not round_obj:
        return []

    with SessionLocal() as session:
        qa_records = (
            session.execute(
                select(QuestionAnswer)
                .where(QuestionAnswer.round_id == round_obj.id)
                .order_by(QuestionAnswer.question_index)
            )
            .scalars()
            .all()
        )

    questions_data = []
    for qa in qa_records:
        questions_data.append(
            {
                "question": qa.question_text,
                "answer": qa.answer_text if qa.is_answered else None,
                "category": qa.question_category,
                "is_answered": qa.is_answered,
            }
        )

    return questions_data


def _load_session_rounds(session):
    rounds = RoundService.get_rounds_by_session(session.id)
    rounds_dict = []

    for round_obj in rounds:
        round_data = RoundService.to_dict(round_obj)
        try:
            questions = _load_round_questions(session.id, round_data["round_index"])
            round_data["questions"] = questions
        except Exception as exc:
            logger.error("Error loading questions for round %s: %s", round_data.get("id"), exc)
            round_data["questions"] = []

        rounds_dict.append(round_data)

    return rounds_dict


def _verify_webhook_signature(request: Request, body_bytes: bytes) -> bool:
    secret = os.getenv("WEBHOOK_SECRET")
    if not secret:
        logger.error("WEBHOOK_SECRET 未配置，无法验证签名")
        return False

    signature = request.headers.get("X-DH-Signature")
    if not signature:
        logger.warning("缺少 X-DH-Signature 请求头")
        return False

    try:
        body_text = body_bytes.decode("utf-8")
    except UnicodeDecodeError:
        body_text = body_bytes.decode("utf-8", errors="replace")

    message = f"{request.method.upper()}{request.url.path}{body_text}".encode("utf-8")
    expected_signature = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()

    if not hmac.compare_digest(expected_signature, signature):
        logger.warning("签名验证失败: expected=%s, received=%s", expected_signature, signature)
        return False

    return True


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


@router.get("/api/v1/rounds/{session_id}")
def get_rounds(request: Request, session_id: str):
    if not is_valid_uuid(session_id):
        return ApiResponse.bad_request("无效的session_id格式")

    current_user, auth_error = require_api_user(request)
    if auth_error:
        return auth_error

    _, owner_error = ensure_session_owner(session_id, current_user)
    if owner_error:
        return owner_error

    rounds = RoundService.get_rounds_by_session(session_id)
    return ApiResponse.success(data=[RoundService.to_dict(round_obj) for round_obj in rounds])


@router.post("/api/v1/rounds/complete")
async def complete_round_webhook(request: Request):
    body_bytes = await request.body()

    try:
        json_payload = await request.json()
    except Exception:
        return ApiResponse.bad_request("请求体必须为JSON对象")

    if not isinstance(json_payload, dict):
        return ApiResponse.bad_request("请求体必须为JSON对象")

    required_fields = [
        "room_id",
        "session_id",
        "round_index",
        "qa_object",
        "occurred_at",
        "idempotency_key",
    ]
    missing_fields = [field for field in required_fields if json_payload.get(field) is None]
    if missing_fields:
        return ApiResponse.bad_request(f"缺少必要字段: {', '.join(missing_fields)}")

    if not _verify_webhook_signature(request, body_bytes):
        return ApiResponse.error("签名验证失败", code=ResponseCode.UNAUTHORIZED)

    room_id = str(json_payload["room_id"])
    session_id = str(json_payload["session_id"])
    round_index_raw = json_payload["round_index"]
    qa_object = json_payload["qa_object"]
    occurred_at_raw = json_payload["occurred_at"]
    idempotency_key = json_payload["idempotency_key"]

    try:
        round_index = int(round_index_raw)
    except (TypeError, ValueError):
        return ApiResponse.bad_request("round_index 必须为整数")

    if not isinstance(qa_object, (dict, list)):
        return ApiResponse.bad_request("qa_object 必须为 JSON 对象")

    if not isinstance(idempotency_key, str) or not idempotency_key.strip():
        return ApiResponse.bad_request("idempotency_key 无效")

    if not isinstance(occurred_at_raw, str):
        return ApiResponse.bad_request("occurred_at 格式不正确")

    try:
        occurred_at = datetime.fromisoformat(occurred_at_raw.replace("Z", "+00:00"))
    except ValueError:
        return ApiResponse.bad_request("occurred_at 格式不正确")

    session = SessionService.get_session(session_id)
    if not session:
        return ApiResponse.not_found("面试会话")

    if str(session.room.id) != room_id:
        return ApiResponse.bad_request("room_id 与 session_id 不匹配")

    round_obj = RoundService.get_round_by_session_and_index(session_id, round_index)
    if not round_obj:
        return ApiResponse.not_found("面试轮次")

    existing_completion = RoundCompletionService.get_by_idempotency(idempotency_key)
    if existing_completion:
        return ApiResponse.success(
            data={"completion_id": existing_completion.id},
            message="轮次完成事件已处理",
        )

    existing_completion = RoundCompletionService.get_by_session_and_index(session, round_index)
    if existing_completion:
        return ApiResponse.success(
            data={"completion_id": existing_completion.id},
            message="轮次完成事件已处理",
        )

    try:
        completion = RoundCompletionService.record_completion(
            session=session,
            round_index=round_index,
            qa_object=qa_object,
            occurred_at=occurred_at,
            idempotency_key=idempotency_key,
            round_obj=round_obj,
        )
        return ApiResponse.success(
            data={"completion_id": completion.id},
            message="轮次完成记录已创建",
        )
    except Exception as exc:
        logger.error("Failed to record round completion: %s", exc, exc_info=True)
        return ApiResponse.internal_error("处理轮次完成事件失败")


@router.post("/api/v1/session/{session_id}/boot_dh")
def boot_digital_human_async(request: Request, session_id: str):
    if not is_valid_uuid(session_id):
        return ApiResponse.bad_request("无效的session_id格式")

    current_user, auth_error = require_api_user(request)
    if auth_error:
        return auth_error

    session, owner_error = ensure_session_owner(session_id, current_user)
    if owner_error:
        return owner_error

    try:
        dh_message, dh_connect_url = _boot_digital_human(session)
        return ApiResponse.success(data={"message": dh_message, "connect_url": dh_connect_url})
    except Exception as exc:
        logger.error("Failed to boot digital human: %s", exc)
        return ApiResponse.internal_error(f"启动数字人失败: {exc}")


@router.get("/api/v1/session/{session_id}/rounds")
def get_session_rounds_async(request: Request, session_id: str):
    if not is_valid_uuid(session_id):
        return ApiResponse.bad_request("无效的session_id格式")

    current_user, auth_error = require_api_user(request)
    if auth_error:
        return auth_error

    session, owner_error = ensure_session_owner(session_id, current_user)
    if owner_error:
        return owner_error

    try:
        rounds_dict = _load_session_rounds(session)
        return ApiResponse.success(data=rounds_dict)
    except Exception as exc:
        logger.error("Failed to load session rounds: %s", exc)
        return ApiResponse.internal_error(f"加载轮次数据失败: {exc}")


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

    try:
        status_data = {
            "status": session.status,
            "current_round": session.current_round,
            "status_display": SessionService.get_status_display(session),
        }
        return ApiResponse.success(data=status_data)
    except Exception as exc:
        logger.error("Failed to get session status: %s", exc)
        return ApiResponse.internal_error(f"获取会话状态失败: {exc}")
