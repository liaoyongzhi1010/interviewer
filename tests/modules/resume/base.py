"""简历模块真实业务测试公共基类（无 mock）。"""

import os
import sys
import time
import uuid
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from flask import Flask
from jose import jwt

from backend.controllers.resume_controller import resume_bp
from backend.models.models import (
    database,
    init_database,
    Resume,
    Room,
    Session,
    Round,
    QuestionAnswer,
    RoundCompletion,
)

# 与后端鉴权中间件保持一致
JWT_SECRET = "e802e988a02546cc47415e4bc76346aae7ceece97a0f950319c861a5de38b20d"
JWT_ALGORITHM = "HS256"
TEST_USER = "0xabc123"

TEST_DB_DIR = PROJECT_ROOT / "tests" / "data"
TEST_PDF_PATH = PROJECT_ROOT / "tests" / "data" / "resume.pdf"


def build_auth_token(wallet_address: str = TEST_USER) -> str:
    """构造用于 require_auth 的有效 JWT。"""
    payload = {
        "sub": wallet_address.lower(),
        "exp": int(time.time()) + 3600,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


class ResumeApiBaseTest(unittest.TestCase):
    """简历模块 API 测试基类：真实路由 + 真实数据库。"""

    _db_prepared = False
    _shared_app = None

    @classmethod
    def setUpClass(cls) -> None:
        # 整套用例只准备一次数据库，避免异步线程与删库冲突
        if not ResumeApiBaseTest._db_prepared:
            test_db_path = TEST_DB_DIR / f"resume_module_test_{os.getpid()}.db"

            if not database.is_closed():
                database.close()
            if test_db_path.exists():
                test_db_path.unlink()

            database.init(str(test_db_path))
            init_database()
            ResumeApiBaseTest._db_prepared = True

        if ResumeApiBaseTest._shared_app is None:
            app = Flask(__name__)
            app.register_blueprint(resume_bp)
            ResumeApiBaseTest._shared_app = app

        cls.app = ResumeApiBaseTest._shared_app

    @classmethod
    def tearDownClass(cls) -> None:
        # 异步解析任务可能还在运行，此处不主动关闭连接
        return

    def setUp(self) -> None:
        self.current_user = TEST_USER

        # 每个用例前清理数据库，保证测试互不影响
        if database.is_closed():
            database.connect()

        QuestionAnswer.delete().execute()
        RoundCompletion.delete().execute()
        Round.delete().execute()
        Session.delete().execute()
        Room.delete().execute()
        Resume.delete().execute()

        self.client = self.app.test_client()
        # 自动注入登录态，避免每个测试重复登录流程
        self.client.set_cookie("auth_token", build_auth_token(self.current_user))

    def unique_name(self, prefix: str = "测试简历") -> str:
        """生成唯一简历名，避免重名冲突。"""
        return f"{prefix}_{uuid.uuid4().hex[:8]}"

    def upload_resume_via_api(self, name: str | None = None, company: str = "测试公司", position: str = "测试岗位"):
        """通过真实 API 上传简历。"""
        resume_name = name or self.unique_name("上传简历")

        with open(TEST_PDF_PATH, "rb") as f:
            response = self.client.post(
                "/api/resumes/upload",
                data={
                    "name": resume_name,
                    "company": company,
                    "position": position,
                    "resume": (f, "resume.pdf"),
                },
                content_type="multipart/form-data",
            )

        return response
