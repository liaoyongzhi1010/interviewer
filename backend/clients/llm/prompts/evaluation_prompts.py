"""
面试评价相关prompt模板
"""

from typing import Any, Dict


def get_interview_evaluation_prompt(qa_data: Dict[str, Any]) -> str:
    """
    生成面试评价的prompt模板
    基于华为面试报告格式进行评价
    """
    qa_pairs = qa_data.get('qa_pairs', [])
    qa_chains = qa_data.get('qa_chains', [])
    session_info = qa_data.get('session_info', {})

    qa_content = ""
    for i, qa in enumerate(qa_pairs, 1):
        question_type = qa.get('question_type', 'main')
        question_type_display = "追问" if question_type == "follow_up" else "主问题"
        qa_content += f"""
问题{i}：{qa.get('question', '')}
分类：{qa.get('category', '')}
类型：{question_type_display}
层级：{qa.get('depth', 0)}
回答：{qa.get('answer', '')}
回答评分：{qa.get('answer_score', '')}
"""

    chain_content = ""
    for idx, chain in enumerate(qa_chains, 1):
        main = chain.get("main", {})
        follow_ups = chain.get("follow_ups", [])
        chain_content += f"\n主问题{idx}：{main.get('question', '')}\n主问题回答：{main.get('answer', '')}\n"
        if follow_ups:
            for follow_index, follow_up in enumerate(follow_ups, 1):
                chain_content += (
                    f"  追问{follow_index}：{follow_up.get('question', '')}\n"
                    f"  追问回答：{follow_up.get('answer', '')}\n"
                )
        else:
            chain_content += "  无追问\n"

    prompt = f"""
请你作为专业的技术面试官，对以下面试QA进行全面评价。

面试信息：
- 会话名称：{session_info.get('session_name', '')}
- 总题数：{len(qa_pairs)}

面试QA内容：
{qa_content}

主问题-追问链路：
{chain_content}

请按照以下 JSON 格式返回评价结果：

{{
    "interviewer_comment": {{
        "summary": "面试官总体评价（100-200字）",
        "suggestions": "改进建议（100-200字）"
    }},
    "comprehensive_analysis": {{
        "content_completeness": {{
            "score": "1-10 的数字",
            "comment": "内容完整度评价"
        }},
        "highlight_prominence": {{
            "score": "1-10 的数字",
            "comment": "亮点突出度评价"
        }},
        "logical_clarity": {{
            "score": "1-10 的数字",
            "comment": "逻辑清晰度评价"
        }},
        "expression_ability": {{
            "score": "1-10 的数字",
            "comment": "表达能力评价"
        }},
        "position_matching": {{
            "score": "1-10 的数字",
            "comment": "岗位契合度评价"
        }}
    }},
    "key_points_analysis": {{
        "project_depth": {{
            "level": "中",
            "description": "项目深度分析",
            "can_strengthen": true
        }},
        "personality_potential": {{
            "level": "高",
            "description": "个性潜质分析",
            "can_strengthen": false
        }},
        "professional_knowledge": {{
            "level": "中",
            "description": "专业知识点分析",
            "can_strengthen": true
        }},
        "soft_skills": {{
            "level": "高",
            "description": "软素质分析",
            "can_strengthen": false
        }}
    }},
    "question_analysis": [
        {{
            "question_number": 1,
            "question": "问题内容",
            "category": "问题分类",
            "question_type": "main/follow_up",
            "parent_question_number": null,
            "key_points": "本题考点",
            "improvement_suggestions": "改进建议",
            "reference_answer": "参考回答"
        }}
    ]
}}

评价要求：
1. 分数范围1-10分，要客观公正
2. 评价要具体，避免空泛
3. 改进建议要有针对性和可操作性
4. 参考回答要专业且简洁
5. 保持专业的面试官语气
6. 针对每个问题都要给出具体的分析和改进建议
7. 考点分析要准确，体现问题的技术深度
8. 对追问题重点评价：回答是否补全主问题关键细节
9. 禁止使用固定模板分（例如 8/7/7/8/8），必须基于本场问答内容给出动态分数
10. 最终输出必须是合法 JSON，score 必须是数值类型（不是字符串）
"""
    return prompt
