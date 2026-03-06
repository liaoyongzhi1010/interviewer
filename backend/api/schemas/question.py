"""题目与问答请求模型。"""

from pydantic import BaseModel


class UploadJDRequest(BaseModel):
    content: str
    company: str | None = None
    position: str | None = None


class SaveAnswerRequest(BaseModel):
    qa_id: str
    answer_text: str
