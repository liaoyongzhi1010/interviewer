"""面试间与会话服务（无轮次版本）。"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from backend.common.config import config
from backend.common.logger import get_logger
from backend.models import QuestionAnswer, Room, Session, SessionLocal, db_session

logger = get_logger(__name__)


class RoomService:
    """面试间管理服务。"""

    @staticmethod
    def create_room(
        name: Optional[str] = None,
        owner_address: Optional[str] = None,
        resume_id: Optional[str] = None,
    ) -> Room:
        """创建新的面试间。"""
        from backend.services.resume_service import ResumeService

        room_id = str(uuid.uuid4())
        today = datetime.now().strftime("%Y-%m-%d")

        if not name:
            if resume_id:
                resume = ResumeService.get_resume(resume_id)
                room_name = f"{resume.name}-{today}" if resume else f"面试间-{today}"
            else:
                room_name = f"面试间-{today}"
        else:
            room_name = name

        memory_id = f"memory_{room_id[:8]}"
        if config.RAG_ENABLED:
            try:
                from backend.clients.rag_client import get_rag_client

                rag_client = get_rag_client()
                memory_id = rag_client.create_memory(app="interviewer")
                logger.info("Created RAG memory for room %s: %s", room_id, memory_id)
            except Exception as exc:
                logger.warning(
                    "Failed to create RAG memory for room %s, fallback to local memory id %s: %s",
                    room_id,
                    memory_id,
                    exc,
                )
        else:
            logger.info("RAG disabled, using local memory id for room %s: %s", room_id, memory_id)

        room = Room(
            id=room_id,
            memory_id=memory_id,
            name=room_name,
            owner_address=owner_address,
            resume_id=resume_id,
        )
        with db_session() as session:
            session.add(room)

        logger.info("Created room %s for owner %s with resume %s", room_id, owner_address, resume_id)
        return room

    @staticmethod
    def get_room(room_id: str) -> Optional[Room]:
        """获取面试间。"""
        with SessionLocal() as session:
            stmt = select(Room).where(Room.id == room_id)
            return session.execute(stmt).scalar_one_or_none()

    @staticmethod
    def get_rooms_by_owner(owner_address: str) -> List[Room]:
        """获取指定用户的所有面试间。"""
        with SessionLocal() as session:
            stmt = (
                select(Room)
                .where(Room.owner_address == owner_address)
                .order_by(Room.created_at.desc())
            )
            return list(session.execute(stmt).scalars().all())

    @staticmethod
    def delete_room(room_id: str) -> bool:
        """删除面试间及其全部会话数据。"""
        session_ids: list[str] = []
        with SessionLocal() as session:
            room = session.get(Room, room_id)
            if not room:
                return False
            session_ids = list(session.execute(select(Session.id).where(Session.room_id == room_id)).scalars().all())

        for session_id in session_ids:
            SessionService.delete_session(session_id)

        with db_session() as session:
            room = session.get(Room, room_id)
            if not room:
                return True
            session.delete(room)
        return True

    @staticmethod
    def update_room(room_id: str, name: Optional[str] = None) -> bool:
        """更新面试间信息。"""
        with db_session() as session:
            room = session.get(Room, room_id)
            if not room:
                logger.warning("Room not found: %s", room_id)
                return False
            if name is not None:
                room.name = name
        logger.info("Updated room: %s", room_id)
        return True

    @staticmethod
    def update_room_resume(room_id: str, resume_id: Optional[str] = None) -> bool:
        """更新面试间关联简历。"""
        with db_session() as session:
            room = session.get(Room, room_id)
            if not room:
                logger.warning("Room not found: %s", room_id)
                return False
            room.resume_id = resume_id
        logger.info("Updated room resume: %s -> resume: %s", room_id, resume_id)
        return True

    @staticmethod
    def _get_room_display_name(room: Room) -> str:
        """获取用于前端展示的面试间名称，避免泄露内部标识。"""
        raw_name = (room.name or "").strip()
        is_internal_name = (not raw_name) or (raw_name == room.memory_id) or raw_name.startswith("memory_")
        if not is_internal_name:
            return raw_name

        date_text = room.created_at.strftime("%Y-%m-%d") if room.created_at else datetime.now().strftime("%Y-%m-%d")
        if room.resume_id:
            try:
                from backend.services.resume_service import ResumeService

                resume = ResumeService.get_resume(room.resume_id)
                resume_name = (resume.name or "").strip() if resume else ""
                if resume_name:
                    return f"{resume_name}-{date_text}"
            except Exception as exc:
                logger.warning("Failed to build display name with resume for room %s: %s", room.id, exc)
        return f"面试间-{date_text}"

    @staticmethod
    def _split_display_name(name: str) -> tuple[str, Optional[str]]:
        """将 `名称-YYYY-MM-DD` 拆成主标题和日期。"""
        raw_name = (name or "").strip()
        if not raw_name:
            return "面试间", None

        match = re.match(r"^(.*)-(\d{4}-\d{2}-\d{2})$", raw_name)
        if not match:
            return raw_name, None

        main_name = (match.group(1) or "").strip() or "面试间"
        date_text = match.group(2)
        try:
            datetime.strptime(date_text, "%Y-%m-%d")
        except ValueError:
            return raw_name, None
        return main_name, date_text

    @staticmethod
    def to_dict(room: Room) -> Dict[str, Any]:
        """将 Room 对象转换为字典。"""
        with SessionLocal() as session:
            sessions_count = session.scalar(select(func.count(Session.id)).where(Session.room_id == room.id)) or 0
            completed_sessions = (
                session.scalar(
                    select(func.count(Session.id)).where(
                        Session.room_id == room.id,
                        Session.status == "completed",
                    )
                )
                or 0
            )
            questions_count = (
                session.scalar(
                    select(func.count(QuestionAnswer.id))
                    .join(Session, QuestionAnswer.session_id == Session.id)
                    .where(Session.room_id == room.id)
                )
                or 0
            )

        display_name = RoomService._get_room_display_name(room)
        display_main, display_date = RoomService._split_display_name(display_name)

        return {
            "id": room.id,
            "name": display_name,
            "display_name": display_name,
            "display_main": display_main,
            "display_date": display_date,
            "owner_address": room.owner_address,
            "created_at": room.created_at.isoformat() if room.created_at else None,
            "updated_at": room.updated_at.isoformat() if room.updated_at else None,
            "sessions_count": int(sessions_count),
            "completed_sessions_count": int(completed_sessions),
            "questions_count": int(questions_count),
        }


class SessionService:
    """会话管理服务。"""

    @staticmethod
    def create_session(room_id: str, name: Optional[str] = None) -> Optional[Session]:
        """在指定面试间创建新的面试会话。"""
        with db_session() as session:
            room = session.get(Room, room_id)
            if not room:
                return None

            session_count = session.scalar(select(func.count(Session.id)).where(Session.room_id == room_id)) or 0

            interview_session = Session(
                id=str(uuid.uuid4()),
                name=name or f"面试会话{int(session_count) + 1}",
                room_id=room_id,
                status="initialized",
            )
            session.add(interview_session)

        return interview_session

    @staticmethod
    def get_session(session_id: str) -> Optional[Session]:
        """获取面试会话。"""
        with SessionLocal() as session:
            stmt = select(Session).where(Session.id == session_id).options(selectinload(Session.room))
            return session.execute(stmt).scalar_one_or_none()

    @staticmethod
    def get_sessions_by_room(room_id: str) -> List[Session]:
        """获取指定房间的所有会话。"""
        with SessionLocal() as session:
            stmt = (
                select(Session)
                .where(Session.room_id == room_id)
                .options(selectinload(Session.room))
                .order_by(Session.created_at.desc())
            )
            return list(session.execute(stmt).scalars().all())

    @staticmethod
    def delete_session(session_id: str) -> bool:
        """删除会话及其相关数据。"""
        with SessionLocal() as session:
            interview_session = session.get(Session, session_id)
            if not interview_session:
                return False

        try:
            from backend.clients.minio_client import minio_client

            minio_client.delete_session_files(session_id)
        except Exception as exc:
            logger.warning("Failed to delete MinIO files for session %s: %s", session_id, exc)

        with db_session() as session:
            interview_session = session.get(Session, session_id)
            if interview_session:
                session.delete(interview_session)
        return True

    @staticmethod
    def get_status_display(session: Session) -> str:
        """获取会话状态的显示文本。"""
        status_map = {
            "initialized": "未开始",
            "generating": "正在生成题目",
            "interviewing": "面试进行中",
            "analyzing": "正在生成报告",
            "completed": "已完成",
        }
        return status_map.get(session.status, "未知状态")

    @staticmethod
    def _get_question_stats(session_id: str) -> tuple[int, int]:
        with SessionLocal() as session:
            total_questions = (
                session.scalar(select(func.count(QuestionAnswer.id)).where(QuestionAnswer.session_id == session_id)) or 0
            )
            answered_questions = (
                session.scalar(
                    select(func.count(QuestionAnswer.id)).where(
                        QuestionAnswer.session_id == session_id,
                        QuestionAnswer.is_answered.is_(True),
                    )
                )
                or 0
            )
        return int(total_questions), int(answered_questions)

    @staticmethod
    def to_dict(session: Session) -> Dict[str, Any]:
        """将 Session 对象转换为字典。"""
        room_id = session.room.id if session.room else session.room_id
        total_questions, answered_questions = SessionService._get_question_stats(session.id)

        return {
            "id": session.id,
            "name": session.name,
            "room_id": room_id,
            "status": session.status,
            "status_display": SessionService.get_status_display(session),
            "created_at": session.created_at.isoformat() if session.created_at else None,
            "updated_at": session.updated_at.isoformat() if session.updated_at else None,
            "questions_count": total_questions,
            "answered_count": answered_questions,
            "is_completed": session.status == "completed",
        }
