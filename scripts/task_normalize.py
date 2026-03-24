#!/usr/bin/env python3
"""
任务标准化：从原始任务 payload 推导 task_brief，缺失字段填默认假设。
不调用任何 LLM，纯规则映射。
stdin JSON:  原始任务 payload（含 topic/goal/audience/brand_voice 等）
stdout JSON: {"success": true, "data": {"task_brief": {...}, "assumptions": [...]}}
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from lib.common import read_stdin, ok, fail, CFG

# 关键词 → content_type 推断
CONTENT_TYPE_HINTS = {
    "指南": "guide", "教程": "guide", "如何": "guide", "怎么": "guide", "步骤": "guide",
    "分析": "analysis", "报告": "analysis", "研究": "analysis", "数据": "analysis",
    "新闻": "news_commentary", "热点": "news_commentary", "评论": "news_commentary",
    "故事": "brand_story", "品牌": "brand_story", "案例": "case_study",
    "观点": "opinion", "为什么": "opinion", "应该": "opinion",
}

INTENT_HINTS = {
    "传播": "traffic", "阅读": "traffic", "流量": "traffic", "热门": "traffic",
    "转化": "conversion", "销售": "conversion", "购买": "conversion", "转介绍": "conversion",
    "品牌": "branding", "专业": "branding", "信任": "branding", "形象": "branding",
    "教育": "education", "学习": "education", "知识": "education", "理解": "education",
}

def infer_content_type(topic: str, goal: str):
    text = (topic or "") + (goal or "")
    for kw, ct in CONTENT_TYPE_HINTS.items():
        if kw in text:
            return ct, None
    return "education", f"无法推断内容类型，默认使用 'education'"

def infer_intent(goal: str, topic: str):
    text = (goal or "") + (topic or "")
    for kw, intent in INTENT_HINTS.items():
        if kw in text:
            return intent, None
    return "branding", f"无法推断内容意图，默认使用 'branding'"

def main():
    inp = read_stdin()
    topic = (inp.get("topic") or "").strip()
    if not topic:
        fail("invalid_param", "topic is required")

    goal       = inp.get("goal", "")
    audience   = inp.get("audience", "")
    brand_voice = inp.get("brand_voice") or CFG.get("task_defaults", {}).get("brand_voice", "专业、克制、可信")
    must_include = inp.get("must_include", [])
    must_avoid   = inp.get("must_avoid", [])

    assumptions = []

    content_type, ct_note = infer_content_type(topic, goal)
    if ct_note:
        assumptions.append(ct_note)

    intent, intent_note = infer_intent(goal, topic)
    if intent_note:
        assumptions.append(intent_note)

    if not audience:
        audience = "微信公众号读者（通用）"
        assumptions.append("未指定受众，默认使用通用读者画像")

    if not goal:
        goal = f'围绕"{topic}"产出高质量内容，提升品牌专业度'
        assumptions.append("未指定内容目标，使用默认品牌目标")

    constraints = []
    if must_include:
        constraints.append(f"必须包含：{', '.join(must_include)}")
    if must_avoid:
        constraints.append(f"必须规避：{', '.join(must_avoid)}")

    task_brief = {
        "topic_statement": topic,
        "content_type":    content_type,
        "audience_profile": audience,
        "intent":          intent,
        "brand_voice":     brand_voice,
        "constraints":     constraints,
        "assumptions":     assumptions,
        "goal":            goal,
    }

    ok({"task_brief": task_brief, "assumptions": assumptions})

if __name__ == "__main__":
    main()
