"""功能测试：更新简历信息（真实链路）。"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.resume_service import ResumeService
from tests.modules.resume.base import ResumeApiBaseTest


class TestUpdateResume(ResumeApiBaseTest):
    """验证 PUT /api/resumes/<resume_id>。"""

    def test_update_resume_success(self):
        resume = ResumeService.create_resume(
            owner_address=self.current_user,
            name=self.unique_name("更新前简历"),
            file_name="resume.pdf",
            file_size=512,
        )

        new_name = self.unique_name("更新后简历")
        response = self.client.put(
            f"/api/resumes/{resume.id}",
            json={
                "name": new_name,
                "company": "目标公司A",
                "position": "后端开发工程师",
            },
        )
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["success"])

        updated = payload["data"]["resume"]
        self.assertEqual(updated["id"], resume.id)
        self.assertEqual(updated["name"], new_name)
        self.assertEqual(updated["company"], "目标公司A")
        self.assertEqual(updated["position"], "后端开发工程师")


if __name__ == "__main__":
    import unittest

    unittest.main()
