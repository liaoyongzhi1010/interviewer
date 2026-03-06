"""集中配置管理模块。"""

import os
from typing import Optional
from dotenv import load_dotenv

load_dotenv()


class Config:
    """应用配置单例。"""

    _instance: Optional['Config'] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """初始化配置（执行一次）。"""
        if self._initialized:
            return

        # 运行时配置
        self.SECRET_KEY = os.getenv('SECRET_KEY')
        self.JWT_SECRET = os.getenv('JWT_SECRET') or self.SECRET_KEY
        self.JWT_ALGORITHM = os.getenv('JWT_ALGORITHM', 'HS256')
        self.JWT_EXPIRE_HOURS = int(os.getenv('JWT_EXPIRE_HOURS', '1'))
        self.GUEST_JWT_EXPIRE_HOURS = int(os.getenv('GUEST_JWT_EXPIRE_HOURS', '12'))
        self.APP_DEBUG = os.getenv('APP_DEBUG', 'False').lower() in ('true', '1', 'yes')
        self.LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()

        # 数据库配置
        self.DATABASE_PATH = os.getenv('DATABASE_PATH', 'data/yeying_interviewer.db')

        # 大模型配置
        self.QWEN_BASE_URL = os.getenv('QWEN_BASE_URL', 'https://dashscope.aliyuncs.com/api/v1')
        self.QWEN_API_KEY = os.getenv('QWEN_API_KEY') or os.getenv('API_KEY')
        self.MODEL_NAME = os.getenv('MODEL_NAME', 'qwen-turbo')

        # RAG 服务配置
        self.RAG_ENABLED = os.getenv('RAG_ENABLED', 'false').lower() in ('true', '1', 'yes', 'on')
        self.RAG_API_URL = os.getenv('RAG_API_URL', 'http://localhost:8000')
        self.RAG_TIMEOUT = int(os.getenv('RAG_TIMEOUT', '30'))

        # 文档解析服务配置
        self.MINERU_API_KEY = os.getenv('MINERU_API_KEY')
        self.MINERU_API_URL = os.getenv('MINERU_API_URL', 'https://mineru.net/api/v4')

        # 对象存储配置
        self.MINIO_ENDPOINT = os.getenv('MINIO_ENDPOINT', 'test-minio.yeying.pub')
        self.MINIO_ACCESS_KEY = os.getenv('MINIO_ACCESS_KEY')
        self.MINIO_SECRET_KEY = os.getenv('MINIO_SECRET_KEY')
        self.MINIO_BUCKET = os.getenv('MINIO_BUCKET', 'yeying-interviewer')
        self.MINIO_SECURE = os.getenv('MINIO_SECURE', 'true').lower() == 'true'

        # 应用配置
        self.APP_HOST = os.getenv('APP_HOST', '0.0.0.0')
        self.APP_PORT = int(os.getenv('APP_PORT', '8080'))

        self._initialized = True

    def validate(self) -> tuple[bool, list[str]]:
        """
        验证必需的配置项

        Returns:
            (is_valid, missing_configs): 是否有效，缺失的配置列表
        """
        missing = []

        # 必需的配置项
        required_configs = {
            'JWT_SECRET': self.JWT_SECRET,
            'QWEN_API_KEY': self.QWEN_API_KEY,
            'MINIO_ACCESS_KEY': self.MINIO_ACCESS_KEY,
            'MINIO_SECRET_KEY': self.MINIO_SECRET_KEY,
        }

        for name, value in required_configs.items():
            if not value:
                missing.append(name)

        return len(missing) == 0, missing


# 全局配置实例
config = Config()
