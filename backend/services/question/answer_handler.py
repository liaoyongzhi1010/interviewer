"""
面试答案处理服务
负责管理问题回答、获取当前问题等
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import func, select

from backend.common.logger import get_logger
from backend.models import QuestionAnswer, Round, SessionLocal, db_session
from backend.services.interview_service import RoundService

logger = get_logger(__name__)


class AnswerHandler:
    """答案处理器"""

    def get_current_question(self, round_id: str) -> Optional[Dict[str, Any]]:
        """获取当前轮次的当前问题。"""
        try:
            round_obj = RoundService.get_round(round_id)
            if not round_obj:
                return None

            current_index = round_obj.current_question_index
            qa_record = self._find_unanswered_question(round_id, current_index)
            if not qa_record:
                return None

            with SessionLocal() as session:
                total_questions = session.scalar(
                    select(func.count(QuestionAnswer.id)).where(QuestionAnswer.round_id == round_id)
                ) or 0

            return {
                "qa_id": qa_record.id,
                "question": qa_record.question_text,
                "category": qa_record.question_category,
                "question_number": qa_record.question_index + 1,
                "total_questions": int(total_questions),
                "round_id": round_id,
            }
        except Exception as exc:
            logger.error("Error getting current question: %s", exc, exc_info=True)
            return None

    def save_answer(self, qa_id: str, answer_text: str) -> Dict[str, Any]:
        """保存用户回答。"""
        try:
            with db_session() as session:
                qa_record = session.get(QuestionAnswer, qa_id)
                if not qa_record:
                    return {"success": False, "error": "问答记录不存在"}

                qa_record.answer_text = answer_text
                qa_record.is_answered = True

                round_obj = session.get(Round, qa_record.round_id)
                if not round_obj:
                    return {"success": False, "error": "轮次不存在"}

                round_obj.current_question_index = qa_record.question_index + 1

                remaining_questions = session.scalar(
                    select(func.count(QuestionAnswer.id)).where(
                        QuestionAnswer.round_id == round_obj.id,
                        QuestionAnswer.is_answered.is_(False),
                    )
                ) or 0

                if int(remaining_questions) == 0:
                    round_obj.status = "completed"

            if int(remaining_questions) == 0:
                latest_round = RoundService.get_round(round_obj.id)
                if latest_round:
                    self._save_completed_qa_json(latest_round)

            return {
                "success": True,
                "is_round_completed": int(remaining_questions) == 0,
                "remaining_questions": int(remaining_questions),
            }
        except Exception as exc:
            logger.error("Error saving answer: %s", exc, exc_info=True)
            return {"success": False, "error": str(exc)}

    def _find_unanswered_question(self, round_id: str, current_index: int) -> Optional[QuestionAnswer]:
        """查找未回答的问题。"""
        with SessionLocal() as session:
            stmt = (
                select(QuestionAnswer)
                .where(
                    QuestionAnswer.round_id == round_id,
                    QuestionAnswer.question_index == current_index,
                    QuestionAnswer.is_answered.is_(False),
                )
                .limit(1)
            )
            qa_record = session.execute(stmt).scalar_one_or_none()
            if qa_record:
                return qa_record

            fallback_stmt = (
                select(QuestionAnswer)
                .where(
                    QuestionAnswer.round_id == round_id,
                    QuestionAnswer.is_answered.is_(False),
                )
                .order_by(QuestionAnswer.question_index)
                .limit(1)
            )
            return session.execute(fallback_stmt).scalar_one_or_none()

    def _save_completed_qa_json(self, round_obj: Round) -> None:
        """生成完整的 QA 记录 JSON 文件供大模型分析。"""
        try:
            with SessionLocal() as session:
                qa_records = (
                    session.execute(
                        select(QuestionAnswer)
                        .where(QuestionAnswer.round_id == round_obj.id)
                        .order_by(QuestionAnswer.question_index)
                    )
                    .scalars()
                    .all()
                )

            session_obj = round_obj.session
            room_obj = session_obj.room
            room_id = room_obj.id
            session_id = session_obj.id

            qa_data = {
                "round_info": {
                    "round_id": round_obj.id,
                    "session_id": session_id,
                    "room_id": room_id,
                    "round_index": round_obj.round_index,
                    "total_questions": len(qa_records),
                    "completed_at": datetime.now().isoformat(),
                    "round_type": round_obj.round_type,
                },
                "session_info": {
                    "session_name": session_obj.name,
                    "room_id": room_id,
                },
                "qa_pairs": [],
                "analysis_ready": True,
                "metadata": {
                    "generated_for": "llm_analysis",
                    "version": "1.0",
                    "file_type": "qa_complete",
                },
            }

            for qa in qa_records:
                qa_data["qa_pairs"].append(
                    {
                        "question_index": qa.question_index,
                        "category": qa.question_category,
                        "question": qa.question_text,
                        "answer": qa.answer_text,
                        "answered_at": qa.updated_at.isoformat() if qa.updated_at else None,
                        "answer_length": len(qa.answer_text) if qa.answer_text else 0,
                        "qa_id": qa.id,
                    }
                )

            from backend.clients.minio_client import upload_qa_analysis

            success = upload_qa_analysis(qa_data, room_id, session_id, round_obj.round_index)
            if success:
                logger.info(
                    "Complete QA data saved for LLM analysis: room=%s, session=%s, round=%s",
                    room_id,
                    session_id,
                    round_obj.round_index,
                )
                try:
                    self._push_to_rag_memory(room_id, session_id, round_obj, qa_data)
                except Exception as exc:
                    logger.error("Failed to push QA data to RAG memory: %s", exc, exc_info=True)
            else:
                logger.warning("Failed to save QA analysis data")
        except Exception as exc:
            logger.error("Error saving completed QA JSON: %s", exc, exc_info=True)

    def _push_to_rag_memory(
        self,
        room_id: str,
        session_id: str,
        round_obj: Round,
        qa_data: Dict[str, Any],
    ) -> None:
        """推送问答数据到 RAG 记忆体。"""
        from backend.clients.rag_client import get_rag_client

        room = round_obj.session.room
        memory_id = room.memory_id
        minio_url = f"rooms/{room_id}/sessions/{session_id}/analysis/qa_complete_{round_obj.round_index}.json"
        description = json.dumps(qa_data, ensure_ascii=False)

        rag_client = get_rag_client()
        rag_client.push_message(
            memory_id=memory_id,
            url=minio_url,
            description=description,
            app="interviewer",
        )

        logger.info("Successfully pushed QA data to RAG memory %s: %s", memory_id, minio_url)

