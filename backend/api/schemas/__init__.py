"""接口请求模型导出。"""

from backend.api.schemas.auth import AuthChallengeRequest, AuthVerifyRequest
from backend.api.schemas.question import QACompletionRequest, SaveAnswerRequest, UploadJDRequest
from backend.api.schemas.resume import UpdateResumeRequest
from backend.api.schemas.room import CreateRoomRequest, UpdateRoomRequest, UpdateRoomResumeRequest

__all__ = [
    "AuthChallengeRequest",
    "AuthVerifyRequest",
    "CreateRoomRequest",
    "UpdateRoomRequest",
    "UpdateRoomResumeRequest",
    "UploadJDRequest",
    "SaveAnswerRequest",
    "QACompletionRequest",
    "UpdateResumeRequest",
]
