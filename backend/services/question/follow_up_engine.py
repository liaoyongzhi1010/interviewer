"""主问题回答后的追问决策引擎。"""

from __future__ import annotations

import json
import re
from typing import Any, Dict

from backend.clients.llm.prompts.follow_up_prompts import get_follow_up_decision_prompt
from backend.clients.llm.qwen_client import QwenClient
from backend.common.logger import get_logger

logger = get_logger(__name__)


class FollowUpDecisionEngine:
    """根据回答质量判断是否需要追问，并生成追问问题。"""

    def __init__(self):
        self.qwen_client = QwenClient()

    def decide(self, question: str, answer: str, category: str | None = None) -> Dict[str, Any]:
        answer_text = str(answer or "").strip()
        question_text = str(question or "").strip()

        if not answer_text:
            return {
                "answer_score": 0.0,
                "answer_eval_brief": "回答为空，无法评估技术深度。",
                "should_follow_up": True,
                "follow_up_question": self._build_fallback_follow_up(question_text),
            }

        try:
            prompt = get_follow_up_decision_prompt(question_text, answer_text, category)
            response = self.qwen_client.chat_completion(
                [{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=800,
            )
            parsed = self._parse_json_response(response)
            return self._normalize_result(parsed, question_text, answer_text)
        except Exception as exc:
            logger.warning("Follow-up decision via LLM failed, fallback to rule engine: %s", exc)
            return self._fallback_result(question_text, answer_text)

    def _parse_json_response(self, response: str) -> Dict[str, Any]:
        content = str(response or "").strip()
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?", "", content).strip()
            if content.endswith("```"):
                content = content[:-3].strip()
        return json.loads(content)

    def _normalize_result(self, data: Dict[str, Any], question: str, answer: str) -> Dict[str, Any]:
        raw_score = data.get("answer_score", 0)
        try:
            score = float(raw_score)
        except (TypeError, ValueError):
            score = 0.0
        score = max(0.0, min(10.0, score))

        brief = str(data.get("answer_eval_brief") or "").strip()
        if not brief:
            brief = "回答具备基础信息，但可继续深挖关键细节。"

        should_follow_up = bool(data.get("should_follow_up"))
        follow_up_question = str(data.get("follow_up_question") or "").strip()

        if should_follow_up:
            if not follow_up_question:
                follow_up_question = self._build_fallback_follow_up(question)
            elif not follow_up_question.endswith(("?", "？")):
                follow_up_question = f"{follow_up_question.rstrip('。.!！')}？"
        else:
            follow_up_question = ""

        if len(answer) >= 160 and score >= 7.0:
            should_follow_up = False
            follow_up_question = ""

        return {
            "answer_score": round(score, 1),
            "answer_eval_brief": brief[:120],
            "should_follow_up": should_follow_up,
            "follow_up_question": follow_up_question,
        }

    def _fallback_result(self, question: str, answer: str) -> Dict[str, Any]:
        answer_len = len(answer)
        if answer_len < 80:
            return {
                "answer_score": 5.6,
                "answer_eval_brief": "回答信息量不足，关键实现细节缺失。",
                "should_follow_up": True,
                "follow_up_question": self._build_fallback_follow_up(question),
            }

        if answer_len < 140:
            return {
                "answer_score": 6.8,
                "answer_eval_brief": "回答有一定思路，但细节和量化结果不够充分。",
                "should_follow_up": True,
                "follow_up_question": self._build_fallback_follow_up(question),
            }

        return {
            "answer_score": 7.6,
            "answer_eval_brief": "回答结构较完整，具备较好的技术表达。",
            "should_follow_up": False,
            "follow_up_question": "",
        }

    def _build_fallback_follow_up(self, question: str) -> str:
        if question:
            return "你刚才的回答提到了方案方向，请补充核心实现细节、关键取舍和最终效果数据？"
        return "请补充你在该问题上的具体实现细节、关键取舍和最终效果？"
