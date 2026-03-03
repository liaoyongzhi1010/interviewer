"""接口冒烟测试。"""

import os
import unittest

from fastapi.testclient import TestClient

# 为测试提供最小必需配置，避免依赖本机环境变量文件。
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")
os.environ.setdefault("QWEN_API_KEY", "test-qwen-key")
os.environ.setdefault("DATABASE_PATH", "/tmp/yeying_test.db")

from backend.main import app
from backend.models import init_database


class FastAPISmokeTest(unittest.TestCase):
    def setUp(self) -> None:
        init_database()
        self.client = TestClient(app)

    def test_openapi_and_docs_available(self) -> None:
        openapi_resp = self.client.get("/openapi.json")
        self.assertEqual(openapi_resp.status_code, 200)
        self.assertIn("paths", openapi_resp.json())

        docs_resp = self.client.get("/api/docs")
        self.assertEqual(docs_resp.status_code, 200)

    def test_auth_guard_on_api(self) -> None:
        resp = self.client.get("/api/v1/resumes")
        self.assertEqual(resp.status_code, 401)
        body = resp.json()
        self.assertFalse(body.get("success"))
        self.assertEqual(body.get("code"), 401)

    def test_api_not_found_uses_standard_response(self) -> None:
        resp = self.client.get("/api/v1/not-found-endpoint")
        self.assertEqual(resp.status_code, 404)
        body = resp.json()
        self.assertFalse(body.get("success"))
        self.assertEqual(body.get("code"), 404)
        self.assertIn("timestamp", body)

    def test_api_validation_error_uses_standard_response(self) -> None:
        resp = self.client.post("/api/v1/auth/challenge", json={})
        self.assertEqual(resp.status_code, 422)
        body = resp.json()
        self.assertFalse(body.get("success"))
        self.assertEqual(body.get("code"), 422)
        self.assertIn("timestamp", body)

    def test_guest_login_can_access_protected_api(self) -> None:
        login_resp = self.client.post("/api/v1/auth/guest-login")
        self.assertEqual(login_resp.status_code, 200)

        resumes_resp = self.client.get("/api/v1/resumes")
        self.assertEqual(resumes_resp.status_code, 200)
        self.assertTrue(resumes_resp.json().get("success"))


if __name__ == "__main__":
    unittest.main()
