"""功能测试：上传简历（真实链路）。"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.resume_service import ResumeService
from tests.modules.resume.base import ResumeApiBaseTest


class TestUploadResume(ResumeApiBaseTest):
    """验证 POST /api/resumes/upload。"""

    def test_upload_resume_success(self):
        response = self.upload_resume_via_api()
        payload = response.get_json()

        self.assertEqual(response.status_code, 200, msg=f"上传失败: {payload}")
        self.assertTrue(payload["success"])

        resume_data = payload["data"]["resume"]
        resume_id = resume_data["id"]
        self.assertTrue(resume_id)
        self.assertIn(resume_data.get("parse_status"), {"pending", "parsing", "parsed", "failed"})

        # 校验：简历记录确实落库
        db_resume = ResumeService.get_resume(resume_id)
        self.assertIsNotNone(db_resume)
        self.assertEqual(db_resume.owner_address, self.current_user)


if __name__ == "__main__":
    import unittest

    unittest.main()
