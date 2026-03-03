"""简历请求模型。"""

from pydantic import BaseModel


class UpdateResumeRequest(BaseModel):
    name: str | None = None
    company: str | None = None
    position: str | None = None
