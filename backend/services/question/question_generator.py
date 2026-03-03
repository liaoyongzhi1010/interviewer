"""
面试问题生成服务
负责根据简历生成面试题
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from backend.clients.llm.qwen_client import QwenClient
from backend.clients.rag_client import get_rag_client
from backend.common.logger import get_logger
from backend.models import QuestionAnswer, db_session
from backend.services.interview_service import RoundService

logger = get_logger(__name__)


class QuestionGenerator:
    """面试题生成器"""

    def __init__(self):
        self.qwen_client = QwenClient()
        self.use_rag = True

    def generate_questions(self, session_id: str) -> Optional[Dict[str, Any]]:
        """为指定会话生成面试题。"""
        try:
            from backend.services.interview_service import SessionService
            from backend.services.resume_service import ResumeService

            session = SessionService.get_session(session_id)
            if not session:
                return {"success": False, "error": "会话不存在"}

            room_id = session.room.id
            room = session.room

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

            if self.use_rag:
                try:
                    questions_result = self._generate_questions_via_rag(
                        memory_id=room.memory_id,
                        resume_data=resume_data,
                        resume_id=room.resume_id,
                        jd_id=room.jd_id,
                    )
                    all_questions = questions_result["questions"]
                    categorized_questions = {"RAG生成": all_questions}
                except Exception as exc:
                    logger.error("Failed to generate questions via RAG: %s", exc)
                    logger.info("Fallback to Qwen client")
                    resume_content = self._format_resume_for_llm(resume_data)
                    categorized_questions = self.qwen_client.generate_questions(resume_content)
                    all_questions = self._merge_questions(categorized_questions)
            else:
                resume_content = self._format_resume_for_llm(resume_data)
                categorized_questions = self.qwen_client.generate_questions(resume_content)
                all_questions = self._merge_questions(categorized_questions)

            if not all_questions:
                raise ValueError("未能生成面试题")

            round_obj = RoundService.create_round(session_id, all_questions)
            if not round_obj:
                raise ValueError("创建轮次失败")

            self._create_question_answer_records(round_obj.id, categorized_questions)

            success = self._save_questions_to_minio(
                all_questions,
                round_obj,
                room_id,
                session_id,
                categorized_questions,
            )
            if not success:
                logger.warning("Failed to save questions to MinIO for round %s", round_obj.id)

            return {
                "success": True,
                "round_id": round_obj.id,
                "questions": all_questions,
                "round_index": round_obj.round_index,
                "categorized_questions": categorized_questions,
            }

        except Exception as exc:
            logger.error("Error generating questions: %s", exc, exc_info=True)
            return {"success": False, "error": str(exc)}

    def _generate_questions_via_rag(
        self,
        memory_id: str,
        resume_data: Dict[str, Any],
        resume_id: str,
        jd_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """通过 RAG 服务生成问题。"""
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

        logger.info("Generated %s questions via RAG for memory %s", len(result["questions"]), memory_id)
        return result

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

    def _merge_questions(self, categorized_questions: Dict[str, List[str]]) -> List[str]:
        """合并分类问题为单一列表。"""
        all_questions: list[str] = []
        for category, questions in categorized_questions.items():
            for question in questions:
                all_questions.append(f"【{category}】{question}")
        return all_questions

    def _create_question_answer_records(self, round_id: str, categorized_questions: Dict[str, List[str]]) -> None:
        """为轮次创建问答记录。"""
        question_index = 0
        with db_session() as session:
            for category, questions in categorized_questions.items():
                for question in questions:
                    session.add(
                        QuestionAnswer(
                            id=str(uuid.uuid4()),
                            round_id=round_id,
                            question_index=question_index,
                            question_text=question,
                            question_category=category,
                            is_answered=False,
                        )
                    )
                    question_index += 1

    def _save_questions_to_minio(
        self,
        all_questions: List[str],
        round_obj,
        room_id: str,
        session_id: str,
        categorized_questions: Dict[str, List[str]],
    ) -> bool:
        """保存问题到 MinIO（使用新的目录结构）。"""
        from backend.clients.minio_client import upload_questions_data

        qa_data = {
            "questions": all_questions,
            "round_id": round_obj.id,
            "session_id": session_id,
            "room_id": room_id,
            "round_index": round_obj.round_index,
            "total_count": len(all_questions),
            "generated_at": datetime.now().isoformat(),
            "categorized_questions": categorized_questions,
        }

        return upload_questions_data(qa_data, room_id, session_id, round_obj.round_index)

