"""
简历管理 Service 层
负责简历的业务逻辑处理
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select

from backend.common.logger import get_logger
from backend.models import Resume, Room, SessionLocal, db_session

logger = get_logger(__name__)


class ResumeService:
    """简历管理服务"""

    PARSE_STATUS_DISPLAY = {
        "pending": "待解析",
        "parsing": "解析中",
        "parsed": "解析成功",
        "failed": "解析失败",
    }

    @staticmethod
    def check_name_exists(owner_address: str, name: str, exclude_resume_id: Optional[str] = None) -> bool:
        """检查简历名称是否已存在。"""
        with SessionLocal() as session:
            stmt = select(Resume.id).where(
                Resume.owner_address == owner_address,
                Resume.name == name,
                Resume.status == "active",
            )
            if exclude_resume_id:
                stmt = stmt.where(Resume.id != exclude_resume_id)
            return session.execute(stmt.limit(1)).first() is not None

    @staticmethod
    def create_resume(
        owner_address: str,
        name: str,
        file_name: Optional[str] = None,
        file_size: Optional[int] = None,
        company: Optional[str] = None,
        position: Optional[str] = None,
    ) -> Resume:
        """创建新简历。"""
        if ResumeService.check_name_exists(owner_address, name):
            raise ValueError(f"简历名称 '{name}' 已存在，请使用其他名称")

        resume = Resume(
            id=str(uuid.uuid4()),
            name=name,
            owner_address=owner_address,
            file_name=file_name,
            file_size=file_size,
            company=company,
            position=position,
            status="active",
            parse_status="pending",
            parse_error=None,
        )

        with db_session() as session:
            session.add(resume)

        logger.info("Created resume: %s for user: %s", resume.id, owner_address)
        return resume

    @staticmethod
    def get_resume(resume_id: str) -> Optional[Resume]:
        """获取简历。"""
        with SessionLocal() as session:
            return session.get(Resume, resume_id)

    @staticmethod
    def get_resumes_by_owner(owner_address: str) -> List[Resume]:
        """获取用户的所有简历。"""
        with SessionLocal() as session:
            stmt = (
                select(Resume)
                .where(Resume.owner_address == owner_address, Resume.status == "active")
                .order_by(Resume.created_at.desc())
            )
            return list(session.execute(stmt).scalars().all())

    @staticmethod
    def update_resume(
        resume_id: str,
        name: Optional[str] = None,
        company: Optional[str] = None,
        position: Optional[str] = None,
    ) -> bool:
        """更新简历信息。"""
        with db_session() as session:
            resume = session.get(Resume, resume_id)
            if not resume:
                logger.warning("Resume not found: %s", resume_id)
                return False

            if name is not None and name != resume.name:
                stmt = select(Resume.id).where(
                    Resume.owner_address == resume.owner_address,
                    Resume.name == name,
                    Resume.status == "active",
                    Resume.id != resume_id,
                )
                if session.execute(stmt.limit(1)).first() is not None:
                    raise ValueError(f"简历名称 '{name}' 已存在，请使用其他名称")
                resume.name = name

            if company is not None:
                resume.company = company
            if position is not None:
                resume.position = position

        logger.info("Updated resume: %s", resume_id)
        return True

    @staticmethod
    def delete_resume(resume_id: str) -> bool:
        """软删除简历（标记为 deleted）。"""
        with db_session() as session:
            resume = session.get(Resume, resume_id)
            if not resume:
                logger.warning("Resume not found: %s", resume_id)
                return False
            resume.status = "deleted"

        logger.info("Deleted resume: %s", resume_id)
        return True

    @staticmethod
    def update_parse_status(resume_id: str, parse_status: str, parse_error: Optional[str] = None) -> bool:
        """更新简历解析状态。"""
        with db_session() as session:
            resume = session.get(Resume, resume_id)
            if not resume:
                logger.warning("Resume not found when updating parse status: %s", resume_id)
                return False

            resume.parse_status = parse_status
            resume.parse_error = parse_error

        logger.info(
            "Updated resume parse status: %s -> %s%s",
            resume_id,
            parse_status,
            f" ({parse_error})" if parse_error else "",
        )
        return True

    @staticmethod
    def get_parse_status_display(parse_status: Optional[str]) -> str:
        """获取解析状态展示文本。"""
        if not parse_status:
            return "未知状态"
        return ResumeService.PARSE_STATUS_DISPLAY.get(parse_status, parse_status)

    @staticmethod
    def get_resume_stats(owner_address: str) -> Dict[str, int]:
        """获取用户简历统计信息。"""
        with SessionLocal() as session:
            total_resumes = session.scalar(
                select(func.count(Resume.id)).where(
                    Resume.owner_address == owner_address,
                    Resume.status == "active",
                )
            ) or 0

            parsed_resumes = session.scalar(
                select(func.count(Resume.id)).where(
                    Resume.owner_address == owner_address,
                    Resume.status == "active",
                    Resume.parse_status == "parsed",
                )
            ) or 0

            linked_rooms = session.scalar(
                select(func.count(Room.id)).where(
                    Room.owner_address == owner_address,
                    Room.resume_id.is_not(None),
                )
            ) or 0

        return {
            "total_resumes": int(total_resumes),
            "parsed_resumes": int(parsed_resumes),
            "linked_rooms": int(linked_rooms),
        }

    @staticmethod
    def to_dict(resume: Resume) -> Dict[str, Any]:
        """将 Resume 对象转换为字典。"""
        with SessionLocal() as session:
            linked_rooms = (
                session.execute(select(Room).where(Room.resume_id == resume.id).order_by(Room.created_at.desc()))
                .scalars()
                .all()
            )

        linked_rooms_list = [{"id": room.id, "name": room.name} for room in linked_rooms]
        file_name = (resume.file_name or "").strip()
        fallback_names = {"-.pdf", "-_.pdf", ".pdf", "-"}
        if not file_name or file_name.lower() in fallback_names:
            fallback_name = resume.name or "resume"
            file_name = fallback_name if fallback_name.lower().endswith(".pdf") else f"{fallback_name}.pdf"

        return {
            "id": resume.id,
            "name": resume.name,
            "owner_address": resume.owner_address,
            "file_name": file_name,
            "file_size": resume.file_size,
            "company": resume.company,
            "position": resume.position,
            "status": resume.status,
            "parse_status": resume.parse_status,
            "parse_status_display": ResumeService.get_parse_status_display(resume.parse_status),
            "parse_error": resume.parse_error,
            "linked_rooms_count": len(linked_rooms_list),
            "linked_rooms": linked_rooms_list,
            "created_at": resume.created_at.isoformat() if resume.created_at else None,
            "updated_at": resume.updated_at.isoformat() if resume.updated_at else None,
        }

