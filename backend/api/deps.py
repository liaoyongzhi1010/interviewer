"""路由鉴权与授权辅助函数。"""

from typing import Optional, Tuple

from fastapi import Request
from jose import JWTError, jwt

from backend.api.response import ApiResponse
from backend.common.config import config
from backend.common.logger import get_logger
from backend.services.interview_service import RoomService, SessionService

logger = get_logger(__name__)

AUTH_COOKIE_NAME = "auth_token"

def get_current_user_optional(request: Request) -> Optional[str]:
    token = request.cookies.get(AUTH_COOKIE_NAME)
    if not token:
        return None

    try:
        payload = jwt.decode(token, config.JWT_SECRET, algorithms=[config.JWT_ALGORITHM])
        wallet_address = payload.get("sub")
        if isinstance(wallet_address, str) and wallet_address.strip():
            return wallet_address
        return None
    except JWTError as exc:
        logger.warning("JWT validation failed: %s", exc)
        return None
    except Exception as exc:
        logger.error("Token parse error: %s", exc, exc_info=True)
        return None


def require_api_user(request: Request) -> tuple[Optional[str], Optional[object]]:
    user = get_current_user_optional(request)
    if not user:
        return None, ApiResponse.unauthorized()
    return user, None


def ensure_room_owner(room_id: str, current_user: str) -> Tuple[Optional[object], Optional[object]]:
    room = RoomService.get_room(room_id)
    if not room:
        return None, ApiResponse.not_found("面试间")
    if room.owner_address != current_user:
        logger.warning(
            "Forbidden room access: user=%s room=%s owner=%s",
            current_user,
            room_id,
            room.owner_address,
        )
        return None, ApiResponse.forbidden()
    return room, None


def ensure_session_owner(session_id: str, current_user: str) -> Tuple[Optional[object], Optional[object]]:
    session = SessionService.get_session(session_id)
    if not session:
        return None, ApiResponse.not_found("面试会话")
    if session.room.owner_address != current_user:
        logger.warning(
            "Forbidden session access: user=%s session=%s owner=%s",
            current_user,
            session_id,
            session.room.owner_address,
        )
        return None, ApiResponse.forbidden()
    return session, None


def is_valid_uuid(value: str) -> bool:
    import uuid

    try:
        uuid.UUID(value)
        return True
    except (ValueError, AttributeError, TypeError):
        return False
