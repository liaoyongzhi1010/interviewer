"""面试题生成服务（按会话单次生成）。"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select

from backend.clients.llm.qwen_client import QwenClient
from backend.common.config import config
from backend.common.logger import get_logger
from backend.models import QuestionAnswer, SessionLocal, db_session

logger = get_logger(__name__)


class QuestionGenerator:
    """面试题生成器。"""

    MAIN_CATEGORY_ORDER = ["基础题", "项目题", "场景题"]
    MAIN_TARGET_PER_CATEGORY = 2

    def __init__(self):
        self.qwen_client = QwenClient()

    def generate_questions(self, session_id: str) -> Optional[Dict[str, Any]]:
        """为指定会话生成面试题（每个会话仅允许一次）。"""
        try:
            from backend.services.interview_service import SessionService
            from backend.services.resume_service import ResumeService

            interview_session = SessionService.get_session(session_id)
            if not interview_session:
                return {"success": False, "error": "会话不存在"}

            if self._has_generated_questions(session_id):
                existing_questions = self._load_existing_questions(session_id)
                return {
                    "success": True,
                    "questions": existing_questions.get("questions", []),
                    "question_count": len(existing_questions.get("questions", [])),
                    "categorized_questions": existing_questions.get("categorized_questions", {}),
                    "already_generated": True,
                }

            room = interview_session.room

            if not room.resume_id:
                return {"success": False, "error": "该面试间还未关联简历，请先关联简历"}

            resume = ResumeService.get_resume(room.resume_id)
            if not resume:
                return {"success": False, "error": "关联简历不存在，请重新选择简历"}
            if resume.parse_status in {"pending", "parsing"}:
                return {"success": False, "error": "简历正在解析中，请稍后再生成面试题"}
            if resume.parse_status == "failed":
                parse_error = resume.parse_error or "未知原因"
                return {"success": False, "error": f"简历解析失败：{parse_error}"}

            from backend.clients.minio_client import download_resume_data

            resume_data = download_resume_data(room.resume_id)
            if not resume_data:
                return {"success": False, "error": "简历解析结果尚未就绪，请稍后重试"}

            target_position = str(resume_data.get("position") or resume.position or "").strip()
            if not target_position:
                return {"success": False, "error": "生成面试题前请先补充目标岗位（可在简历信息中填写职位）"}
            resume_data["position"] = target_position

            categorized_questions: Dict[str, List[str]]
            all_questions: List[str]
            if config.RAG_ENABLED:
                try:
                    rag_result = self._generate_questions_via_rag(
                        memory_id=room.memory_id,
                        resume_id=str(room.resume_id),
                        resume_data=resume_data,
                        jd_id=room.jd_id,
                    )
                    rag_questions = rag_result.get("questions", [])
                    categorized_questions = {"RAG生成": rag_questions}
                    categorized_questions, ordered_questions = self._select_main_questions_plan(
                        categorized_questions,
                        per_category=self.MAIN_TARGET_PER_CATEGORY,
                    )
                    all_questions = self._merge_ordered_questions(ordered_questions)
                    if not all_questions:
                        raise ValueError("RAG 返回空题目")
                    logger.info("Generated %s questions via RAG for session %s", len(all_questions), session_id)
                except Exception as exc:
                    logger.warning("Failed to generate questions via RAG, fallback to Qwen: %s", exc)
                    resume_content = self._format_resume_for_llm(resume_data)
                    request_count_per_category = max(3, self.MAIN_TARGET_PER_CATEGORY)
                    categorized_questions = self.qwen_client.generate_questions(
                        resume_content,
                        question_types={category: request_count_per_category for category in self.MAIN_CATEGORY_ORDER},
                    )
                    categorized_questions, ordered_questions = self._select_main_questions_plan(
                        categorized_questions,
                        per_category=self.MAIN_TARGET_PER_CATEGORY,
                    )
                    all_questions = self._merge_ordered_questions(ordered_questions)
            else:
                resume_content = self._format_resume_for_llm(resume_data)
                request_count_per_category = max(3, self.MAIN_TARGET_PER_CATEGORY)
                categorized_questions = self.qwen_client.generate_questions(
                    resume_content,
                    question_types={category: request_count_per_category for category in self.MAIN_CATEGORY_ORDER},
                )
                categorized_questions, ordered_questions = self._select_main_questions_plan(
                    categorized_questions,
                    per_category=self.MAIN_TARGET_PER_CATEGORY,
                )
                all_questions = self._merge_ordered_questions(ordered_questions)

            if not all_questions:
                raise ValueError("未能生成面试题")

            self._create_question_answer_records(session_id, ordered_questions)

            return {
                "success": True,
                "questions": all_questions,
                "question_count": len(all_questions),
                "categorized_questions": categorized_questions,
                "already_generated": False,
            }

        except Exception as exc:
            logger.error("Error generating questions: %s", exc, exc_info=True)
            return {"success": False, "error": str(exc)}

    def _has_generated_questions(self, session_id: str) -> bool:
        with SessionLocal() as session:
            count = session.scalar(
                select(func.count(QuestionAnswer.id)).where(QuestionAnswer.session_id == session_id)
            ) or 0
        return int(count) > 0

    def _load_existing_questions(self, session_id: str) -> Dict[str, Any]:
        with SessionLocal() as session:
            qa_rows = (
                session.execute(
                    select(QuestionAnswer)
                    .where(QuestionAnswer.session_id == session_id)
                    .order_by(QuestionAnswer.question_index)
                )
                .scalars()
                .all()
            )

        categorized: Dict[str, List[str]] = {}
        ordered_questions: List[str] = []
        for qa in qa_rows:
            category = qa.question_category or "未分类"
            categorized.setdefault(category, []).append(qa.question_text)
            ordered_questions.append(f"【{category}】{qa.question_text}")

        return {
            "questions": ordered_questions,
            "categorized_questions": categorized,
        }

    def _generate_questions_via_rag(
        self,
        memory_id: str,
        resume_id: str,
        resume_data: Dict[str, Any],
        jd_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """通过 RAG 服务生成问题。"""
        from backend.clients.rag_client import get_rag_client

        rag_client = get_rag_client()
        resume_url = f"resumes/{resume_id}/resume.json"

        result = rag_client.generate_questions(
            memory_id=memory_id,
            resume_url=resume_url,
            company=resume_data.get("company"),
            target_position=resume_data.get("position"),
            jd_id=jd_id,
            jd_top_k=3,
            memory_top_k=3,
            max_chars=4000,
        )

        questions = [
            str(question).strip()
            for question in result.get("questions", [])
            if str(question).strip()
        ]
        return {
            "questions": questions,
            "context_used": result.get("context_used"),
        }

    def _format_resume_for_llm(self, resume_data: Dict[str, Any]) -> str:
        """格式化简历数据供 LLM 使用。"""
        if not resume_data:
            return ""

        content = f"""
