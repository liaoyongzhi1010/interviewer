"""简历模块 API 测试（覆盖核心成功与异常分支）。"""

import os
import uuid
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

# 为测试提供最小必需配置，避免依赖本机环境变量文件。
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")
os.environ.setdefault("QWEN_API_KEY", "test-qwen-key")
os.environ["DATABASE_PATH"] = "/tmp/yeying_test_resume_api.db"

from backend.main import app
from backend.models import (
    AuthChallenge,
    QuestionAnswer,
    Resume,
    Room,
    Session,
    SessionLocal,
    db_session,
    init_database,
)


class ResumeApiTest(unittest.TestCase):
    def setUp(self) -> None:
        init_database()
        self._clean_tables()
        self.client = TestClient(app)

        login_resp = self.client.post("/api/v1/auth/guest-login")
        self.assertEqual(login_resp.status_code, 200)
        self.owner_address = login_resp.json()["data"]["address"]

    def _clean_tables(self) -> None:
        # 按外键依赖顺序清理，保证测试互不影响。
        with db_session() as session:
            session.execute(delete(QuestionAnswer))
            session.execute(delete(Session))
            session.execute(delete(Room))
            session.execute(delete(Resume))
            session.execute(delete(AuthChallenge))

    def _assert_api_response(
        self,
        response,
        *,
        status_code: int,
        success: bool,
        code: int,
    ) -> dict:
        self.assertEqual(response.status_code, status_code)
        body = response.json()
        self.assertEqual(body["success"], success)
        self.assertEqual(body["code"], code)
        self.assertIn("message", body)
        self.assertIn("data", body)
        self.assertIn("timestamp", body)
        return body

    def _create_resume(
        self,
        *,
        owner_address: str | None = None,
        name: str = "默认简历",
        status: str = "active",
        parse_status: str = "pending",
    ) -> Resume:
        resume = Resume(
            id=str(uuid.uuid4()),
            owner_address=owner_address or self.owner_address,
            name=name,
            status=status,
            parse_status=parse_status,
            file_name=f"{name}.pdf",
        )
        with db_session() as session:
            session.add(resume)
        return resume

    def _create_room(
        self,
        *,
        owner_address: str | None = None,
        resume_id: str | None = None,
    ) -> Room:
        room = Room(
            id=str(uuid.uuid4()),
            memory_id=f"memory_{uuid.uuid4().hex[:8]}",
            name="测试面试间",
            owner_address=owner_address or self.owner_address,
            resume_id=resume_id,
        )
        with db_session() as session:
            session.add(room)
        return room

    def test_list_resumes_unauthorized(self) -> None:
        anon_client = TestClient(app)
        resp = anon_client.get("/api/v1/resumes")
        self._assert_api_response(resp, status_code=401, success=False, code=401)

    def test_list_resumes_empty(self) -> None:
        resp = self.client.get("/api/v1/resumes")
        body = self._assert_api_response(resp, status_code=200, success=True, code=200)
        self.assertEqual(body["data"]["resumes"], [])

    def test_upload_resume_missing_file(self) -> None:
        resp = self.client.post("/api/v1/resumes/upload", data={"name": "空上传"})
        self._assert_api_response(resp, status_code=400, success=False, code=400)

    def test_upload_resume_reject_non_pdf(self) -> None:
        resp = self.client.post(
            "/api/v1/resumes/upload",
            files={"resume": ("resume.txt", b"not-pdf", "text/plain")},
            data={"name": "bad"},
        )
        self._assert_api_response(resp, status_code=400, success=False, code=400)

    @patch("backend.api.routers.resume.submit_resume_parse_task", return_value=True)
    @patch("backend.api.routers.resume.upload_resume_pdf", return_value=True)
    def test_upload_resume_reject_duplicate_name(self, _mock_upload, _mock_submit) -> None:
        self._create_resume(name="重复名简历")
        pdf_path = Path("tests/data/resume.pdf")

        with pdf_path.open("rb") as fp:
            resp = self.client.post(
                "/api/v1/resumes/upload",
                files={"resume": ("resume.pdf", fp, "application/pdf")},
                data={"name": "重复名简历"},
            )

        self._assert_api_response(resp, status_code=400, success=False, code=400)

    @patch("backend.api.routers.resume.submit_resume_parse_task", return_value=True)
    @patch("backend.api.routers.resume.upload_resume_pdf", return_value=True)
    def test_upload_resume_success(self, _mock_upload, _mock_submit) -> None:
        pdf_path = Path("tests/data/resume.pdf")
        with pdf_path.open("rb") as fp:
            resp = self.client.post(
                "/api/v1/resumes/upload",
                files={"resume": ("resume.pdf", fp, "application/pdf")},
                data={"name": "简历A", "company": "OpenAI", "position": "工程师"},
            )

        body = self._assert_api_response(resp, status_code=200, success=True, code=200)
        self.assertEqual(body["data"]["resume"]["name"], "简历A")
        with SessionLocal() as session:
            resume_count = session.scalar(
                select(func.count(Resume.id)).where(Resume.owner_address == self.owner_address)
            )
        self.assertEqual(int(resume_count or 0), 1)

    def test_get_resume_invalid_uuid(self) -> None:
        resp = self.client.get("/api/v1/resumes/not-a-uuid")
        self._assert_api_response(resp, status_code=400, success=False, code=400)

    def test_get_resume_not_found(self) -> None:
        resp = self.client.get(f"/api/v1/resumes/{uuid.uuid4()}")
        self._assert_api_response(resp, status_code=404, success=False, code=404)

    def test_get_resume_forbidden_when_not_owner(self) -> None:
        resume = self._create_resume(owner_address="guest_other_owner", name="别人的简历")
        resp = self.client.get(f"/api/v1/resumes/{resume.id}")
        self._assert_api_response(resp, status_code=403, success=False, code=403)

    @patch("backend.api.routers.resume.download_resume_data", return_value={"name": "候选人"})
    def test_get_resume_detail_with_parsed_data(self, _mock_download) -> None:
        resume = self._create_resume(name="可解析简历", parse_status="parsed")
        resp = self.client.get(f"/api/v1/resumes/{resume.id}")
        body = self._assert_api_response(resp, status_code=200, success=True, code=200)
        self.assertEqual(body["data"]["resume_data"]["name"], "候选人")

    def test_retry_parse_invalid_uuid(self) -> None:
        resp = self.client.post("/api/v1/resumes/not-a-uuid/retry-parse")
        self._assert_api_response(resp, status_code=400, success=False, code=400)

    def test_retry_parse_not_found(self) -> None:
        resp = self.client.post(f"/api/v1/resumes/{uuid.uuid4()}/retry-parse")
        self._assert_api_response(resp, status_code=404, success=False, code=404)

    def test_retry_parse_forbidden(self) -> None:
        resume = self._create_resume(owner_address="guest_other_owner", name="别人的简历")
        resp = self.client.post(f"/api/v1/resumes/{resume.id}/retry-parse")
        self._assert_api_response(resp, status_code=403, success=False, code=403)

    def test_retry_parse_reject_when_pending(self) -> None:
        resume = self._create_resume(name="待解析简历", parse_status="pending")
        resp = self.client.post(f"/api/v1/resumes/{resume.id}/retry-parse")
        self._assert_api_response(resp, status_code=400, success=False, code=400)

    def test_retry_parse_reject_when_deleted(self) -> None:
        resume = self._create_resume(name="已删除简历", status="deleted", parse_status="failed")
        resp = self.client.post(f"/api/v1/resumes/{resume.id}/retry-parse")
        self._assert_api_response(resp, status_code=400, success=False, code=400)

    @patch("backend.api.routers.resume.submit_resume_parse_task", return_value=False)
    def test_retry_parse_submit_failed(self, _mock_submit) -> None:
        resume = self._create_resume(name="失败简历", parse_status="failed")
        resp = self.client.post(f"/api/v1/resumes/{resume.id}/retry-parse")
        self._assert_api_response(resp, status_code=500, success=False, code=500)

    @patch("backend.api.routers.resume.submit_resume_parse_task", return_value=True)
    def test_retry_parse_success_when_failed(self, _mock_submit) -> None:
        resume = self._create_resume(name="失败简历", parse_status="failed")
        resp = self.client.post(f"/api/v1/resumes/{resume.id}/retry-parse")
        self._assert_api_response(resp, status_code=200, success=True, code=200)
        with SessionLocal() as session:
            refreshed = session.get(Resume, resume.id)
        self.assertIsNotNone(refreshed)
        self.assertEqual(refreshed.parse_status, "pending")

    def test_update_resume_invalid_uuid(self) -> None:
        resp = self.client.put("/api/v1/resumes/not-a-uuid", json={"name": "更新名"})
        self._assert_api_response(resp, status_code=400, success=False, code=400)

    def test_update_resume_not_found(self) -> None:
        resp = self.client.put(f"/api/v1/resumes/{uuid.uuid4()}", json={"name": "更新名"})
        self._assert_api_response(resp, status_code=404, success=False, code=404)

    def test_update_resume_forbidden(self) -> None:
        resume = self._create_resume(owner_address="guest_other_owner", name="别人的简历")
        resp = self.client.put(f"/api/v1/resumes/{resume.id}", json={"name": "更新名"})
        self._assert_api_response(resp, status_code=403, success=False, code=403)

    def test_update_resume_name_conflict(self) -> None:
        resume_a = self._create_resume(name="简历A")
        resume_b = self._create_resume(name="简历B")
        resp = self.client.put(f"/api/v1/resumes/{resume_b.id}", json={"name": resume_a.name})
        self._assert_api_response(resp, status_code=400, success=False, code=400)

    def test_update_resume_success(self) -> None:
        resume = self._create_resume(name="原始简历")
        resp = self.client.put(
            f"/api/v1/resumes/{resume.id}",
            json={"name": "新简历名", "company": "OpenAI", "position": "算法工程师"},
        )
        body = self._assert_api_response(resp, status_code=200, success=True, code=200)
        self.assertEqual(body["data"]["resume"]["name"], "新简历名")
        self.assertEqual(body["data"]["resume"]["company"], "OpenAI")
        self.assertEqual(body["data"]["resume"]["position"], "算法工程师")

    def test_delete_resume_invalid_uuid(self) -> None:
        resp = self.client.delete("/api/v1/resumes/not-a-uuid")
        self._assert_api_response(resp, status_code=400, success=False, code=400)

    def test_delete_resume_not_found(self) -> None:
        resp = self.client.delete(f"/api/v1/resumes/{uuid.uuid4()}")
        self._assert_api_response(resp, status_code=404, success=False, code=404)

    def test_delete_resume_forbidden(self) -> None:
        resume = self._create_resume(owner_address="guest_other_owner", name="别人的简历")
        resp = self.client.delete(f"/api/v1/resumes/{resume.id}")
        self._assert_api_response(resp, status_code=403, success=False, code=403)

    @patch("backend.api.routers.resume.delete_resume_pdf", return_value=True)
    @patch("backend.api.routers.resume.delete_resume_data", return_value=True)
    def test_delete_resume_success(self, _mock_delete_data, _mock_delete_pdf) -> None:
        resume = self._create_resume(name="待删除简历")
        self._create_room(resume_id=resume.id)

        resp = self.client.delete(f"/api/v1/resumes/{resume.id}")
        self._assert_api_response(resp, status_code=200, success=True, code=200)

        with SessionLocal() as session:
            refreshed = session.get(Resume, resume.id)
        self.assertIsNotNone(refreshed)
        self.assertEqual(refreshed.status, "deleted")

    def test_get_resume_by_room_invalid_uuid(self) -> None:
        resp = self.client.get("/api/v1/rooms/not-a-uuid/resume")
        self._assert_api_response(resp, status_code=400, success=False, code=400)

    def test_get_resume_by_room_not_found(self) -> None:
        resp = self.client.get(f"/api/v1/rooms/{uuid.uuid4()}/resume")
        self._assert_api_response(resp, status_code=404, success=False, code=404)

    def test_get_resume_by_room_forbidden(self) -> None:
        room = self._create_room(owner_address="guest_other_owner")
        resp = self.client.get(f"/api/v1/rooms/{room.id}/resume")
        self._assert_api_response(resp, status_code=403, success=False, code=403)

    def test_get_resume_by_room_without_linked_resume(self) -> None:
        room = self._create_room(resume_id=None)
        resp = self.client.get(f"/api/v1/rooms/{room.id}/resume")
        body = self._assert_api_response(resp, status_code=200, success=True, code=200)
        self.assertIsNone(body["data"]["resume"])

    def test_get_resume_by_room_linked_resume_missing(self) -> None:
        room = self._create_room(resume_id=str(uuid.uuid4()))
        resp = self.client.get(f"/api/v1/rooms/{room.id}/resume")
        body = self._assert_api_response(resp, status_code=200, success=True, code=200)
        self.assertIsNone(body["data"]["resume"])

    @patch("backend.api.routers.resume.download_resume_data", return_value={"name": "候选人"})
    def test_get_resume_by_room_with_parsed_resume(self, _mock_download) -> None:
        resume = self._create_resume(name="可解析简历", parse_status="parsed")
        room = self._create_room(resume_id=resume.id)
        resp = self.client.get(f"/api/v1/rooms/{room.id}/resume")
        body = self._assert_api_response(resp, status_code=200, success=True, code=200)
        self.assertEqual(body["data"]["resume"]["id"], resume.id)
        self.assertEqual(body["data"]["resume_data"]["name"], "候选人")


if __name__ == "__main__":
    unittest.main()
