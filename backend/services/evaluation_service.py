"""面试 QA 评价服务（按会话）。"""

import json
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from backend.clients.llm.prompts.evaluation_prompts import get_interview_evaluation_prompt
from backend.clients.llm.qwen_client import QwenClient
from backend.clients.minio_client import download_qa_analysis, upload_evaluation_report
from backend.common.logger import get_logger

logger = get_logger(__name__)


class InterviewEvaluationService:
    """面试评价服务。"""

    def __init__(self):
        self.qwen_client = QwenClient()

    def generate_evaluation_report(self, session_id: str) -> Optional[Dict[str, Any]]:
        """生成面试评价报告。"""
        try:
            from backend.services.interview_service import SessionService

            session = SessionService.get_session(session_id)
            if not session:
                raise ValueError("会话不存在")
            room_id = session.room.id

            qa_data = self._load_qa_data(room_id, session_id)
            if not qa_data:
                raise ValueError("无法加载问答数据")

            evaluation_result = self._evaluate_with_llm(qa_data)
            report_data = self._build_evaluation_report(qa_data, evaluation_result, session_id)

            report_filename = f"rooms/{room_id}/sessions/{session_id}/reports/evaluation.json"
            success = upload_evaluation_report(report_data, room_id, session_id)

            if success:
                logger.info("Evaluation report saved: %s", report_filename)
                return {
                    "success": True,
                    "report_data": report_data,
                    "report_filename": report_filename,
                }
            raise RuntimeError("保存评价报告失败")

        except Exception as e:
            logger.error("Error generating evaluation report: %s", e, exc_info=True)
            return {
                "success": False,
                "error": str(e),
            }

    def _load_qa_data(self, room_id: str, session_id: str) -> Optional[Dict[str, Any]]:
        """加载问答完成数据。"""
        return download_qa_analysis(room_id, session_id)

    def _evaluate_with_llm(self, qa_data: Dict[str, Any]) -> Dict[str, Any]:
        """使用大模型评价问答数据。"""
        try:
            evaluation_prompt = get_interview_evaluation_prompt(qa_data)
            messages = [{"role": "user", "content": evaluation_prompt}]
            response = self.qwen_client.chat_completion(messages, temperature=0.3, max_tokens=3000)
            return self._parse_evaluation_response(response)

        except Exception as e:
            logger.error("Error in LLM evaluation: %s", e, exc_info=True)
            return self._get_default_evaluation()

    def _parse_evaluation_response(self, response: str) -> Dict[str, Any]:
        """解析大模型评价响应。"""
        try:
            response = response.strip()
            if response.startswith("```json"):
                response = response[7:]
            if response.endswith("```"):
                response = response[:-3]

            evaluation_data = json.loads(response)
            return evaluation_data

        except json.JSONDecodeError as e:
            logger.error("Failed to parse LLM response as JSON: %s", e, exc_info=True)
            return self._get_default_evaluation()

    def _get_default_evaluation(self) -> Dict[str, Any]:
        """获取默认评价结果。"""
        return {
            "interviewer_comment": {
                "summary": "面试者在技术问题上表现良好，展现了一定的基础知识和实践经验。",
                "suggestions": "建议在回答时更加详细和具体，展现更深入的技术理解。",
            },
            "comprehensive_analysis": {
                "content_completeness": {"score": 7, "comment": "回答内容基本完整"},
                "highlight_prominence": {"score": 6, "comment": "亮点表现一般"},
                "logical_clarity": {"score": 7, "comment": "逻辑结构清晰"},
                "expression_ability": {"score": 7, "comment": "表达能力良好"},
                "position_matching": {"score": 7, "comment": "岗位匹配度中等"},
            },
            "key_points_analysis": {
                "project_depth": {
                    "level": "中",
                    "description": "项目经验有一定深度",
                    "can_strengthen": True,
                },
                "personality_potential": {
                    "level": "中",
                    "description": "个性潜质表现一般",
                    "can_strengthen": True,
                },
                "professional_knowledge": {
                    "level": "中",
                    "description": "专业知识掌握程度中等",
                    "can_strengthen": True,
                },
                "soft_skills": {
                    "level": "中",
                    "description": "软技能表现一般",
                    "can_strengthen": True,
                },
            },
            "question_analysis": [],
        }

    def _length_score(self, answer: str) -> float:
        length = len(str(answer or "").strip())
        if length < 40:
            return 4.8
        if length < 80:
            return 6.0
        if length < 140:
            return 6.9
        return 7.6

    def _safe_score(self, raw_score: Any, fallback: float) -> float:
        try:
            score = float(raw_score)
        except (TypeError, ValueError):
            score = fallback
        return max(1.0, min(10.0, score))

    def _derive_dynamic_scores(self, qa_data: Dict[str, Any]) -> Dict[str, float]:
        qa_pairs = qa_data.get("qa_pairs", []) or []
        if not qa_pairs:
            return {
                "content_completeness": 6.6,
                "highlight_prominence": 6.4,
                "logical_clarity": 6.6,
                "expression_ability": 6.7,
                "position_matching": 6.5,
            }

        answered_pairs = [qa for qa in qa_pairs if str(qa.get("answer") or "").strip()]
        answered_count = len(answered_pairs)
        answered_ratio = answered_count / max(1, len(qa_pairs))

        answer_scores = []
        answer_lengths = []
        structure_hits = 0
        strong_hits = 0
        categories = set()

        for qa in answered_pairs:
            answer = str(qa.get("answer") or "").strip()
            answer_lengths.append(len(answer))

            raw_score = qa.get("answer_score")
            score = self._safe_score(raw_score, self._length_score(answer))
            answer_scores.append(score)
            if score >= 7.5:
                strong_hits += 1

            if any(token in answer for token in ["首先", "其次", "然后", "最后", "第一", "第二", "1.", "2."]):
                structure_hits += 1

            category = str(qa.get("category") or "").strip()
            if category:
                categories.add(category)

        avg_score = sum(answer_scores) / max(1, len(answer_scores))
        avg_length = sum(answer_lengths) / max(1, len(answer_lengths))
        strong_ratio = strong_hits / max(1, answered_count)
        structure_ratio = structure_hits / max(1, answered_count)
        category_coverage = len(categories) / 3.0  # 技能题/项目题/场景题

        def clamp(value: float) -> float:
            return round(max(1.0, min(10.0, value)), 1)

        return {
            "content_completeness": clamp(avg_score + (answered_ratio - 0.8) * 2.0 + (avg_length - 140.0) / 220.0),
            "highlight_prominence": clamp(avg_score + (strong_ratio - 0.3) * 2.2 - 0.3),
            "logical_clarity": clamp(avg_score + (structure_ratio - 0.4) * 1.8),
            "expression_ability": clamp(avg_score + (avg_length - 120.0) / 260.0),
            "position_matching": clamp(avg_score + (category_coverage - 0.66) * 1.4 + (strong_ratio - 0.3) * 0.8),
        }

    def _normalize_comprehensive_analysis(
        self,
        qa_data: Dict[str, Any],
        evaluation_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        raw_analysis = evaluation_result.get("comprehensive_analysis", {}) or {}
        derived_scores = self._derive_dynamic_scores(qa_data)

        dimensions = [
            ("content_completeness", "内容完整度"),
            ("highlight_prominence", "亮点突出度"),
            ("logical_clarity", "逻辑清晰度"),
            ("expression_ability", "表达能力"),
            ("position_matching", "岗位契合度"),
        ]
        template_signature = [8.0, 7.0, 7.0, 8.0, 8.0]

        parsed_scores = []
        for key, _ in dimensions:
            raw_item = raw_analysis.get(key, {})
            fallback = derived_scores[key]
            score = self._safe_score(raw_item.get("score"), fallback)
            parsed_scores.append(round(score, 1))

        is_template_like = parsed_scores == template_signature
        score_span = max(parsed_scores) - min(parsed_scores) if parsed_scores else 0.0
        should_force_dynamic = is_template_like or score_span < 0.2

        normalized: Dict[str, Any] = {}
        for key, label in dimensions:
            raw_item = raw_analysis.get(key, {})
            dynamic_score = derived_scores[key]
            final_score = dynamic_score if should_force_dynamic else self._safe_score(raw_item.get("score"), dynamic_score)
            comment = str(raw_item.get("comment") or "").strip()
            if not comment:
                comment = f"{label}表现为 {final_score} 分，建议继续通过结构化表达与案例细节提升表现。"
            normalized[key] = {
                "score": round(final_score, 1),
                "comment": comment,
            }

        return normalized

    def _build_evaluation_report(
        self,
        qa_data: Dict[str, Any],
        evaluation_result: Dict[str, Any],
        session_id: str,
    ) -> Dict[str, Any]:
        """构建完整的评价报告。"""
        session_info = qa_data.get("session_info", {})
        qa_pairs = qa_data.get("qa_pairs", [])

        normalized_analysis = self._normalize_comprehensive_analysis(qa_data, evaluation_result)
        scores = normalized_analysis
        total_score = sum(
            [
                scores.get("content_completeness", {}).get("score", 7),
                scores.get("highlight_prominence", {}).get("score", 6),
                scores.get("logical_clarity", {}).get("score", 7),
                scores.get("expression_ability", {}).get("score", 7),
                scores.get("position_matching", {}).get("score", 7),
            ]
        ) / 5

        if total_score >= 9:
            grade = "A+"
        elif total_score >= 8:
            grade = "A"
        elif total_score >= 7:
            grade = "B+"
        elif total_score >= 6:
            grade = "B"
        else:
            grade = "C"

        report_data = {
            "report_id": str(uuid.uuid4()),
            "generated_at": datetime.now().isoformat(),
            "session_info": {
                "session_id": session_id,
                "session_name": session_info.get("session_name", ""),
                "room_id": session_info.get("room_id", ""),
                "total_questions": len(qa_pairs),
            },
            "report_header": {
                "company_name": "夜莺面试官",
                "report_title": f"{session_info.get('session_name', '面试会话')}-模拟面试报告",
                "generated_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "overall_grade": grade,
                "total_score": round(total_score, 1),
            },
            "interviewer_comment": evaluation_result.get("interviewer_comment", {}),
            "comprehensive_analysis": normalized_analysis,
            "key_points_analysis": evaluation_result.get("key_points_analysis", {}),
            "question_analysis": evaluation_result.get("question_analysis", []),
            "original_qa_data": qa_pairs,
            "metadata": {
                "report_type": "interview_evaluation",
                "version": "2.0",
                "template": "huawei_style",
            },
        }

        return report_data

_evaluation_service = None


def get_evaluation_service():
    """获取评价服务实例（延迟初始化）。"""
    global _evaluation_service
    if _evaluation_service is None:
        _evaluation_service = InterviewEvaluationService()
    return _evaluation_service
