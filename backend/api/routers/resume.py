"""简历相关 API 路由。"""

import os
import shutil
import tempfile

from fastapi import APIRouter, File, Form, Request, UploadFile
from sqlalchemy import select

from backend.api.deps import is_valid_uuid, require_api_user
from backend.api.response import ApiResponse
from backend.api.schemas import UpdateResumeRequest
from backend.clients.minio_client import (
    delete_resume_data,
    delete_resume_pdf,
    download_resume_data,
    upload_resume_pdf,
)
from backend.common.logger import get_logger
from backend.models import Room, SessionLocal
from backend.services.interview_service import RoomService
from backend.services.resume_parse_service import submit_resume_parse_task
from backend.services.resume_service import ResumeService

logger = get_logger(__name__)

router = APIRouter(tags=["Resume"])


def _save_temp_file(uploaded_file: UploadFile) -> str:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
        shutil.copyfileobj(uploaded_file.file, temp_file)
        return temp_file.name


@router.post("/api/v1/resumes/upload")
def upload_resume(
    request: Request,
    resume: UploadFile | None = File(default=None),
    name: str | None = Form(default=None),
    company: str | None = Form(default=None),
    position: str | None = Form(default=None),
):
    current_user, auth_error = require_api_user(request)
    if auth_error:
        return auth_error

    try:
        if resume is None:
            return ApiResponse.bad_request("没有上传文件")

        if not resume.filename:
            return ApiResponse.bad_request("没有选择文件")

        if not resume.filename.lower().endswith(".pdf"):
            return ApiResponse.bad_request("只支持PDF格式")

        resume_name = (name or "").strip() or resume.filename
        company_value = (company or "").strip() or None
        position_value = (position or "").strip() or None

        if ResumeService.check_name_exists(current_user, resume_name):
            return ApiResponse.bad_request(f"简历名称 '{resume_name}' 已存在，请使用其他名称")

        temp_path = _save_temp_file(resume)

        try:
            try:
                resume_obj = ResumeService.create_resume(
                    owner_address=current_user,
                    name=resume_name,
                    file_name=os.path.basename(resume.filename),
                    file_size=os.path.getsize(temp_path),
                    company=company_value,
                    position=position_value,
                )
            except ValueError as exc:
                return ApiResponse.bad_request(str(exc))

            pdf_saved = upload_resume_pdf(temp_path, resume_obj.id)
            if not pdf_saved:
                ResumeService.delete_resume(resume_obj.id)
                return ApiResponse.internal_error("原始PDF保存失败")

            parse_task_started = submit_resume_parse_task(resume_obj.id)
            message = "简历上传成功，正在后台解析"

            if not parse_task_started:
                ResumeService.update_parse_status(
                    resume_obj.id,
                    parse_status="failed",
                    parse_error="解析任务提交失败，请稍后重试",
                )
                message = "简历上传成功，但解析任务提交失败"

            latest_resume = ResumeService.get_resume(resume_obj.id) or resume_obj
            return ApiResponse.success(
                data={"resume": ResumeService.to_dict(latest_resume)},
                message=message,
            )
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    except Exception as exc:
        logger.error("Failed to upload resume: %s", exc, exc_info=True)
        return ApiResponse.internal_error(f"上传失败: {exc}")


@router.get("/api/v1/resumes")
def list_resumes(request: Request):
    current_user, auth_error = require_api_user(request)
    if auth_error:
        return auth_error

    try:
        resumes = ResumeService.get_resumes_by_owner(current_user)
        resumes_dict = [ResumeService.to_dict(resume) for resume in resumes]
        stats = ResumeService.get_resume_stats(current_user)
        return ApiResponse.success(data={"resumes": resumes_dict, "stats": stats})
    except Exception as exc:
        logger.error("Failed to list resumes: %s", exc, exc_info=True)
        return ApiResponse.internal_error(f"获取简历列表失败: {exc}")


@router.get("/api/v1/resumes/{resume_id}")
def get_resume(request: Request, resume_id: str):
    if not is_valid_uuid(resume_id):
        return ApiResponse.bad_request("无效的resume_id格式")

    current_user, auth_error = require_api_user(request)
    if auth_error:
        return auth_error

    try:
        resume = ResumeService.get_resume(resume_id)
        if not resume:
            return ApiResponse.not_found("简历")

        if resume.owner_address != current_user:
            return ApiResponse.forbidden()

        resume_data = None
        if resume.parse_status == "parsed":
            resume_data = download_resume_data(resume_id)

        return ApiResponse.success(
            data={"resume": ResumeService.to_dict(resume), "resume_data": resume_data}
        )
    except Exception as exc:
        logger.error("Failed to get resume: %s", exc, exc_info=True)
        return ApiResponse.internal_error(f"获取简历失败: {exc}")


