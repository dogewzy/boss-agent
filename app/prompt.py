from __future__ import annotations

import json

from app.schemas import JDAnalysis


def build_messages(
    *,
    resume_text: str,
    job_title: str,
    company: str,
    description: str,
    jd_analysis: JDAnalysis,
    history_examples: list[dict] | None = None,
) -> list[dict[str, str]]:
    system = (
        "你是一个求职沟通助手，帮助候选人基于岗位 JD 和简历生成 BOSS 直聘开场打招呼内容。"
        "你必须严格依据 JD 画像选择简历中最贴近的事实，不要默认堆候选人最强但不相关的经历。"
        "要求：中文，真诚自然，不夸大，不编造经历，不出现联系方式，不要使用项目符号，"
        "总长度必须小于 190 个中文字符。"
    )
    user = f"""
请根据以下信息生成一段可以直接发送给招聘方的打招呼内容。

输出要求：
1. 以“您好”开头。
2. 先覆盖 JD 的 2-3 个核心关键词或业务场景，再写个人优势。
3. 优先引用简历中最能匹配 JD 的 2-3 个事实，弱相关经历不要写。
4. 如果 JD 强调数据平台、数据治理、数据分析、BI、搜索推荐或大数据系统，优先提数据工作流、调度、ETL、大数据量查询、Milvus/向量检索、Agent 与数据场景结合等经历。
5. 如果 JD 强调 AI Coding、研发效能、代码生成、代码评审、PR 自动化、CI/CD、自动修复或质量门禁，优先提 Coding Agent、代码仓库理解、AI IDE/Coding Agent 使用、受控代码修改/MR、trace 审计、自动化测试/发布等经历；不要泛泛写 RAG 知识库。
6. 如果 JD 画像不是 AI Coding/研发效能方向，输出中禁止出现“Coding Agent”“代码仓库”“受控代码修改”“MR”等 AI Coding 证据；可改用 Agent 基建、业务流程抽象、工具编排、多 Agent、RAG、后端工程等更贴近岗位主体的事实。
7. 如果 JD 没有明确提到 K8s、日志、线上诊断、部署运维，不要把 K8s、日志、生产诊断作为招呼重点。
8. 不要只罗列技术名词，要把技术名词落到“能做什么场景”。
9. 不要写“我非常完美匹配”等过度营销表达。
10. 候选人的工作年限、项目数量、用户数量、技术经历只能来自简历，不能从 JD 的任职要求中复制。例如 JD 写“5年以上经验”不代表候选人只有5年。
11. 优先匹配 JD 画像中的 main_responsibilities 和 required_skills；bonus_points 只能作为辅助，不要覆盖岗位主体。
12. 只输出打招呼正文，不要解释。

推荐句式：
您好，我有 X 年 Python 后端/Agent 工程化经验，做过 A 场景和 B 场景；结合 JD 的 C/D/E 方向，我过往的 F 经历可以支撑快速落地。

JD 画像：
{_dump_analysis(jd_analysis)}

相似历史记录：
{_dump_history_examples(history_examples or [])}

岗位标题：
{job_title or "未知"}

公司：
{company or "未知"}

职位描述：
{description}

候选人简历：
{resume_text}
""".strip()
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def build_resume_polish_messages(
    *,
    resume_text: str,
    job_title: str,
    company: str,
    description: str,
    jd_analysis: JDAnalysis,
) -> list[dict[str, str]]:
    system = (
        "你是资深中文技术简历顾问，擅长根据岗位 JD 对候选人的既有简历进行定制化润色。"
        "必须严格基于原简历事实，不得编造不存在的公司、项目、职责、数字、学历、证书或技术栈。"
        "可以调整表达顺序、标题、个人优势、技能分组和项目 bullet 的侧重点，让简历更贴合岗位。"
        "只输出完整 Markdown 简历正文，不要解释，不要使用代码块。"
    )
    user = f"""
请基于目标岗位，对候选人简历进行完整润色，生成一份可直接保存为 Markdown 的定制版简历。

润色要求：
1. 保留候选人真实身份信息、工作经历时间线、公司和教育经历。
2. 根据 JD 强化最相关的能力与项目证据，把弱相关内容压缩，但不要删除关键履历连续性。
3. “个人优势 / 与岗位匹配的核心能力 / 技能栈 / 项目经历”这些部分可以重组，但必须来自原简历事实。
4. 项目 bullet 尽量体现“场景 -> 动作 -> 结果 / 证据”，数字只能使用原简历已经出现过的数字。
5. 语言自然、专业、克制，适合发送给招聘方或投递系统。
6. 输出完整 Markdown，不要附加任何说明。
7. 根据 JD 画像强化最相关部分，画像中的 avoid_points 不要作为简历重点。

JD 画像：
{_dump_analysis(jd_analysis)}

目标岗位标题：
{job_title or "未知"}

目标公司：
{company or "未知"}

职位描述：
{description}

原始简历：
{resume_text}
""".strip()
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def normalize_greeting(text: str, limit: int = 200) -> str:
    cleaned = text.strip().strip("`").strip()
    for prefix in ("打招呼内容：", "正文：", "输出："):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix) :].strip()
    cleaned = cleaned.strip("“”\"'")
    if len(cleaned) <= limit:
        return cleaned
    sentence_endings = ["。", "！", "?", "？", "；", ";"]
    clipped = cleaned[:limit]
    last_sentence_end = max(clipped.rfind(mark) for mark in sentence_endings)
    if last_sentence_end >= 80:
        return clipped[: last_sentence_end + 1]
    return clipped.rstrip("，,、；;。") + "。"


def normalize_markdown_resume(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    return cleaned + "\n"


def _dump_analysis(jd_analysis: JDAnalysis) -> str:
    return json.dumps(jd_analysis.model_dump(), ensure_ascii=False, indent=2)


def _dump_history_examples(history_examples: list[dict]) -> str:
    if not history_examples:
        return "暂无。"
    lines = [
        "以下是本地 SQLite 中相似 JD 的历史生成记录，仅用于参考表达风格和避免重复泛化。"
        "不要机械复用历史话术；如果历史岗位主体与当前 JD 的 main_responsibilities 不一致，必须忽略。"
    ]
    for index, item in enumerate(history_examples[:5], start=1):
        analysis = item.get("jd_analysis")
        role_type = analysis.role_type if isinstance(analysis, JDAnalysis) else ""
        scenarios = "、".join(analysis.business_scenarios[:4]) if isinstance(analysis, JDAnalysis) else ""
        lines.append(
            f"{index}. 状态:{item.get('status', 'generated')} | 岗位:{item.get('job_title', '')} | "
            f"画像:{role_type} | 场景:{scenarios} | 历史话术:{item.get('greeting', '')}"
        )
    return "\n".join(lines)