姓名：{resume_data.get('name', '')}
职位：{resume_data.get('position', '')}

技能：
"""
        skills = resume_data.get("skills", [])
        for index, skill in enumerate(skills, 1):
            content += f"{index}. {skill}\n"

        content += "\n项目经验：\n"
        projects = resume_data.get("projects", [])
        for index, project in enumerate(projects, 1):
            content += f"{index}. {project}\n"

        return content.strip()

    def _merge_ordered_questions(self, ordered_questions: List[tuple[str, str]]) -> List[str]:
        """按既定顺序合并问题文本。"""
        return [f"【{category}】{question}" for category, question in ordered_questions]

    def _select_main_questions_plan(
        self,
        categorized_questions: Dict[str, List[str]],
        per_category: int,
    ) -> tuple[Dict[str, List[str]], List[tuple[str, str]]]:
        """
        选择主问题方案：
        - 目标：基础题/项目题/场景题各 `per_category` 道
        - 若某类不足，使用其它类别题目补齐
        - 输出顺序按“技能->项目->场景”交错排列
        """
        if per_category <= 0:
            return {}, []

        normalized: Dict[str, List[str]] = {}
        for category, questions in categorized_questions.items():
            normalized[category] = [str(question).strip() for question in questions if str(question).strip()]

        selected: Dict[str, List[str]] = {category: [] for category in self.MAIN_CATEGORY_ORDER}
        used_questions: set[str] = set()

        # 先取同类题目，尽量满足2/2/2分类目标。
        for category in self.MAIN_CATEGORY_ORDER:
            for question in normalized.get(category, []):
                if len(selected[category]) >= per_category:
                    break
                if question in used_questions:
                    continue
                selected[category].append(question)
                used_questions.add(question)

        # 回收池：把剩余题目作为补位来源。
        fallback_pool: List[str] = []
        ordered_pool_categories = self.MAIN_CATEGORY_ORDER + [
            category for category in normalized.keys() if category not in self.MAIN_CATEGORY_ORDER
        ]
        for category in ordered_pool_categories:
            for question in normalized.get(category, []):
                if question in used_questions:
                    continue
                fallback_pool.append(question)
                used_questions.add(question)

        # 对短缺类别进行补位。
        for category in self.MAIN_CATEGORY_ORDER:
            while len(selected[category]) < per_category and fallback_pool:
                selected[category].append(fallback_pool.pop(0))

        # 交错顺序输出：技能->项目->场景，再循环下一轮。
        ordered_questions: List[tuple[str, str]] = []
        for index in range(per_category):
            for category in self.MAIN_CATEGORY_ORDER:
                if index < len(selected[category]):
                    ordered_questions.append((category, selected[category][index]))

        selected_trimmed = {category: questions for category, questions in selected.items() if questions}
        return selected_trimmed, ordered_questions

    def _create_question_answer_records(self, session_id: str, ordered_questions: List[tuple[str, str]]) -> None:
        """为会话创建问答记录。"""
        with db_session() as session:
            for question_index, (category, question) in enumerate(ordered_questions):
                session.add(
                    QuestionAnswer(
                        id=str(uuid.uuid4()),
                        session_id=session_id,
                        parent_qa_id=None,
                        question_index=question_index,
                        depth=0,
                        question_type="main",
                        question_text=question,
                        answer_score=None,
                        answer_eval_brief=None,
                        question_category=category,
                        is_answered=False,
                    )
                )
