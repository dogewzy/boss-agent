from __future__ import annotations

import json
import re

from app.schemas import JDAnalysis


def build_jd_analysis_messages(
    *,
    job_title: str,
    company: str,
    description: str,
) -> list[dict[str, str]]:
    system = (
        "你是资深招聘 JD 分析专家。你的任务是把岗位描述抽象成稳定的岗位画像，"
        "用于后续匹配候选人简历事实。只输出严格 JSON，不要 Markdown，不要解释。"
    )
    user = f"""
请分析以下 JD，输出严格 JSON。不要编造 JD 中没有的信息；可以做合理归纳。

JSON schema:
{{
  "role_type": "岗位类型，例如 AI Coding研发效能 / Agent 应用工程化 / LLM Runtime平台 / 数据平台智能化 / FDE现场交付 / RAG知识库 等",
  "business_scenarios": ["业务场景，最多5项"],
  "core_capabilities": ["岗位最看重的能力，最多6项"],
  "engineering_requirements": ["工程要求，最多5项"],
  "bonus_points": ["加分项，最多5项"],
  "communication_angle": "给候选人开场沟通时最应该强调的角度，1句话",
  "avoid_points": ["如果候选人简历里有但本JD不应重点强调的方向，最多5项"]
}}

判断要求：
1. role_type 要根据 JD 主体判断，不要只看标题。
2. business_scenarios 要贴业务词，例如 AI辅助研发、代码生成、PR自动化、故障自动修复、车联网智能应用、数据治理、客户现场、知识库、部署交付。
3. core_capabilities 要贴能力词，例如需求分析、架构设计、RAG、Workflow、Tool Calling、Agent编排、代码仓库理解、可观测性、灰度发布、审计、性能稳定性。
4. avoid_points 用来防止候选人乱秀不相关经历，例如 JD 没有线上诊断就不要强调 K8s 日志排查。
5. 如果 JD 出现 coding、代码生成、单测、代码评审、PR、CI/CD、质量门禁、研发效能、自动修复、补丁、跑测等词，role_type 应优先归纳为 AI Coding研发效能 / Agent应用工程化。
6. 输出必须是一个 JSON object。

岗位标题：
{job_title or "未知"}

公司：
{company or "未知"}

JD：
{description}
""".strip()
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def parse_jd_analysis(raw_text: str, description: str) -> JDAnalysis:
    try:
        payload = json.loads(_extract_json_object(raw_text))
        return enrich_jd_analysis(JDAnalysis.model_validate(payload), description)
    except Exception:
        return enrich_jd_analysis(fallback_jd_analysis(description), description)


def fallback_jd_analysis(description: str) -> JDAnalysis:
    text = description.lower()
    business_scenarios: list[str] = []
    core_capabilities: list[str] = []
    engineering_requirements: list[str] = []
    bonus_points: list[str] = []
    avoid_points: list[str] = []

    if _contains_any(text, _CODING_EFFICIENCY_KEYWORDS):
        role_type = "AI Coding研发效能 / Agent 应用工程化"
        business_scenarios.extend(["AI 辅助研发", "代码生成", "代码评审", "PR 自动化", "故障诊断与自动修复"])
        core_capabilities.extend(["Coding Agent", "代码仓库理解", "Agent 编排", "可观测性", "质量门禁", "CI/CD 集成"])
        engineering_requirements.extend(["Python 后端工程", "工程系统落地", "稳定性与审计"])
        bonus_points.extend(["研发效能平台经验", "AI Coding 工具经验", "自动化测试和发布经验"])
        avoid_points.extend(["泛泛的 RAG 知识库", "数据平台治理", "客户现场交付"])
    elif _contains_any(text, ["数据平台", "数据治理", "数据分析", "bi", "搜索推荐", "大数据", "数据开发"]):
        role_type = "数据平台智能化 / Agent 应用研发"
        business_scenarios.extend(["数据平台智能化", "数据开发", "数据治理", "数据分析"])
        core_capabilities.extend(["Agent 方案设计", "RAG", "Workflow", "Tool Calling"])
        engineering_requirements.extend(["Python 后端工程", "性能和稳定性优化"])
        bonus_points.extend(["大数据系统经验", "搜索推荐或 BI 经验"])
        avoid_points.extend(["K8s 日志排查", "线上诊断", "代码仓库分析"])
    elif _contains_any(text, ["现场", "部署", "交付", "客户", "实施", "解决方案"]):
        role_type = "FDE现场交付 / 企业 AI 应用落地"
        business_scenarios.extend(["客户现场", "部署交付", "需求调研", "解决方案落地"])
        core_capabilities.extend(["业务理解", "方案设计", "跨角色协作", "问题排查"])
        engineering_requirements.extend(["Python 后端工程", "部署运维基础"])
    elif _contains_any(text, ["知识库", "rag", "检索", "问答"]):
        role_type = "RAG知识库 / AI 应用研发"
        business_scenarios.extend(["知识库", "智能问答", "检索增强生成"])
        core_capabilities.extend(["RAG", "知识切片", "向量检索", "Prompt Engineering"])
        engineering_requirements.extend(["Python 后端工程", "LLM 应用工程"])
    else:
        role_type = "Agent 应用研发"
        business_scenarios.extend(["AI 应用落地", "Agent 能力建设"])
        core_capabilities.extend(["Agent 架构", "Tool Calling", "工程化落地"])
        engineering_requirements.extend(["Python 后端工程", "系统稳定性"])

    return JDAnalysis(
        role_type=role_type,
        business_scenarios=business_scenarios[:5],
        core_capabilities=core_capabilities[:6],
        engineering_requirements=engineering_requirements[:5],
        bonus_points=bonus_points[:5],
        communication_angle="围绕 JD 的业务场景选择简历事实，少讲无关技术亮点。",
        avoid_points=avoid_points[:5],
    )


