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
  "main_responsibilities": ["主职责/岗位主体，最多5项"],
  "required_skills": ["必备要求，最多6项"],
  "business_scenarios": ["业务场景，最多5项"],
  "core_capabilities": ["岗位最看重的能力，最多6项"],
  "engineering_requirements": ["工程要求，最多5项"],
  "bonus_points": ["加分项，最多5项"],
  "communication_angle": "给候选人开场沟通时最应该强调的角度，1句话",
  "avoid_points": ["如果候选人简历里有但本JD不应重点强调的方向，最多5项"]
}}

判断要求：
1. role_type 要根据 JD 主体判断，不要只看标题。
2. 必须区分主职责、必备要求、加分项。加分项不能覆盖岗位主体。
3. business_scenarios 要贴业务词，例如 AI辅助研发、代码生成、PR自动化、故障自动修复、车联网智能应用、电商治理、AI客服、知识库、部署交付。
4. core_capabilities 要贴能力词，例如需求分析、架构设计、RAG、Workflow、Tool Calling、Agent编排、代码仓库理解、可观测性、灰度发布、审计、性能稳定性。
5. avoid_points 用来防止候选人乱秀不相关经历，例如 JD 没有线上诊断就不要强调 K8s 日志排查。
6. 只有当 AI Coding、代码生成、PR、CI/CD、质量门禁、研发效能、自动修复等内容出现在标题或主职责中时，role_type 才应归纳为 AI Coding研发效能。若这些词只出现在加分项中，只能放入 bonus_points。
7. 输出必须是一个 JSON object。

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


def parse_jd_analysis(raw_text: str, description: str, job_title: str = "") -> JDAnalysis:
    try:
        payload = json.loads(_extract_json_object(raw_text))
        return enrich_jd_analysis(JDAnalysis.model_validate(payload), description, job_title)
    except Exception:
        return enrich_jd_analysis(fallback_jd_analysis(description, job_title), description, job_title)


def fallback_jd_analysis(description: str, job_title: str = "") -> JDAnalysis:
    text = _main_signal_text(description, job_title).lower()
    full_text = f"{job_title}\n{description}".lower()
    coding_in_main = _contains_any(text, _CODING_EFFICIENCY_KEYWORDS)
    business_scenarios: list[str] = []
    main_responsibilities: list[str] = []
    required_skills: list[str] = []
    core_capabilities: list[str] = []
    engineering_requirements: list[str] = []
    bonus_points: list[str] = []
    avoid_points: list[str] = []

    if coding_in_main:
        role_type = "AI Coding研发效能 / Agent 应用工程化"
        main_responsibilities.extend(["AI 辅助研发链路建设", "代码生成/评审/PR 自动化", "自动化诊断与修复"])
        required_skills.extend(["Agent 编排", "代码仓库理解", "CI/CD 集成", "可观测性"])
        business_scenarios.extend(["AI 辅助研发", "代码生成", "代码评审", "PR 自动化", "故障诊断与自动修复"])
        core_capabilities.extend(["Coding Agent", "代码仓库理解", "Agent 编排", "可观测性", "质量门禁", "CI/CD 集成"])
        engineering_requirements.extend(["Python 后端工程", "工程系统落地", "稳定性与审计"])
        bonus_points.extend(["研发效能平台经验", "AI Coding 工具经验", "自动化测试和发布经验"])
        avoid_points.extend(["泛泛的 RAG 知识库", "数据平台治理", "客户现场交付"])
    elif _contains_any(text, ["电商治理", "交易治理", "商家宣教", "假货", "纠纷仲裁", "信用评价", "规则引擎", "处置平台", "审核平台"]):
        role_type = "服务端平台 / 电商治理系统"
        main_responsibilities.extend(["电商治理业务平台建设", "规则引擎和处置平台", "人机协同审核平台"])
        required_skills.extend(["服务端研发", "Java/Spring/Dubbo", "微服务架构", "数据结构与工程能力"])
        business_scenarios.extend(["电商治理", "商家宣教", "纠纷仲裁", "人机协同审核", "大数据情报感知"])
        core_capabilities.extend(["高性能规则引擎", "可解释处置平台", "服务端工程", "业务治理抽象"])
        engineering_requirements.extend(["Java 服务端", "微服务", "高性能平台建设"])
        if _contains_any(full_text, _CODING_EFFICIENCY_KEYWORDS):
            bonus_points.extend(["AI Coding/Agent 经验"])
        avoid_points.extend(["把 AI Coding 当作岗位主体", "纯 Agent Demo", "与电商治理无关的代码修复"])
    elif _contains_any(text, ["数据平台", "数据治理", "数据分析", "bi", "搜索推荐", "大数据", "数据开发"]):
        role_type = "数据平台智能化 / Agent 应用研发"
        main_responsibilities.extend(["数据平台智能化建设", "数据开发/治理/分析场景 Agent 落地"])
        required_skills.extend(["Agent 方案设计", "Python 后端工程", "数据系统经验"])
        business_scenarios.extend(["数据平台智能化", "数据开发", "数据治理", "数据分析"])
        core_capabilities.extend(["Agent 方案设计", "RAG", "Workflow", "Tool Calling"])
        engineering_requirements.extend(["Python 后端工程", "性能和稳定性优化"])
        bonus_points.extend(["大数据系统经验", "搜索推荐或 BI 经验"])
        avoid_points.extend(["K8s 日志排查", "线上诊断", "代码仓库分析"])
    elif _contains_any(text, ["现场", "部署", "交付", "客户", "实施", "解决方案"]):
        role_type = "FDE现场交付 / 企业 AI 应用落地"
        main_responsibilities.extend(["客户现场交付", "需求调研", "解决方案落地"])
        required_skills.extend(["业务理解", "部署实施", "跨角色沟通"])
        business_scenarios.extend(["客户现场", "部署交付", "需求调研", "解决方案落地"])
        core_capabilities.extend(["业务理解", "方案设计", "跨角色协作", "问题排查"])
        engineering_requirements.extend(["Python 后端工程", "部署运维基础"])
    elif _contains_any(text, ["知识库", "rag", "检索", "问答"]):
        role_type = "RAG知识库 / AI 应用研发"
        main_responsibilities.extend(["知识库/问答系统建设", "RAG 能力落地"])
        required_skills.extend(["RAG", "向量检索", "Prompt Engineering"])
        business_scenarios.extend(["知识库", "智能问答", "检索增强生成"])
        core_capabilities.extend(["RAG", "知识切片", "向量检索", "Prompt Engineering"])
        engineering_requirements.extend(["Python 后端工程", "LLM 应用工程"])
    else:
        role_type = "Agent 应用研发"
        main_responsibilities.extend(["Agent 能力建设", "AI 应用工程化落地"])
        required_skills.extend(["Agent 架构", "Tool Calling", "Python 后端工程"])
        business_scenarios.extend(["AI 应用落地", "Agent 能力建设"])
        core_capabilities.extend(["Agent 架构", "Tool Calling", "工程化落地"])
        engineering_requirements.extend(["Python 后端工程", "系统稳定性"])

    return JDAnalysis(
        role_type=role_type,
        main_responsibilities=main_responsibilities[:5],
        required_skills=required_skills[:6],
        business_scenarios=business_scenarios[:5],
        core_capabilities=core_capabilities[:6],
        engineering_requirements=engineering_requirements[:5],
        bonus_points=bonus_points[:5],
        communication_angle="围绕 JD 的业务场景选择简历事实，少讲无关技术亮点。",
        avoid_points=avoid_points[:5],
    )


