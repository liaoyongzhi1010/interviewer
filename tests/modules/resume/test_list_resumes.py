"""功能测试：获取简历列表（真实链路）。"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.resume_service import ResumeService
from tests.modules.resume.base import ResumeApiBaseTest


class TestListResumes(ResumeApiBaseTest):
    """验证 GET /api/resumes。"""

    def test_list_resumes_success(self):
        # 准备数据：创建两份简历，其中一份标记为 parsed
        r1 = ResumeService.create_resume(
            owner_address=self.current_user,
            name=self.unique_name("列表简历A"),
            file_name="resume.pdf",
            file_size=123,
        )
        r2 = ResumeService.create_resume(
            owner_address=self.current_user,
            name=self.unique_name("列表简历B"),
            file_name="resume.pdf",
            file_size=456,
        )
        ResumeService.update_parse_status(r2.id, parse_status="parsed", parse_error=None)

        response = self.client.get("/api/resumes")
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["success"])

        resumes = payload["data"]["resumes"]
        stats = payload["data"]["stats"]
        resume_ids = {item["id"] for item in resumes}

        self.assertIn(r1.id, resume_ids)
        self.assertIn(r2.id, resume_ids)
        self.assertEqual(stats["total_resumes"], 2)
        self.assertEqual(stats["parsed_resumes"], 1)


if __name__ == "__main__":
    import unittest

    unittest.main()
