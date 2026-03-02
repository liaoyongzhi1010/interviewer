"""功能测试：删除简历（真实链路）。"""

import sys
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.models.models import Room
from backend.services.resume_service import ResumeService
from tests.modules.resume.base import ResumeApiBaseTest


class TestDeleteResume(ResumeApiBaseTest):
    """验证 DELETE /api/resumes/<resume_id>。"""

    def test_delete_resume_success(self):
        resume = ResumeService.create_resume(
            owner_address=self.current_user,
            name=self.unique_name("删除简历"),
            file_name="resume.pdf",
            file_size=1024,
        )

        # 准备一个关联面试间，验证删除简历时会删除关联面试间
        room = Room.create(
            id=str(uuid.uuid4()),
            memory_id=f"memory_{uuid.uuid4().hex[:8]}",
            name="删除联动测试面试间",
            owner_address=self.current_user,
            resume_id=resume.id,
        )

        response = self.client.delete(f"/api/resumes/{resume.id}")
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["success"])

        deleted_resume = ResumeService.get_resume(resume.id)
        self.assertIsNotNone(deleted_resume)
        self.assertEqual(deleted_resume.status, "deleted")

        deleted_room = Room.get_or_none(Room.id == room.id)
        self.assertIsNone(deleted_room)


if __name__ == "__main__":
    import unittest

    unittest.main()
