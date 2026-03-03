"""
面试管理服务
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from backend.common.logger import get_logger
from backend.models import QuestionAnswer, Room, Round, RoundCompletion, Session, SessionLocal, db_session

logger = get_logger(__name__)


class RoomService:
    """房间管理服务"""

    @staticmethod
    def create_room(
        name: Optional[str] = None,
        owner_address: Optional[str] = None,
        resume_id: Optional[str] = None,
    ) -> Room:
        """创建新的面试间。"""
        from backend.clients.rag_client import get_rag_client
        from backend.services.resume_service import ResumeService

        room_id = str(uuid.uuid4())

        if not name:
            if resume_id:
                resume = ResumeService.get_resume(resume_id)
                room_name = f"面试间 {resume.name}" if resume else "面试间"
            else:
                room_name = "面试间"
        else:
            room_name = name

        try:
            rag_client = get_rag_client()
            memory_id = rag_client.create_memory(app="interviewer")
            logger.info("Created RAG memory for room %s: %s", room_id, memory_id)
        except Exception as exc:
            logger.error("Failed to create RAG memory: %s", exc)
            memory_id = f"memory_{room_id[:8]}"

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
    def get_all_rooms() -> List[Room]:
        """获取所有面试间。"""
        with SessionLocal() as session:
            stmt = select(Room).order_by(Room.created_at.desc())
            return list(session.execute(stmt).scalars().all())

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
        """删除面试间。"""
        session_ids: list[str] = []
        with SessionLocal() as session:
            room = session.get(Room, room_id)
            if not room:
                return False
            session_ids = list(
                session.execute(select(Session.id).where(Session.room_id == room_id)).scalars().all()
            )

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
    def to_dict(room: Room) -> Dict[str, Any]:
        """将 Room 对象转换为字典。"""
        sessions = SessionService.get_sessions_by_room(room.id)
        total_rounds = 0
        for session in sessions:
            rounds = RoundService.get_rounds_by_session(session.id)
            total_rounds += len(rounds)

        return {
            "id": room.id,
            "memory_id": room.memory_id,
            "name": room.name,
            "owner_address": room.owner_address,
            "created_at": room.created_at.isoformat() if room.created_at else None,
            "updated_at": room.updated_at.isoformat() if room.updated_at else None,
            "sessions_count": len(sessions),
            "rounds_count": total_rounds,
        }


class SessionService:
    """会话管理服务"""

    @staticmethod
    def create_session(room_id: str, name: Optional[str] = None) -> Optional[Session]:
        """在指定面试间创建新的面试会话。"""
        with db_session() as session:
            room = session.get(Room, room_id)
            if not room:
                return None

            session_count = session.scalar(
                select(func.count(Session.id)).where(Session.room_id == room_id)
            ) or 0

            interview_session = Session(
                id=str(uuid.uuid4()),
                name=name or f"面试会话{int(session_count) + 1}",
                room_id=room_id,
            )
            session.add(interview_session)

        return interview_session

    @staticmethod
    def get_session(session_id: str) -> Optional[Session]:
        """获取面试会话。"""
        with SessionLocal() as session:
            stmt = (
                select(Session)
                .where(Session.id == session_id)
                .options(selectinload(Session.room))
            )
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
        round_ids: list[str] = []
        with SessionLocal() as session:
            stmt = (
                select(Session)
                .where(Session.id == session_id)
                .options(selectinload(Session.rounds))
            )
            interview_session = session.execute(stmt).scalar_one_or_none()
            if not interview_session:
                return False
            round_ids = [round_obj.id for round_obj in interview_session.rounds]

        for round_id in round_ids:
            RoundService.delete_round(round_id)

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
    def update_session_status(session_id: str, status: str) -> bool:
        """更新会话状态。"""
        with db_session() as session:
            interview_session = session.get(Session, session_id)
            if not interview_session:
                return False
            interview_session.status = status
        return True

    @staticmethod
    def get_status_display(session: Session) -> str:
        """获取会话状态的显示文本。"""
        status = session.status
        current_round = session.current_round

        if status == "initialized":
            return "初始化"
        if status == "generating":
            return f"第{current_round}轮出题中"
        if status == "interviewing":
            return f"第{current_round}轮面试中"
        if status == "analyzing":
            return f"第{current_round}轮分析中"
        if status == "round_completed":
            return f"第{current_round}轮已完成"
        return "未知状态"

    @staticmethod
    def to_dict(session: Session) -> Dict[str, Any]:
        """将 Session 对象转换为字典。"""
        rounds = RoundService.get_rounds_by_session(session.id)
        total_questions = sum(round_obj.questions_count for round_obj in rounds)

        room_id = session.room.id if session.room else session.room_id
        return {
            "id": session.id,
            "name": session.name,
            "room_id": room_id,
            "status": session.status,
            "current_round": session.current_round,
            "status_display": SessionService.get_status_display(session),
            "created_at": session.created_at.isoformat() if session.created_at else None,
            "updated_at": session.updated_at.isoformat() if session.updated_at else None,
            "rounds_count": len(rounds),
            "questions_count": total_questions,
        }


class RoundService:
    """轮次管理服务"""

    @staticmethod
    def create_round(session_id: str, questions: List[str], round_type: str = "ai_generated") -> Optional[Round]:
        """创建新的对话轮次。"""
        with db_session() as session:
            stmt = (
                select(Session)
                .where(Session.id == session_id)
                .options(selectinload(Session.room))
            )
            interview_session = session.execute(stmt).scalar_one_or_none()
            if not interview_session:
                return None

            round_count = session.scalar(select(func.count(Round.id)).where(Round.session_id == session_id)) or 0
            round_index = int(round_count)

            round_obj = Round(
                id=str(uuid.uuid4()),
                session_id=session_id,
                round_index=round_index,
                questions_count=len(questions),
                questions_file_path=(
                    f"rooms/{interview_session.room.id}/sessions/{session_id}/questions/round_{round_index}.json"
                ),
                round_type=round_type,
                current_question_index=0,
                status="active",
            )
            session.add(round_obj)

        return round_obj

    @staticmethod
    def get_round(round_id: str) -> Optional[Round]:
        """获取轮次。"""
        with SessionLocal() as session:
            stmt = (
                select(Round)
                .where(Round.id == round_id)
                .options(selectinload(Round.session).selectinload(Session.room))
            )
            return session.execute(stmt).scalar_one_or_none()

    @staticmethod
    def get_rounds_by_session(session_id: str) -> List[Round]:
        """获取指定会话的所有轮次。"""
        with SessionLocal() as session:
            stmt = (
                select(Round)
                .where(Round.session_id == session_id)
                .options(selectinload(Round.session))
                .order_by(Round.round_index)
            )
            return list(session.execute(stmt).scalars().all())

    @staticmethod
    def get_round_by_session_and_index(session_id: str, round_index: int) -> Optional[Round]:
        """根据会话和轮次索引获取轮次记录。"""
        with SessionLocal() as session:
            stmt = (
                select(Round)
                .where(Round.session_id == session_id, Round.round_index == round_index)
                .options(selectinload(Round.session).selectinload(Session.room))
            )
            return session.execute(stmt).scalar_one_or_none()

    @staticmethod
    def delete_round(round_id: str) -> bool:
        """删除轮次及其相关数据。"""
        with SessionLocal() as session:
            stmt = (
                select(Round)
                .where(Round.id == round_id)
                .options(selectinload(Round.session).selectinload(Session.room))
            )
            round_obj = session.execute(stmt).scalar_one_or_none()
            if not round_obj:
                return False

        RoundService._delete_round_files(round_obj)

        with db_session() as session:
            round_obj = session.get(Round, round_id)
            if round_obj:
                session.delete(round_obj)
        return True

    @staticmethod
    def _delete_round_files(round_obj: Round) -> None:
        """删除轮次相关的 MinIO 文件。"""
        try:
            from backend.clients.minio_client import minio_client

            room_id = round_obj.session.room.id
            session_id = round_obj.session.id

            questions_file = f"rooms/{room_id}/sessions/{session_id}/questions/round_{round_obj.round_index}.json"
            minio_client.delete_object(questions_file)
            logger.info("Deleted questions file: %s", questions_file)

            analysis_file = f"rooms/{room_id}/sessions/{session_id}/analysis/qa_complete_{round_obj.round_index}.json"
            minio_client.delete_object(analysis_file)
            logger.info("Deleted analysis file: %s", analysis_file)
        except Exception as exc:
            logger.error("Error deleting round files: %s", exc)

    @staticmethod
    def to_dict(round_obj: Round) -> Dict[str, Any]:
        """将 Round 对象转换为字典。"""
        return {
            "id": round_obj.id,
            "session_id": round_obj.session_id,
            "round_index": round_obj.round_index,
            "questions_count": round_obj.questions_count,
            "questions_file_path": round_obj.questions_file_path,
            "round_type": round_obj.round_type,
            "status": round_obj.status,
            "created_at": round_obj.created_at.isoformat() if round_obj.created_at else None,
            "updated_at": round_obj.updated_at.isoformat() if round_obj.updated_at else None,
        }


class RoundCompletionService:
    """轮次完成记录服务"""

    @staticmethod
    def get_by_idempotency(idempotency_key: str) -> Optional[RoundCompletion]:
        if not idempotency_key:
            return None
        with SessionLocal() as session:
            stmt = (
                select(RoundCompletion)
                .where(RoundCompletion.idempotency_key == idempotency_key)
                .options(selectinload(RoundCompletion.session))
            )
            return session.execute(stmt).scalar_one_or_none()

    @staticmethod
    def get_by_session_and_index(session: Optional[Session], round_index: int) -> Optional[RoundCompletion]:
        if not session:
            return None
        with SessionLocal() as db:
            stmt = (
                select(RoundCompletion)
                .where(RoundCompletion.session_id == session.id, RoundCompletion.round_index == round_index)
                .options(selectinload(RoundCompletion.session))
            )
            return db.execute(stmt).scalar_one_or_none()

    @staticmethod
    def record_completion(
        session: Session,
        round_index: int,
        *,
        qa_object: Any,
        occurred_at: datetime,
        idempotency_key: str,
        round_obj: Optional[Round] = None,
    ) -> RoundCompletion:
        payload = (
            json.dumps(qa_object, ensure_ascii=False)
            if isinstance(qa_object, (dict, list))
            else str(qa_object)
        )

        completion = RoundCompletion(
            id=str(uuid.uuid4()),
            session_id=session.id,
            round_index=round_index,
            idempotency_key=idempotency_key,
            payload=payload,
            occurred_at=occurred_at,
        )

        with db_session() as db:
            db.add(completion)
            if round_obj:
                persistent_round = db.get(Round, round_obj.id)
                if persistent_round:
                    persistent_round.status = "completed"
                    if persistent_round.questions_count is not None:
                        persistent_round.current_question_index = max(
                            persistent_round.current_question_index,
                            persistent_round.questions_count,
                        )

        logger.info(
            "Recorded round completion: session=%s, round_index=%s, idempotency_key=%s",
            session.id,
            round_index,
            idempotency_key,
        )
        return completion

