"""报告相关 API 路由（无轮次版本）。"""

from fastapi import APIRouter, Request
from fastapi.responses import Response

from backend.api.deps import ensure_session_owner, is_valid_uuid, require_api_user
from backend.api.response import ApiResponse, ResponseCode
from backend.clients.minio_client import download_evaluation_report, minio_client
from backend.common.logger import get_logger
from backend.models import Session, db_session

logger = get_logger(__name__)

router = APIRouter(tags=["Report"])


@router.post("/api/v1/generate_report/{session_id}")
def generate_report(request: Request, session_id: str):
    if not is_valid_uuid(session_id):
        return ApiResponse.bad_request("无效的session_id格式")

    current_user, auth_error = require_api_user(request)
    if auth_error:
        return auth_error

    interview_session, owner_error = ensure_session_owner(session_id, current_user)
    if owner_error:
        return owner_error

    try:
        from backend.services.evaluation_service import get_evaluation_service
        from backend.services.pdf import get_pdf_generator

        room_id = interview_session.room.id
        evaluation_filename = f"rooms/{room_id}/sessions/{session_id}/reports/evaluation.json"
        pdf_filename = f"rooms/{room_id}/sessions/{session_id}/reports/report.pdf"
        with db_session() as db:
            persistent_session = db.get(Session, interview_session.id)
            if not persistent_session:
                return ApiResponse.not_found("面试会话")
            if persistent_session.status == "analyzing":
                return ApiResponse.bad_request("报告正在生成中，请稍候")
            if persistent_session.status != "completed":
                return ApiResponse.bad_request("面试尚未完成，无法生成报告")

            evaluation_exists = minio_client.object_exists(evaluation_filename)
            pdf_exists = minio_client.object_exists(pdf_filename)
            if evaluation_exists or pdf_exists:
                return ApiResponse.error(
                    message="报告已存在，无需重复生成",
                    code=ResponseCode.CONFLICT,
                    data={
                        "evaluation_exists": evaluation_exists,
                        "pdf_exists": pdf_exists,
                    },
                )

            persistent_session.status = "analyzing"

        evaluation_service = get_evaluation_service()
        eval_result = evaluation_service.generate_evaluation_report(session_id)

        if not eval_result.get("success"):
            with db_session() as db:
                persistent_session = db.get(Session, interview_session.id)
                if persistent_session:
                    persistent_session.status = "completed"
            return ApiResponse.error(eval_result.get("error", "生成评价失败"))

        pdf_generator = get_pdf_generator()
        pdf_bytes = pdf_generator.generate_report_pdf(eval_result["report_data"])

        if not pdf_bytes:
            with db_session() as db:
                persistent_session = db.get(Session, interview_session.id)
                if persistent_session:
                    persistent_session.status = "completed"
            return ApiResponse.error("PDF生成失败")

        pdf_filename = pdf_generator.save_pdf_to_minio(pdf_bytes, room_id, session_id)
        if not pdf_filename:
            with db_session() as db:
                persistent_session = db.get(Session, interview_session.id)
                if persistent_session:
                    persistent_session.status = "completed"
            return ApiResponse.error("PDF保存失败")

        with db_session() as db:
            persistent_session = db.get(Session, interview_session.id)
            if persistent_session:
                persistent_session.status = "completed"

        return ApiResponse.success(
            data={
                "evaluation_filename": eval_result["report_filename"],
                "pdf_filename": pdf_filename,
                "report_data": eval_result["report_data"],
            }
        )
    except Exception as exc:
        with db_session() as db:
            persistent_session = db.get(Session, interview_session.id)
            if persistent_session:
                persistent_session.status = "completed"
        logger.error("Failed to generate report: %s", exc, exc_info=True)
        return ApiResponse.internal_error(f"生成报告失败: {exc}")


@router.get("/api/v1/reports/{session_id}")
def get_report(request: Request, session_id: str):
    if not is_valid_uuid(session_id):
        return ApiResponse.bad_request("无效的session_id格式")

    current_user, auth_error = require_api_user(request)
    if auth_error:
        return auth_error

    interview_session, owner_error = ensure_session_owner(session_id, current_user)
    if owner_error:
        return owner_error

    try:
        room_id = interview_session.room.id
        evaluation_filename = f"rooms/{room_id}/sessions/{session_id}/reports/evaluation.json"
        evaluation_data = download_evaluation_report(room_id, session_id)

        pdf_filename = f"rooms/{room_id}/sessions/{session_id}/reports/report.pdf"
        pdf_exists = minio_client.object_exists(pdf_filename)

        if evaluation_data:
            return ApiResponse.success(
                data={
                    "evaluation_data": evaluation_data,
                    "evaluation_filename": evaluation_filename,
                    "pdf_filename": pdf_filename if pdf_exists else None,
                    "pdf_exists": pdf_exists,
                }
            )
        return ApiResponse.not_found("报告")
    except Exception as exc:
        logger.error("Failed to get report: %s", exc, exc_info=True)
        return ApiResponse.internal_error(f"获取报告失败: {exc}")


@router.get("/api/v1/reports/download/{session_id}")
def download_report_pdf(request: Request, session_id: str):
    if not is_valid_uuid(session_id):
        return ApiResponse.bad_request("无效的session_id格式")

    current_user, auth_error = require_api_user(request)
    if auth_error:
        return auth_error

    interview_session, owner_error = ensure_session_owner(session_id, current_user)
    if owner_error:
        return owner_error

    pdf_object = None
    try:
        room_id = interview_session.room.id
        pdf_filename = f"rooms/{room_id}/sessions/{session_id}/reports/report.pdf"

        pdf_object = minio_client.client.get_object(minio_client.bucket_name, pdf_filename)
        pdf_data = pdf_object.read()

        return Response(
            content=pdf_data,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename=interview_report_{session_id}.pdf"
            },
        )
    except Exception as exc:
        logger.error("Failed to download report: %s", exc, exc_info=True)
        return ApiResponse.not_found("PDF文件")
    finally:
        if pdf_object is not None:
            pdf_object.close()
            pdf_object.release_conn()


@router.get("/api/v1/reports/list/{session_id}")
def list_session_reports(request: Request, session_id: str):
    if not is_valid_uuid(session_id):
        return ApiResponse.bad_request("无效的session_id格式")

    current_user, auth_error = require_api_user(request)
    if auth_error:
        return auth_error

    interview_session, owner_error = ensure_session_owner(session_id, current_user)
    if owner_error:
        return owner_error

    try:
        room_id = interview_session.room.id

        evaluation_filename = f"rooms/{room_id}/sessions/{session_id}/reports/evaluation.json"
        evaluation_exists = minio_client.object_exists(evaluation_filename)

        pdf_filename = f"rooms/{room_id}/sessions/{session_id}/reports/report.pdf"
        pdf_exists = minio_client.object_exists(pdf_filename)

        return ApiResponse.success(
            data={
                "session_id": session_id,
                "report_available": evaluation_exists or pdf_exists,
                "evaluation_exists": evaluation_exists,
                "pdf_exists": pdf_exists,
                "evaluation_filename": evaluation_filename if evaluation_exists else None,
                "pdf_filename": pdf_filename if pdf_exists else None,
            }
        )
    except Exception as exc:
        logger.error("Failed to list reports: %s", exc, exc_info=True)
        return ApiResponse.internal_error(f"获取报告列表失败: {exc}")
