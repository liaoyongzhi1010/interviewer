"""应用工厂与唯一服务入口。"""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.api.response import ApiResponse, ResponseCode
from backend.api.routes import router as api_router
from backend.common.config import config
from backend.common.logger import get_logger
from backend.models import init_database
from backend.web.routes import router as web_router

logger = get_logger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def init_app() -> None:
    """初始化配置校验与数据库。"""
    is_valid, missing_configs = config.validate()
    if not is_valid:
        logger.error("Missing required configurations: %s", ", ".join(missing_configs))
        raise RuntimeError("Missing required configurations")

    init_database()
    logger.info("Database initialized successfully")


def _is_api_like_path(path: str) -> bool:
    return path.startswith("/api/")


def _extract_error_message(detail: object, fallback: str) -> tuple[str, object | None]:
    if isinstance(detail, str):
        return detail, None
    if detail is None:
        return fallback, None
    return fallback, {"detail": detail}


def create_app() -> FastAPI:
    """创建并配置应用实例。"""
    app = FastAPI(
        title="Yeying API",
        version="1.0.0",
        openapi_url="/openapi.json",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
    )

    app.mount(
        "/static",
        StaticFiles(directory=str(PROJECT_ROOT / "frontend" / "static")),
        name="static",
    )

    @app.on_event("startup")
    async def startup_event() -> None:
        # 启动时执行一次基础初始化，避免把初始化逻辑散落在路由中。
        logger.info("Starting Yeying Interviewer System (FastAPI)...")
        init_app()

    @app.middleware("http")
    async def log_request_middleware(request: Request, call_next):
        # 统一请求日志，便于线上问题排查和链路追踪。
        logger.info(
            "Request: %s %s from %s User-Agent: %s",
            request.method,
            request.url.path,
            request.client.host if request.client else "unknown",
            request.headers.get("user-agent", ""),
        )
        response = await call_next(request)
        logger.info(
            "Response: %s %s Status: %s",
            request.method,
            request.url.path,
            response.status_code,
        )
        return response

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(request: Request, exc: StarletteHTTPException):
        if _is_api_like_path(request.url.path):
            message, data = _extract_error_message(exc.detail, fallback="请求处理失败")
            return ApiResponse.error(message=message, code=exc.status_code, data=data)

        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError):
        if _is_api_like_path(request.url.path):
            return ApiResponse.error(
                message="请求参数校验失败",
                code=ResponseCode.UNPROCESSABLE_ENTITY,
                data={"errors": exc.errors()},
            )

        return JSONResponse(status_code=422, content={"detail": exc.errors()})

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception):
        # 统一兜底异常返回，接口请求与页面请求分开处理。
        logger.error("Unexpected error: %s", exc, exc_info=True)

        if _is_api_like_path(request.url.path):
            return ApiResponse.internal_error("服务器发生未知错误")

        return JSONResponse(status_code=500, content={"detail": "服务器发生未知错误"})

    app.include_router(api_router)
    app.include_router(web_router)
    return app


app = create_app()
