"""追问决策相关提示词。"""


def get_follow_up_decision_prompt(question: str, answer: str, category: str | None = None) -> str:
    """生成追问决策提示词。"""

    safe_category = (category or "未分类").strip() or "未分类"
    return f"""
你是一位技术面试官。请基于候选人的回答，判断是否需要追问。

当前主问题：
{question}

问题分类：
{safe_category}

候选人回答：
{answer}

请仅输出 JSON，不要输出其他内容。格式如下：
{{
  "answer_score": 0-10 的数字,
  "answer_eval_brief": "20-60字，简要评价回答质量",
  "should_follow_up": true 或 false,
  "follow_up_question": "若 should_follow_up=true，则给出1个高质量追问；否则为空字符串"
}}

决策规则：
1. 当回答明显空泛、缺少关键细节、与问题偏离、存在明显矛盾时，should_follow_up=true。
2. 当回答已经结构完整、细节充分、能支撑结论时，should_follow_up=false。
3. follow_up_question 必须具体、可验证、可继续深挖，且要以问号结尾。
4. follow_up_question 不得重复原题。
5. answer_score 保留一位小数即可。
""".strip()
