"""功能测试：按面试间 ID 获取关联简历（真实链路）。"""

import sys
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.models.models import Room
from backend.services.resume_service import ResumeService
from tests.modules.resume.base import ResumeApiBaseTest


class TestGetResumeByRoom(ResumeApiBaseTest):
    """验证 GET /api/resume/<room_id>。"""

    def test_get_resume_by_room_success(self):
        resume = ResumeService.create_resume(
            owner_address=self.current_user,
            name=self.unique_name("房间关联简历"),
            file_name="resume.pdf",
            file_size=2048,
        )

        room = Room.create(
            id=str(uuid.uuid4()),
            memory_id=f"memory_{uuid.uuid4().hex[:8]}",
            name="关联简历面试间",
            owner_address=self.current_user,
            resume_id=resume.id,
        )

        response = self.client.get(f"/api/resume/{room.id}")
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["data"]["resume"]["id"], resume.id)

        # parse_status 为 pending 时，接口不会读取结构化数据
        self.assertIsNone(payload["data"]["resume_data"])


if __name__ == "__main__":
    import unittest

    unittest.main()
