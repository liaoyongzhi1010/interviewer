"""功能测试：重试简历解析任务（真实链路）。"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.resume_service import ResumeService
from tests.modules.resume.base import ResumeApiBaseTest


class TestRetryParseResume(ResumeApiBaseTest):
    """验证 POST /api/resumes/<resume_id>/retry-parse。"""

    def test_retry_parse_resume_success(self):
        resume = ResumeService.create_resume(
            owner_address=self.current_user,
            name=self.unique_name("重试简历"),
            file_name="resume.pdf",
            file_size=256,
        )

        # 先把状态设为 failed，满足“允许重试”的前置条件
        ResumeService.update_parse_status(
            resume.id,
            parse_status="failed",
            parse_error="测试失败原因",
        )

        response = self.client.post(f"/api/resumes/{resume.id}/retry-parse")
        payload = response.get_json()

        self.assertEqual(response.status_code, 200, msg=f"重试解析失败: {payload}")
        self.assertTrue(payload["success"])
        self.assertEqual(payload["data"]["resume"]["id"], resume.id)
        self.assertEqual(payload["message"], "已重新提交解析任务")


if __name__ == "__main__":
    import unittest

    unittest.main()
