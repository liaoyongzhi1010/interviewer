"""统一接口响应辅助函数。"""

from datetime import datetime
from typing import Any

from fastapi.responses import JSONResponse


class ResponseCode:
    SUCCESS = 200
    CREATED = 201
    BAD_REQUEST = 400
    UNAUTHORIZED = 401
    FORBIDDEN = 403
    NOT_FOUND = 404
    CONFLICT = 409
    UNPROCESSABLE_ENTITY = 422
    INTERNAL_ERROR = 500


class ApiResponse:
    @staticmethod
    def _build(success: bool, code: int, message: str, data: Any = None) -> JSONResponse:
        return JSONResponse(
            content={
                "success": success,
                "code": code,
                "message": message,
                "data": data,
                "timestamp": datetime.now().isoformat(),
            },
            status_code=code,
        )

    @staticmethod
    def success(data: Any = None, message: str = "操作成功", code: int = ResponseCode.SUCCESS) -> JSONResponse:
        return ApiResponse._build(True, code, message, data)

    @staticmethod
    def created(data: Any = None, message: str = "创建成功") -> JSONResponse:
        return ApiResponse.success(data=data, message=message, code=ResponseCode.CREATED)

    @staticmethod
    def error(message: str, code: int = ResponseCode.BAD_REQUEST, data: Any = None) -> JSONResponse:
        return ApiResponse._build(False, code, message, data)

    @staticmethod
    def bad_request(message: str = "请求参数错误") -> JSONResponse:
        return ApiResponse.error(message=message, code=ResponseCode.BAD_REQUEST)

    @staticmethod
    def unauthorized(message: str = "未授权，请先登录") -> JSONResponse:
        return ApiResponse.error(message=message, code=ResponseCode.UNAUTHORIZED)

    @staticmethod
    def forbidden(message: str = "无权访问此资源") -> JSONResponse:
        return ApiResponse.error(message=message, code=ResponseCode.FORBIDDEN)

    @staticmethod
    def not_found(resource: str = "资源") -> JSONResponse:
        return ApiResponse.error(message=f"{resource}不存在", code=ResponseCode.NOT_FOUND)

    @staticmethod
    def internal_error(message: str = "服务器内部错误") -> JSONResponse:
        return ApiResponse.error(message=message, code=ResponseCode.INTERNAL_ERROR)
