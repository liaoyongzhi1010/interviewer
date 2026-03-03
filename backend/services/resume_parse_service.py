"""
简历异步解析服务
将上传与识别/结构化提取解耦，避免上传主链路被外部服务阻塞
"""

import os
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Set

from backend.clients.minio_client import upload_resume_data, get_resume_pdf_url
from backend.clients.mineru_client import get_mineru_client
from backend.common.logger import get_logger
from backend.services.resume_parser import get_resume_parser
from backend.services.resume_service import ResumeService

logger = get_logger(__name__)

_max_workers = max(1, int(os.getenv('RESUME_PARSE_WORKERS', '2')))
_executor = ThreadPoolExecutor(max_workers=_max_workers, thread_name_prefix='resume-parse')
_inflight_tasks: Set[str] = set()
_inflight_lock = threading.Lock()


def submit_resume_parse_task(resume_id: str) -> bool:
    """
    提交简历异步解析任务

    Args:
        resume_id: 简历ID

    Returns:
        是否成功提交
    """
    with _inflight_lock:
        if resume_id in _inflight_tasks:
            logger.info(f"Resume parse task already in flight: {resume_id}")
            return True
        _inflight_tasks.add(resume_id)

    try:
        future = _executor.submit(_parse_resume_job, resume_id)
        future.add_done_callback(lambda _: _mark_task_done(resume_id))
        logger.info(f"Submitted async parse task for resume: {resume_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to submit async parse task for {resume_id}: {e}", exc_info=True)
        _mark_task_done(resume_id)
        ResumeService.update_parse_status(
            resume_id,
            parse_status='failed',
            parse_error=f"解析任务提交失败: {e}"
        )
        return False


def _mark_task_done(resume_id: str) -> None:
    """标记任务完成，释放进行中状态"""
    with _inflight_lock:
        _inflight_tasks.discard(resume_id)


def _parse_resume_job(resume_id: str) -> None:
    """后台任务：获取原始简历访问链接 -> 文档识别 -> 结构化提取 -> 保存结果"""

    try:
        resume = ResumeService.get_resume(resume_id)
        if not resume or resume.status != 'active':
            logger.warning(f"Resume missing or inactive, skip parse task: {resume_id}")
            return

        ResumeService.update_parse_status(resume_id, parse_status='parsing', parse_error=None)

        # 直接使用原始简历预签名链接，避免本地临时文件和二次上传中转
        pdf_url = get_resume_pdf_url(resume_id, expires_hours=24)
        if not pdf_url:
            _fail_parse(resume_id, "获取原始PDF访问链接失败，请重新上传简历")
            return

        mineru_client = get_mineru_client()
        markdown_content = mineru_client.parse_pdf_from_url(pdf_url)
        if not markdown_content:
            _fail_parse(
                resume_id,
                mineru_client.get_last_error() or "PDF解析失败，请稍后重试"
            )
            return

        resume_parser = get_resume_parser()
        structured_data = resume_parser.extract_resume_data(markdown_content)
        if not structured_data:
            _fail_parse(
                resume_id,
                resume_parser.get_last_error() or "简历结构化提取失败"
            )
            return

        # 以用户输入为准覆盖公司和岗位
        if resume.company:
            structured_data['company'] = resume.company
        if resume.position:
            structured_data['position'] = resume.position

        if not upload_resume_data(structured_data, resume_id):
            _fail_parse(resume_id, "保存结构化简历数据失败")
            return

        ResumeService.update_parse_status(resume_id, parse_status='parsed', parse_error=None)
        logger.info(f"Async resume parse succeeded: {resume_id}")

    except Exception as e:
        logger.error(f"Async resume parse failed unexpectedly for {resume_id}: {e}", exc_info=True)
        _fail_parse(resume_id, f"解析异常: {e}")


def _fail_parse(resume_id: str, message: str) -> None:
    """统一处理解析失败"""
    ResumeService.update_parse_status(resume_id, parse_status='failed', parse_error=message)
    logger.error(f"Async resume parse failed: {resume_id}, reason: {message}")
