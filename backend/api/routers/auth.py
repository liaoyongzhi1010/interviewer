"""鉴权与登录相关 API。"""

import os
import random
import string
import time
from datetime import datetime, timedelta
from typing import Optional

from eth_account import Account
from eth_account.messages import encode_defunct
from fastapi import APIRouter, Request
from jose import jwt
from sqlalchemy import delete

from backend.api.response import ApiResponse
from backend.api.schemas import AuthChallengeRequest, AuthVerifyRequest
from backend.common.config import config
from backend.common.logger import get_logger
from backend.models import AuthChallenge, SessionLocal, db_session

logger = get_logger(__name__)

router = APIRouter(tags=["Auth"])

AUTH_COOKIE_NAME = "auth_token"
AUTH_COOKIE_SAMESITE = os.getenv("AUTH_COOKIE_SAMESITE", "Lax")
AUTH_COOKIE_DOMAIN = os.getenv("AUTH_COOKIE_DOMAIN")
GUEST_ADDRESS_PREFIX = os.getenv("GUEST_ADDRESS_PREFIX", "guest_")
CHALLENGE_TTL_MINUTES = int(os.getenv("AUTH_CHALLENGE_TTL_MINUTES", "5"))


def _to_bool(value: Optional[str], default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


AUTH_COOKIE_SECURE = _to_bool(os.getenv("AUTH_COOKIE_SECURE"), default=False)


def _generate_random_string(length: int = 8) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))


def _should_use_secure_cookie(request: Request) -> bool:
    if AUTH_COOKIE_SECURE:
        return True
    forwarded_proto = request.headers.get("X-Forwarded-Proto", "")
    proto = forwarded_proto.split(",")[0].strip().lower() if forwarded_proto else ""
    return request.url.scheme == "https" or proto == "https"


def _upsert_challenge(address: str, challenge: str) -> None:
    expires_at = datetime.utcnow() + timedelta(minutes=CHALLENGE_TTL_MINUTES)
    with db_session() as session:
        challenge_record = session.get(AuthChallenge, address)
        if challenge_record is None:
            session.add(AuthChallenge(address=address, challenge=challenge, expires_at=expires_at))
            return
        challenge_record.challenge = challenge
        challenge_record.expires_at = expires_at


def _get_valid_challenge(address: str) -> AuthChallenge | None:
    with SessionLocal() as session:
        challenge_record = session.get(AuthChallenge, address)
    if challenge_record is None:
        return None

    if challenge_record.expires_at < datetime.utcnow():
        _delete_challenge(address)
        return None

    return challenge_record


def _delete_challenge(address: str) -> None:
    with db_session() as session:
        session.execute(delete(AuthChallenge).where(AuthChallenge.address == address))


@router.post("/api/v1/auth/challenge")
def auth_challenge(payload: AuthChallengeRequest):
    address = payload.body.address
    if not address:
        return ApiResponse.bad_request("address 字段不能为空")

    random_part = _generate_random_string()
    challenge = f"请签名以登录 YeYing Wallet\\n\\n随机数: {random_part}\\n时间戳: {int(time.time() * 1000)}"

    addr_key = str(address).lower()
    _upsert_challenge(addr_key, challenge)

    return ApiResponse.success(data={"challenge": challenge}, message="挑战生成成功")


@router.post("/api/v1/auth/guest-login")
def auth_guest_login(request: Request):
    suffix = _generate_random_string(12)
    guest_address = f"{GUEST_ADDRESS_PREFIX}{suffix}".lower()

    expire = datetime.utcnow() + timedelta(hours=config.GUEST_JWT_EXPIRE_HOURS)
    token = jwt.encode(
        {"sub": guest_address, "exp": expire, "login_type": "guest"},
        config.JWT_SECRET,
        algorithm=config.JWT_ALGORITHM,
    )

    response = ApiResponse.success(
        message="游客登录成功",
        data={
            "address": guest_address,
            "login_type": "guest",
            "expires_in_hours": config.GUEST_JWT_EXPIRE_HOURS,
        },
    )

    response.set_cookie(
        AUTH_COOKIE_NAME,
        token,
        httponly=True,
        secure=_should_use_secure_cookie(request),
        samesite=AUTH_COOKIE_SAMESITE,
        max_age=config.GUEST_JWT_EXPIRE_HOURS * 3600,
        path="/",
        domain=AUTH_COOKIE_DOMAIN,
    )
    return response


@router.post("/api/v1/auth/verify")
def auth_verify(request: Request, payload: AuthVerifyRequest):
    address = payload.body.address
    signature = payload.body.signature

    if not address or not signature:
        return ApiResponse.bad_request("param address or signature is None")

    addr_key = str(address).lower()
    challenge_record = _get_valid_challenge(addr_key)
    if challenge_record is None:
        return ApiResponse.bad_request("Challenge 不存在或已过期")

    try:
        message = encode_defunct(text=challenge_record.challenge)
        recovered_address = Account.recover_message(message, signature=signature)

        if recovered_address.lower() != addr_key:
            return ApiResponse.bad_request("签名验证失败")

        _delete_challenge(addr_key)

        expire = datetime.utcnow() + timedelta(hours=config.JWT_EXPIRE_HOURS)
        token = jwt.encode(
            {"sub": addr_key, "exp": expire},
            config.JWT_SECRET,
            algorithm=config.JWT_ALGORITHM,
        )

        response = ApiResponse.success(message="登录成功", data={"token": token})
        response.set_cookie(
            AUTH_COOKIE_NAME,
            token,
            httponly=True,
            secure=_should_use_secure_cookie(request),
            samesite=AUTH_COOKIE_SAMESITE,
            max_age=config.JWT_EXPIRE_HOURS * 3600,
            path="/",
            domain=AUTH_COOKIE_DOMAIN,
        )
        return response
    except Exception as exc:
        logger.error("Signature verification failed: %s", exc)
        return ApiResponse.bad_request(f"authVerify failed: {exc}")


@router.post("/api/v1/auth/logout")
def auth_logout(request: Request):
    response = ApiResponse.success(message="退出成功")
    response.set_cookie(
        AUTH_COOKIE_NAME,
        "",
        expires=0,
        path="/",
        domain=AUTH_COOKIE_DOMAIN,
        secure=_should_use_secure_cookie(request),
        samesite=AUTH_COOKIE_SAMESITE,
        httponly=True,
    )
    return response
