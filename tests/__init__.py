"""测试包初始化：统一隔离测试运行环境。"""

import os

os.environ.setdefault("JWT_SECRET", "test-jwt-secret")
os.environ.setdefault("QWEN_API_KEY", "test-qwen-key")
os.environ["DATABASE_PATH"] = "/tmp/yeying_test_suite.db"
