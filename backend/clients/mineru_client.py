"""
MinerU 文档解析服务客户端
"""

import os
import time
import requests
from typing import Optional
from dotenv import load_dotenv
from backend.common.logger import get_logger

load_dotenv()

logger = get_logger(__name__)


class MinerUClient:
    """文档识别解析客户端"""

    def __init__(self):
        self.api_key = os.getenv("MINERU_API_KEY")
        self.base_url = os.getenv("MINERU_API_URL", "https://mineru.net/api/v4")
        self.last_error: Optional[str] = None

        if not self.api_key:
            raise ValueError("MINERU_API_KEY not found in environment variables")

        # 认证头格式：凭证前缀 + 空格 + 令牌
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def parse_pdf_from_url(self, pdf_url: str) -> Optional[str]:
        """
        通过已存在的PDF访问链接解析PDF，返回Markdown格式内容

        Args:
            pdf_url: 可被 MinerU 访问的 PDF 预签名 URL

        Returns:
            Markdown格式的解析内容，失败返回None
        """
        self.last_error = None

        if not pdf_url:
            self.last_error = "PDF访问链接为空"
            return None

        try:
            return self._parse_pdf_url(pdf_url)
        except Exception as e:
            logger.error(f"Error parsing PDF from URL with MinerU: {e}", exc_info=True)
            self.last_error = f"MinerU 解析异常: {e}"
            return None

    def _parse_pdf_url(self, pdf_url: str) -> Optional[str]:
        """提交并轮询 MinerU 解析任务（输入为 PDF URL）"""
        # 提交解析任务
        task_id = self._submit_parse_task(pdf_url)
        if not task_id:
            logger.error("Failed to submit parse task")
            if not self.last_error:
                self.last_error = "提交 PDF 解析任务失败"
            return None

        logger.info(f"Parse task submitted, task_id: {task_id}")

        # 轮询解析状态并获取结果
        return self._poll_parse_result(task_id)

    def _submit_parse_task(self, pdf_url: str) -> Optional[str]:
        """提交PDF解析任务"""
        try:
            url = f"{self.base_url}/extract/task"

            data = {
                "url": pdf_url,
                "is_ocr": True,
                "enable_formula": False,
            }

            response = requests.post(url, headers=self.headers, json=data, timeout=30)

            if response.status_code == 200:
                result = response.json()
                logger.debug(f"API Response: {result}")

                # 获取任务编号
                task_id = result.get('data', {}).get('task_id') or result.get('data')
                if not task_id:
                    self.last_error = "MinerU 返回成功但未提供 task_id"
                return task_id
            else:
                logger.error(f"Submit task failed: {response.status_code}, {response.text}")
                self.last_error = self._format_submit_error(response)
                return None

        except Exception as e:
            logger.error(f"Error submitting parse task: {e}", exc_info=True)
            self.last_error = f"提交解析任务异常: {e}"
            return None

    def _poll_parse_result(self, task_id: str, max_attempts: int = 60, interval: int = 5) -> Optional[str]:
        """
        轮询解析结果

        Args:
            task_id: 任务ID
            max_attempts: 最大尝试次数（默认60次，共5分钟）
            interval: 轮询间隔（秒）

        Returns:
            Markdown内容，失败返回None
        """
        try:
            status_url = f"{self.base_url}/extract/task/{task_id}"

            for attempt in range(max_attempts):
                response = requests.get(status_url, headers=self.headers, timeout=30)

                if response.status_code != 200:
                    logger.warning(f"Status check failed: {response.status_code}")
                    time.sleep(interval)
                    continue

                result = response.json()
                data = result.get('data', {})
                state = data.get('state', '')

                # 显示进度
                if state == 'running':
                    progress = data.get('extract_progress', {})
                    extracted = progress.get('extracted_pages', 0)
                    total = progress.get('total_pages', 0)
                    logger.info(f"Parse status: {state} ({extracted}/{total} pages) (attempt {attempt + 1}/{max_attempts})")
                else:
                    logger.info(f"Parse status: {state} (attempt {attempt + 1}/{max_attempts})")

                if state == 'done':
                    # 解析完成，下载压缩包并提取标记文本
                    zip_url = data.get('full_zip_url')
                    if not zip_url:
                        logger.error("No ZIP URL in response")
                        return None

                    logger.info(f"Downloading result from: {zip_url}")
                    markdown_content = self._download_and_extract_zip(zip_url)
                    return markdown_content

                elif state == 'failed':
                    err_msg = data.get('err_msg', 'Unknown error')
                    logger.error(f"Parse failed: {err_msg}")
                    self.last_error = f"MinerU 解析失败: {err_msg}"
                    return None
                elif state in ['pending', 'running', 'converting']:
                    # 继续等待
                    time.sleep(interval)
                else:
                    logger.warning(f"Unknown state: {state}")
                    time.sleep(interval)

            logger.error(f"Parse timeout after {max_attempts * interval} seconds")
            self.last_error = "MinerU 解析超时，请稍后重试"
            return None

        except Exception as e:
            logger.error(f"Error polling parse result: {e}", exc_info=True)
            self.last_error = f"轮询解析结果异常: {e}"
            return None

    def _download_and_extract_zip(self, zip_url: str) -> Optional[str]:
        """下载压缩包并提取 Markdown 内容（60 秒超时，最多重试 3 次）"""
        import io
        import zipfile

        max_attempts = 3
        timeout_seconds = 60
        last_error: Optional[Exception] = None

        for attempt in range(1, max_attempts + 1):
            try:
                logger.info(
                    f"Downloading ZIP file... (attempt {attempt}/{max_attempts}, timeout={timeout_seconds}s)"
                )
                response = requests.get(zip_url, timeout=timeout_seconds)

                if response.status_code != 200:
                    logger.warning(
                        f"Failed to download ZIP: HTTP {response.status_code} (attempt {attempt}/{max_attempts})"
                    )
                    self.last_error = f"下载解析结果失败 (HTTP {response.status_code})"
                    if attempt < max_attempts:
                        time.sleep(2 * attempt)
                        continue
                    return None

                logger.info(f"ZIP file downloaded ({len(response.content)} bytes)")

                # 解压压缩包
                zip_file = zipfile.ZipFile(io.BytesIO(response.content))

                # 查找标记文本文件
                markdown_files = [f for f in zip_file.namelist() if f.endswith('.md')]

                if not markdown_files:
                    logger.error("No markdown file found in ZIP")
                    self.last_error = "解析结果中未找到 Markdown 文件"
                    return None

                # 读取第一个标记文本文件
                md_filename = markdown_files[0]
                logger.info(f"Extracting markdown from: {md_filename}")

                markdown_content = zip_file.read(md_filename).decode('utf-8')
                logger.info(f"Markdown extracted ({len(markdown_content)} characters)")
                return markdown_content

            except Exception as e:
                last_error = e
                logger.warning(
                    f"Download/extract ZIP failed on attempt {attempt}/{max_attempts}: {e}"
                )
                if attempt < max_attempts:
                    time.sleep(2 * attempt)
                    continue

        logger.error(f"Error downloading/extracting ZIP after {max_attempts} attempts: {last_error}")
        self.last_error = f"下载或解压解析结果异常: {last_error}"
        return None

    def get_last_error(self) -> Optional[str]:
        """获取最近一次解析失败原因"""
        return self.last_error

    def _format_submit_error(self, response: requests.Response) -> str:
        """格式化提交任务失败信息，便于前端展示"""
        default_error = f"MinerU 提交任务失败 (HTTP {response.status_code})"

        try:
            error_data = response.json()
        except ValueError:
            return default_error

        msg_code = error_data.get("msgCode")
        msg = error_data.get("msg") or error_data.get("message")

        if response.status_code == 401 and msg_code == "A0202":
            return "MinerU 鉴权失败：MINERU_API_KEY 无效或已过期，请更新后重试"

        if msg_code and msg:
            return f"{default_error}: {msg_code} - {msg}"
        if msg:
            return f"{default_error}: {msg}"
        return default_error


# 全局客户端实例
_mineru_client = None

def get_mineru_client() -> MinerUClient:
    """获取MinerU客户端实例（单例模式）"""
    global _mineru_client
    if _mineru_client is None:
        _mineru_client = MinerUClient()
    return _mineru_client
