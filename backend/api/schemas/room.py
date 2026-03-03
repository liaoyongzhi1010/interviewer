"""面试间请求模型。"""

from pydantic import BaseModel


class CreateRoomRequest(BaseModel):
    resume_id: str | None = None


class UpdateRoomRequest(BaseModel):
    name: str | None = None


class UpdateRoomResumeRequest(BaseModel):
    resume_id: str