def enrich_jd_analysis(analysis: JDAnalysis, description: str, job_title: str = "") -> JDAnalysis:
    main_text = _main_signal_text(description, job_title).lower()
    full_text = f"{job_title}\n{description}".lower()
    coding_in_main = _contains_any(main_text, _CODING_EFFICIENCY_KEYWORDS)
    coding_anywhere = _contains_any(full_text, _CODING_EFFICIENCY_KEYWORDS)
    if not coding_anywhere:
        return analysis

    role_type = analysis.role_type
    if coding_in_main and not _contains_any(role_type.lower(), ["coding", "研发效能", "代码", "ai辅助研发"]):
        role_type = f"AI Coding研发效能 / {role_type}".strip(" /")

    if not coding_in_main:
        return analysis.model_copy(
            update={
                "role_type": _remove_coding_prefix(role_type),
                "bonus_points": _prepend_unique(
                    analysis.bonus_points,
                    ["AI Coding/Agent 经验"],
                    limit=5,
                ),
                "avoid_points": _prepend_unique(
                    analysis.avoid_points,
                    ["把加分项 AI Coding 当作岗位主体"],
                    limit=5,
                ),
            }
        )

    return analysis.model_copy(
        update={
            "role_type": role_type,
            "main_responsibilities": _prepend_unique(
                analysis.main_responsibilities,
                ["AI 辅助研发链路建设", "代码生成/评审/PR 自动化", "自动化诊断与修复"],
                limit=5,
            ),
            "required_skills": _prepend_unique(
                analysis.required_skills,
                ["Agent 编排", "代码仓库理解", "CI/CD 集成", "可观测性"],
                limit=6,
            ),
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


def _main_signal_text(description: str, job_title: str = "") -> str:
    text = f"{job_title}\n{description}"
    bonus_markers = [
        "加分项",
        "优先加分项",
        "优先考虑",
        "加分：",
        "加分:",
        "bonus",
    ]
    indexes = [text.find(marker) for marker in bonus_markers if text.find(marker) >= 0]
    if indexes:
        text = text[: min(indexes)]
    return text


def _remove_coding_prefix(role_type: str) -> str:
    cleaned = re.sub(r"^AI\s*Coding研发效能\s*/\s*", "", role_type).strip()
    return cleaned or role_type


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
    "pr自动化",
    "pr 自动化",
    "提交pr",
    "提交 pr",
    "pr模板",
    "pr 模板",
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
