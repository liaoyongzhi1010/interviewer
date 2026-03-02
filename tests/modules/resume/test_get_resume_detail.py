"""功能测试：按简历 ID 获取简历详情（真实链路）。"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.resume_service import ResumeService
from tests.modules.resume.base import ResumeApiBaseTest


class TestGetResumeDetail(ResumeApiBaseTest):
    """验证 GET /api/resumes/<resume_id>。"""

    def test_get_resume_detail_success(self):
        resume = ResumeService.create_resume(
            owner_address=self.current_user,
            name=self.unique_name("详情简历"),
            file_name="resume.pdf",
            file_size=128,
        )

        response = self.client.get(f"/api/resumes/{resume.id}")
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["data"]["resume"]["id"], resume.id)

        # parse_status 为 pending 时，接口应返回 resume_data = None
        self.assertIsNone(payload["data"]["resume_data"])


if __name__ == "__main__":
    import unittest

    unittest.main()