def enrich_jd_analysis(analysis: JDAnalysis, description: str) -> JDAnalysis:
    text = description.lower()
    if not _contains_any(text, _CODING_EFFICIENCY_KEYWORDS):
        return analysis

    role_type = analysis.role_type
    if not _contains_any(role_type.lower(), ["coding", "研发效能", "代码", "ai辅助研发"]):
        role_type = f"AI Coding研发效能 / {role_type}".strip(" /")

    return analysis.model_copy(
        update={
            "role_type": role_type,
            "business_scenarios": _prepend_unique(
                analysis.business_scenarios,
                ["AI 辅助研发", "代码生成", "代码评审", "PR 自动化", "故障诊断与自动修复"],
                limit=5,
            ),
            "core_capabilities": _prepend_unique(
                analysis.core_capabilities,
                ["Coding Agent", "代码仓库理解", "Agent 编排", "可观测性", "质量门禁", "CI/CD 集成"],
                limit=6,
            ),
            "engineering_requirements": _prepend_unique(
                analysis.engineering_requirements,
                ["Python 后端工程", "工程系统落地", "稳定性与审计"],
                limit=5,
            ),
            "bonus_points": _prepend_unique(
                analysis.bonus_points,
                ["AI Coding 工具经验", "研发效能平台经验", "自动化测试和发布经验"],
                limit=5,
            ),
            "communication_angle": "优先强调 AI Coding/研发效能链路、代码仓库理解、自动化修复与可观测工程化落地。",
            "avoid_points": _prepend_unique(
                analysis.avoid_points,
                ["泛泛的 RAG 知识库", "纯聊天机器人经验", "与研发效能无关的数据平台经验"],
                limit=5,
            ),
        }
    )


def _extract_json_object(raw_text: str) -> str:
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        return cleaned[start : end + 1]
    return cleaned


def _contains_any(text: str, keywords: list[str]) -> bool:
    return any(keyword.lower() in text for keyword in keywords)


def _prepend_unique(existing: list[str], priority: list[str], *, limit: int) -> list[str]:
    result: list[str] = []
    for value in [*priority, *existing]:
        normalized = value.strip()
        if normalized and normalized not in result:
            result.append(normalized)
    return result[:limit]


_CODING_EFFICIENCY_KEYWORDS = [
    "coding",
    "代码生成",
    "单测",
    "测试生成",
    "文档/注释",
    "注释生成",
    "代码评审",
    "代码评审辅助",
    "质量门禁",
    "pr",
    "pull request",
    "ci/cd",
    "研发效能",
    "自动化工具",
    "自动化测试",
    "自动修复",
    "修复编排",
    "补丁",
    "跑测",
    "提交pr",
    "代码仓库",
    "研发流程",
    "lint",
    "license",
]