@router.post("/api/v1/resumes/{resume_id}/retry-parse")
def retry_parse_resume(request: Request, resume_id: str):
    if not is_valid_uuid(resume_id):
        return ApiResponse.bad_request("无效的resume_id格式")

    current_user, auth_error = require_api_user(request)
    if auth_error:
        return auth_error

    try:
        resume = ResumeService.get_resume(resume_id)
        if not resume:
            return ApiResponse.not_found("简历")

        if resume.owner_address != current_user:
            return ApiResponse.forbidden()

        if resume.status != "active":
            return ApiResponse.bad_request("简历已删除，无法重试解析")

        if resume.parse_status in {"pending", "parsing"}:
            return ApiResponse.bad_request("该简历正在解析中，请稍后查看结果")

        ResumeService.update_parse_status(resume_id=resume_id, parse_status="pending", parse_error=None)

        task_submitted = submit_resume_parse_task(resume_id)
        if not task_submitted:
            return ApiResponse.internal_error("解析任务提交失败，请稍后重试")

        latest_resume = ResumeService.get_resume(resume_id) or resume
        return ApiResponse.success(
            data={"resume": ResumeService.to_dict(latest_resume)},
            message="已重新提交解析任务",
        )
    except Exception as exc:
        logger.error("Failed to retry parse task for %s: %s", resume_id, exc, exc_info=True)
        return ApiResponse.internal_error(f"重试解析失败: {exc}")


@router.put("/api/v1/resumes/{resume_id}")
def update_resume(request: Request, resume_id: str, payload: UpdateResumeRequest):
    if not is_valid_uuid(resume_id):
        return ApiResponse.bad_request("无效的resume_id格式")

    current_user, auth_error = require_api_user(request)
    if auth_error:
        return auth_error

    try:
        resume = ResumeService.get_resume(resume_id)
        if not resume:
            return ApiResponse.not_found("简历")

        if resume.owner_address != current_user:
            return ApiResponse.forbidden()

        name = payload.name
        company = payload.company
        position = payload.position

        try:
            success = ResumeService.update_resume(
                resume_id=resume_id,
                name=name,
                company=company,
                position=position,
            )
        except ValueError as exc:
            return ApiResponse.bad_request(str(exc))

        if not success:
            return ApiResponse.internal_error("更新失败")

        updated_resume = ResumeService.get_resume(resume_id)
        return ApiResponse.success(
            data={"resume": ResumeService.to_dict(updated_resume)},
            message="简历更新成功",
        )
    except Exception as exc:
        logger.error("Failed to update resume: %s", exc, exc_info=True)
        return ApiResponse.internal_error(f"更新失败: {exc}")


@router.delete("/api/v1/resumes/{resume_id}")
def delete_resume(request: Request, resume_id: str):
    if not is_valid_uuid(resume_id):
        return ApiResponse.bad_request("无效的resume_id格式")

    current_user, auth_error = require_api_user(request)
    if auth_error:
        return auth_error

    try:
        resume = ResumeService.get_resume(resume_id)
        if not resume:
            return ApiResponse.not_found("简历")

        if resume.owner_address != current_user:
            return ApiResponse.forbidden()

        with SessionLocal() as session:
            linked_room_ids = session.execute(select(Room.id).where(Room.resume_id == resume_id)).scalars().all()
        for room_id in linked_room_ids:
            RoomService.delete_room(room_id)

        ResumeService.delete_resume(resume_id)

        delete_resume_data(resume_id)
        delete_resume_pdf(resume_id)

        return ApiResponse.success(message="简历删除成功")
    except Exception as exc:
        logger.error("Failed to delete resume: %s", exc, exc_info=True)
        return ApiResponse.internal_error(f"删除失败: {exc}")


@router.get("/api/v1/rooms/{room_id}/resume")
def get_resume_by_room(request: Request, room_id: str):
    if not is_valid_uuid(room_id):
        return ApiResponse.bad_request("无效的room_id格式")

    current_user, auth_error = require_api_user(request)
    if auth_error:
        return auth_error

    try:
        room = RoomService.get_room(room_id)
        if not room:
            return ApiResponse.not_found("面试间")

        if room.owner_address != current_user:
            return ApiResponse.forbidden()

        if not room.resume_id:
            return ApiResponse.success(data={"resume": None}, message="该面试间尚未关联简历")

        resume = ResumeService.get_resume(room.resume_id)
        if not resume:
            return ApiResponse.success(data={"resume": None}, message="关联的简历不存在")

        resume_data = None
        if resume.parse_status == "parsed":
            resume_data = download_resume_data(resume.id)

        return ApiResponse.success(
            data={"resume": ResumeService.to_dict(resume), "resume_data": resume_data}
        )
    except Exception as exc:
        logger.error("Failed to get resume by room: %s", exc, exc_info=True)
        return ApiResponse.internal_error(f"获取简历失败: {exc}")
