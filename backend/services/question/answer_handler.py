"""面试答案处理服务（按会话）。"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import func, select, update
from sqlalchemy.orm import selectinload

from backend.common.config import config
from backend.common.logger import get_logger
from backend.models import QuestionAnswer, Session, SessionLocal
from backend.services.question.follow_up_engine import FollowUpDecisionEngine

logger = get_logger(__name__)


class AnswerHandler:
    """答案处理器。"""

    MAX_TOTAL_FOLLOW_UPS = 3

    def __init__(self):
        self._follow_up_engine: FollowUpDecisionEngine | None = None

    def get_current_question(self, session_id: str) -> Optional[Dict[str, Any]]:
        """获取会话的当前问题（按未回答顺序）。"""
        try:
            qa_record = self._find_unanswered_question(session_id)
            if not qa_record:
                return None

            with SessionLocal() as session:
                total_questions = session.scalar(
                    select(func.count(QuestionAnswer.id)).where(QuestionAnswer.session_id == session_id)
                ) or 0

            return {
                "qa_id": qa_record.id,
                "question": qa_record.question_text,
                "category": qa_record.question_category,
                "question_number": qa_record.question_index + 1,
                "total_questions": int(total_questions),
                "session_id": session_id,
                "question_type": qa_record.question_type,
                "depth": qa_record.depth,
                "parent_qa_id": qa_record.parent_qa_id,
            }
        except Exception as exc:
            logger.error("Error getting current question: %s", exc, exc_info=True)
            return None

    def save_answer(self, qa_id: str, answer_text: str) -> Dict[str, Any]:
        """保存用户回答。"""
        try:
            normalized_answer = str(answer_text or "").strip()
            if not normalized_answer:
                return {"success": False, "error": "回答内容不能为空"}

            seed_question = ""
            seed_category: str | None = None
            seed_depth = 0
            seed_type = "main"
            already_answered = False
            should_run_follow_up_decision = False

            with SessionLocal() as session:
                qa_record = session.get(QuestionAnswer, qa_id)
                if not qa_record:
                    return {"success": False, "error": "问答记录不存在"}
                seed_question = qa_record.question_text
                seed_category = qa_record.question_category
                seed_depth = int(qa_record.depth or 0)
                seed_type = qa_record.question_type or "main"
                already_answered = bool(qa_record.is_answered)
                if not already_answered:
                    should_run_follow_up_decision = self._should_run_follow_up_decision(session, qa_record)

            follow_up_plan: Dict[str, Any] = {
                "answer_score": None,
                "answer_eval_brief": None,
                "should_follow_up": False,
                "follow_up_question": "",
            }
            if not already_answered and should_run_follow_up_decision:
                follow_up_plan = self._build_follow_up_plan(
                    question=seed_question,
                    category=seed_category,
                    depth=seed_depth,
                    question_type=seed_type,
                    answer_text=normalized_answer,
                )
            elif not already_answered:
                follow_up_plan = {
                    "answer_score": self._score_by_length(normalized_answer),
                    "answer_eval_brief": "回答已记录。",
                    "should_follow_up": False,
                    "follow_up_question": "",
                }

            session_id: str | None = None
            remaining_questions = 0
            follow_up_created = False
            follow_up_question = ""
            qa_analysis_ready = True
            answer_score = follow_up_plan.get("answer_score")
            answer_eval_brief = follow_up_plan.get("answer_eval_brief")

            with SessionLocal() as session:
                qa_record = session.get(QuestionAnswer, qa_id)
                if not qa_record:
                    return {"success": False, "error": "问答记录不存在"}

                session_id = qa_record.session_id
                interview_session = session.get(Session, session_id)
                if not interview_session:
                    session.rollback()
                    return {"success": False, "error": "会话不存在"}

                answer_mutated = False
                if qa_record.is_answered:
                    remaining_questions = session.scalar(
                        select(func.count(QuestionAnswer.id)).where(
                            QuestionAnswer.session_id == session_id,
                            QuestionAnswer.is_answered.is_(False),
                        )
                    ) or 0
                    if int(remaining_questions) > 0:
                        return {"success": False, "error": "该问题已回答，请勿重复提交"}
                else:
                    qa_record.answer_text = normalized_answer
                    qa_record.is_answered = True
                    qa_record.answer_score = float(follow_up_plan.get("answer_score") or 0)
                    qa_record.answer_eval_brief = str(follow_up_plan.get("answer_eval_brief") or "").strip() or None
                    answer_mutated = True

                    if self._can_create_follow_up(session, qa_record, follow_up_plan):
                        follow_up_question = str(follow_up_plan.get("follow_up_question") or "").strip()
                        follow_up_created = self._insert_follow_up_question(session, qa_record, follow_up_question)

                    # 确保后续统计读取到本次回答/追问变更
                    session.flush()

                    remaining_questions = session.scalar(
                        select(func.count(QuestionAnswer.id)).where(
                            QuestionAnswer.session_id == session_id,
                            QuestionAnswer.is_answered.is_(False),
                        )
                    ) or 0

                if answer_mutated or int(remaining_questions) > 0:
                    # 最后一题提交后，先持久化业务事实；完成态在分析文件写入成功后再设置
                    interview_session.status = "interviewing"
                    session.commit()

            is_session_completed = int(remaining_questions) == 0
            if session_id and is_session_completed:
                qa_analysis_ready = self._save_completed_qa_json(session_id)
                target_status = "completed" if qa_analysis_ready else "interviewing"
                status_updated = self._set_session_status(session_id, target_status)
                if not status_updated:
                    return {"success": False, "error": "更新会话状态失败，请重试"}
                if not qa_analysis_ready:
                    logger.error(
                        "Failed to write QA analysis object after DB commit, session=%s",
                        session_id,
                    )
                    return {"success": False, "error": "问答分析写入失败，请重试"}

            return {
                "success": True,
                "is_session_completed": is_session_completed,
                "remaining_questions": int(remaining_questions),
                "session_id": session_id,
                "qa_analysis_ready": qa_analysis_ready,
                "follow_up_created": follow_up_created,
                "follow_up_question": follow_up_question if follow_up_created else None,
                "answer_score": answer_score,
                "answer_eval_brief": answer_eval_brief,
            }
        except Exception as exc:
            logger.error("Error saving answer: %s", exc, exc_info=True)
            return {"success": False, "error": str(exc)}

    def _build_follow_up_plan(
        self,
        question: str,
        category: str | None,
        depth: int,
        question_type: str,
        answer_text: str,
    ) -> Dict[str, Any]:
        """生成追问决策计划。"""
        if depth != 0 or question_type != "main":
            return {
                "answer_score": self._score_by_length(answer_text),
                "answer_eval_brief": "回答已记录。",
                "should_follow_up": False,
                "follow_up_question": "",
            }

        try:
            engine = self._get_follow_up_engine()
            return engine.decide(question=question, answer=answer_text, category=category)
        except Exception as exc:
            logger.warning("Follow-up engine unavailable, using fallback strategy: %s", exc)
            score = self._score_by_length(answer_text)
            return {
                "answer_score": score,
                "answer_eval_brief": "回答已记录，系统将继续下一题。",
                "should_follow_up": False,
                "follow_up_question": "",
            }

    def _score_by_length(self, answer_text: str) -> float:
        """基于回答长度的简化评分兜底。"""
        length = len(str(answer_text or ""))
        if length < 40:
            return 4.8
        if length < 80:
            return 6.0
        if length < 140:
            return 6.9
        return 7.6

    def _get_follow_up_engine(self) -> FollowUpDecisionEngine:
        if self._follow_up_engine is None:
            self._follow_up_engine = FollowUpDecisionEngine()
        return self._follow_up_engine

    def _should_run_follow_up_decision(self, session, qa_record: QuestionAnswer) -> bool:
        """检查是否还有追问额度，避免无效的大模型调用。"""
        if int(qa_record.depth or 0) != 0:
            return False
        if (qa_record.question_type or "main") != "main":
            return False

        child_count = session.scalar(
            select(func.count(QuestionAnswer.id)).where(QuestionAnswer.parent_qa_id == qa_record.id)
        ) or 0
        if int(child_count) > 0:
            return False

        total_follow_up_count = session.scalar(
            select(func.count(QuestionAnswer.id)).where(
                QuestionAnswer.session_id == qa_record.session_id,
                QuestionAnswer.question_type == "follow_up",
            )
        ) or 0
        return int(total_follow_up_count) < self.MAX_TOTAL_FOLLOW_UPS

    def _can_create_follow_up(
        self,
        session,
        qa_record: QuestionAnswer,
        follow_up_plan: Dict[str, Any],
    ) -> bool:
        if not self._should_run_follow_up_decision(session, qa_record):
            return False
        if not bool(follow_up_plan.get("should_follow_up")):
            return False

        follow_up_question = str(follow_up_plan.get("follow_up_question") or "").strip()
        if not follow_up_question:
            return False
        return True

    def _insert_follow_up_question(
        self,
        session,
        parent_qa: QuestionAnswer,
        follow_up_question: str,
    ) -> bool:
        normalized_question = str(follow_up_question or "").strip()
        if not normalized_question:
            return False

        if not normalized_question.endswith(("?", "？")):
            normalized_question = f"{normalized_question.rstrip('。.!！')}？"

        session.execute(
            update(QuestionAnswer)
            .where(
                QuestionAnswer.session_id == parent_qa.session_id,
                QuestionAnswer.question_index > parent_qa.question_index,
            )
            .values(question_index=QuestionAnswer.question_index + 1)
        )

        session.add(
            QuestionAnswer(
                id=str(uuid.uuid4()),
                session_id=parent_qa.session_id,
                parent_qa_id=parent_qa.id,
                question_index=parent_qa.question_index + 1,
                depth=1,
                question_type="follow_up",
                question_text=normalized_question,
                answer_text=None,
                answer_score=None,
                answer_eval_brief=None,
                question_category=parent_qa.question_category,
                is_answered=False,
            )
        )
        return True

    def _find_unanswered_question(self, session_id: str) -> Optional[QuestionAnswer]:
        """查找未回答的问题。"""
        with SessionLocal() as session:
            stmt = (
                select(QuestionAnswer)
                .where(
                    QuestionAnswer.session_id == session_id,
                    QuestionAnswer.is_answered.is_(False),
                )
                .order_by(QuestionAnswer.question_index)
                .limit(1)
            )
            return session.execute(stmt).scalar_one_or_none()

    def _save_completed_qa_json(self, session_id: str) -> bool:
        """生成完整 QA JSON 文件供分析。"""
        try:
            with SessionLocal() as session:
                session_obj = session.execute(
                    select(Session)
                    .where(Session.id == session_id)
                    .options(selectinload(Session.room))
                ).scalar_one_or_none()
                if not session_obj:
                    logger.warning("Session not found when saving QA JSON: %s", session_id)
                    return False

                qa_records = (
                    session.execute(
                        select(QuestionAnswer)
                        .where(QuestionAnswer.session_id == session_id)
                        .order_by(QuestionAnswer.question_index)
                    )
                    .scalars()
                    .all()
                )

            room_id = session_obj.room.id

            qa_data = {
                "session_info": {
                    "session_id": session_id,
                    "session_name": session_obj.name,
                    "room_id": room_id,
                    "total_questions": len(qa_records),
                    "completed_at": datetime.now().isoformat(),
                },
                "qa_pairs": [],
                "qa_chains": self._build_qa_chains(qa_records),
                "analysis_ready": True,
                "metadata": {
                    "generated_for": "llm_analysis",
                    "version": "3.0",
                    "file_type": "qa_complete",
                },
            }

            for qa in qa_records:
                qa_data["qa_pairs"].append(
                    {
                        "question_index": qa.question_index,
                        "category": qa.question_category,
                        "question_type": qa.question_type,
                        "depth": qa.depth,
                        "parent_qa_id": qa.parent_qa_id,
                        "question": qa.question_text,
                        "answer": qa.answer_text,
                        "answer_score": qa.answer_score,
                        "answer_eval_brief": qa.answer_eval_brief,
                        "answered_at": qa.updated_at.isoformat() if qa.updated_at else None,
                        "answer_length": len(qa.answer_text) if qa.answer_text else 0,
                        "qa_id": qa.id,
                    }
                )

            from backend.clients.minio_client import upload_qa_analysis

            success = upload_qa_analysis(qa_data, room_id, session_id)
            if success:
                logger.info(
                    "Complete QA data saved for LLM analysis: room=%s, session=%s",
                    room_id,
                    session_id,
                )
                if config.RAG_ENABLED:
                    try:
                        self._push_to_rag_memory(room_id, session_id, session_obj, qa_data)
                    except Exception as exc:
                        logger.error("Failed to push QA data to RAG memory: %s", exc, exc_info=True)
                return True
            else:
                logger.warning("Failed to save QA analysis data")
                return False
        except Exception as exc:
            logger.error("Error saving completed QA JSON: %s", exc, exc_info=True)
            return False

    def _set_session_status(self, session_id: str, status: str) -> bool:
        """更新会话状态。"""
        try:
            with SessionLocal() as session:
                session_obj = session.get(Session, session_id)
                if not session_obj:
                    return False
                session_obj.status = status
                session.commit()
            return True
        except Exception as exc:
            logger.error(
                "Failed to set session status %s for %s: %s",
                status,
                session_id,
                exc,
                exc_info=True,
            )
            return False

    def _build_qa_chains(self, qa_records: list[QuestionAnswer]) -> list[Dict[str, Any]]:
        """按主问题聚合追问链路。"""
        child_map: dict[str, list[QuestionAnswer]] = {}
        main_questions: list[QuestionAnswer] = []

        for qa in qa_records:
            if qa.parent_qa_id:
                child_map.setdefault(qa.parent_qa_id, []).append(qa)
            else:
                main_questions.append(qa)

        chains: list[Dict[str, Any]] = []
        for main in sorted(main_questions, key=lambda item: item.question_index):
            follow_ups = sorted(child_map.get(main.id, []), key=lambda item: item.question_index)
            chains.append(
                {
                    "main": {
                        "qa_id": main.id,
                        "question_index": main.question_index,
                        "category": main.question_category,
                        "question": main.question_text,
                        "answer": main.answer_text,
                        "answer_score": main.answer_score,
                    },
                    "follow_ups": [
                        {
                            "qa_id": follow_up.id,
                            "question_index": follow_up.question_index,
                            "question": follow_up.question_text,
                            "answer": follow_up.answer_text,
                            "answer_score": follow_up.answer_score,
                        }
                        for follow_up in follow_ups
                    ],
                }
            )
        return chains

    def _push_to_rag_memory(
        self,
        room_id: str,
        session_id: str,
        session_obj: Session,
        qa_data: Dict[str, Any],
    ) -> None:
        """推送问答数据到 RAG 记忆体。"""
        from backend.clients.rag_client import get_rag_client

        memory_id = session_obj.room.memory_id
        minio_url = f"rooms/{room_id}/sessions/{session_id}/analysis/qa_complete.json"
        description = json.dumps(qa_data, ensure_ascii=False)

        rag_client = get_rag_client()
        rag_client.push_message(
            memory_id=memory_id,
            url=minio_url,
            description=description,
            app="interviewer",
        )
        logger.info("Successfully pushed QA data to RAG memory %s: %s", memory_id, minio_url)
