"""面试间相关 API 路由。"""

import threading

from fastapi import APIRouter, Request

from backend.api.deps import ensure_room_owner, is_valid_uuid, require_api_user
from backend.api.response import ApiResponse
from backend.api.schemas import CreateRoomRequest, UpdateRoomRequest, UpdateRoomResumeRequest
from backend.clients.digitalhub_client import ping_dh
from backend.common.logger import get_logger
from backend.services.interview_service import RoomService
from backend.services.resume_service import ResumeService

logger = get_logger(__name__)

router = APIRouter(tags=["Room"])


def _ping_digital_human_async() -> None:
    def _ping() -> None:
        try:
            ping_dh()
        except Exception as exc:
            logger.warning("Failed to ping digital human: %s", exc)

    threading.Thread(target=_ping, daemon=True).start()


@router.post("/api/v1/rooms/create")
def create_room(request: Request, payload: CreateRoomRequest | None = None):
    current_user, auth_error = require_api_user(request)
    if auth_error:
        return auth_error

    _ping_digital_human_async()

    resume_id = payload.resume_id if payload else None
    if resume_id:
        resume = ResumeService.get_resume(resume_id)
        if not resume:
            return ApiResponse.not_found("简历")
        if resume.owner_address != current_user:
            return ApiResponse.forbidden()

    room = RoomService.create_room(owner_address=current_user, resume_id=resume_id)
    return ApiResponse.success(data={"room_id": room.id}, message="面试间创建成功")


@router.put("/api/v1/rooms/{room_id}")
def update_room(request: Request, room_id: str, payload: UpdateRoomRequest | None = None):
    if not is_valid_uuid(room_id):
        return ApiResponse.bad_request("无效的room_id格式")

    current_user, auth_error = require_api_user(request)
    if auth_error:
        return auth_error

    _, owner_error = ensure_room_owner(room_id, current_user)
    if owner_error:
        return owner_error

    name = payload.name if payload else None
    success = RoomService.update_room(room_id=room_id, name=name)
    if not success:
        return ApiResponse.internal_error("更新失败")

    updated_room = RoomService.get_room(room_id)
    return ApiResponse.success(
        data={"room": RoomService.to_dict(updated_room)},
        message="面试间更新成功",
    )


@router.put("/api/v1/rooms/{room_id}/resume")
def update_room_resume(
    request: Request,
    room_id: str,
    payload: UpdateRoomResumeRequest,
):
    if not is_valid_uuid(room_id):
        return ApiResponse.bad_request("无效的room_id格式")

    current_user, auth_error = require_api_user(request)
    if auth_error:
        return auth_error

    _, owner_error = ensure_room_owner(room_id, current_user)
    if owner_error:
        return owner_error

    resume_id = payload.resume_id
    if not resume_id:
        return ApiResponse.bad_request("简历ID不能为空")

    resume = ResumeService.get_resume(resume_id)
    if not resume:
        return ApiResponse.not_found("简历")

    if resume.owner_address != current_user:
        return ApiResponse.forbidden()

    success = RoomService.update_room_resume(room_id=room_id, resume_id=resume_id)
    if not success:
        return ApiResponse.internal_error("更新失败")

    return ApiResponse.success(message="简历更新成功")


@router.get("/api/v1/rooms")
def get_rooms(request: Request):
    current_user, auth_error = require_api_user(request)
    if auth_error:
        return auth_error

    rooms = RoomService.get_rooms_by_owner(current_user)
    return ApiResponse.success(data=[RoomService.to_dict(room) for room in rooms])


@router.delete("/api/v1/rooms/{room_id}")
def delete_room(request: Request, room_id: str):
    if not is_valid_uuid(room_id):
        return ApiResponse.bad_request("无效的room_id格式")

    current_user, auth_error = require_api_user(request)
    if auth_error:
        return auth_error

    _, owner_error = ensure_room_owner(room_id, current_user)
    if owner_error:
        return owner_error

    success = RoomService.delete_room(room_id)
    if success:
        return ApiResponse.success(message="面试间删除成功")
    return ApiResponse.not_found("面试间")
