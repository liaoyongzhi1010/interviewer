"""错题管理请求模型。"""

from pydantic import BaseModel


class UpdateMistakeRequest(BaseModel):
    status: str | None = None
    note: str | None = None
