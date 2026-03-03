"""本地开发启动入口：`python -m backend`。"""

import uvicorn

from backend.common.config import config
from backend.common.logger import get_logger

logger = get_logger(__name__)


def main() -> None:
    """启动 FastAPI 开发服务。"""
    logger.info("Server running on http://%s:%s", config.APP_HOST, config.APP_PORT)
    logger.info("Debug mode: %s", config.APP_DEBUG)
    uvicorn.run(
        "backend.main:app",
        host=config.APP_HOST,
        port=config.APP_PORT,
        reload=config.APP_DEBUG,
        log_level="info",
    )


if __name__ == "__main__":
    main()
