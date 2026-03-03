"""鉴权请求模型。"""

from pydantic import BaseModel


class AuthChallengePayload(BaseModel):
    address: str


class AuthChallengeRequest(BaseModel):
    body: AuthChallengePayload


class AuthVerifyPayload(BaseModel):
    address: str
    signature: str


class AuthVerifyRequest(BaseModel):
    body: AuthVerifyPayload
