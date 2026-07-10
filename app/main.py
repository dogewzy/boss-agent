from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from httpx import HTTPStatusError

from app.history_store import default_history_store
from app.jd_analysis import build_jd_analysis_messages, parse_jd_analysis
from app.llm import DeepSeekClient, DeepSeekConfigError, deepseek_key_loaded
from app.prompt import (
    build_messages,
    build_resume_polish_messages,
    normalize_greeting,
    normalize_markdown_resume,
)
from app.resume_store import ResumeStore
from app.schemas import (
    GreetingRequest,
    GreetingResponse,
    HistoryMarkRequest,
    HistoryMarkResponse,
    HealthResponse,
    ResumePolishRequest,
    ResumePolishResponse,
)

app = FastAPI(title="BOSS Agent Greeting Assistant")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

resume_store = ResumeStore()
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "generated_resumes"
history_store = default_history_store(PROJECT_ROOT)


@app.get("/api/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    agent_loaded, fde_loaded = resume_store.status()
    return HealthResponse(
        ok=True,
        deepseek_key_loaded=deepseek_key_loaded(),
        agent_resume_loaded=agent_loaded,
        fde_resume_loaded=fde_loaded,
    )


@app.post("/api/greeting", response_model=GreetingResponse)
async def create_greeting(payload: GreetingRequest) -> GreetingResponse:
    try:
        resumes = resume_store.load()
        client = DeepSeekClient.from_env()
    except (FileNotFoundError, DeepSeekConfigError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    profile = resume_store.select_profile(
        payload.resume_profile,
        job_title=payload.job_title,
        description=payload.description,
    )
    jd_analysis = await _analyze_jd(
        client,
        job_title=payload.job_title,
        company=payload.company,
        description=payload.description,
    )
    resume_text = resumes.agent if profile == "agent" else resumes.fde
    history_examples = history_store.similar_greetings(jd_analysis)

    messages = build_messages(
        resume_text=resume_text,
        job_title=payload.job_title,
        company=payload.company,
        description=payload.description,
        jd_analysis=jd_analysis,
        history_examples=history_examples,
    )
    try:
        raw_text = await client.chat(messages)
    except HTTPStatusError as exc:
        detail = exc.response.text[:500]
        raise HTTPException(
            status_code=502,
            detail=f"DeepSeek request failed: {exc.response.status_code} {detail}",
        ) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"DeepSeek request failed: {exc}") from exc

    greeting = normalize_greeting(raw_text)
    history_id = None
    try:
        history_id = history_store.append_greeting(
            job_title=payload.job_title,
            company=payload.company,
            description=payload.description,
            resume_profile=profile,
            model=client.model,
            jd_analysis=jd_analysis,
            greeting=greeting,
        )
    except Exception:
        history_id = None
    return GreetingResponse(
        greeting=greeting,
        resume_profile=profile,
        model=client.model,
        jd_analysis=jd_analysis,
        history_id=history_id,
    )


@app.post("/api/resume-polish", response_model=ResumePolishResponse)
async def polish_resume(payload: ResumePolishRequest) -> ResumePolishResponse:
    try:
        resumes = resume_store.load()
        client = DeepSeekClient.from_env()
    except (FileNotFoundError, DeepSeekConfigError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    profile = resume_store.select_profile(
        payload.resume_profile,
        job_title=payload.job_title,
        description=payload.description,
    )
    jd_analysis = await _analyze_jd(
        client,
        job_title=payload.job_title,
        company=payload.company,
        description=payload.description,
    )
    resume_text = resumes.agent if profile == "agent" else resumes.fde
    messages = build_resume_polish_messages(
        resume_text=resume_text,
        job_title=payload.job_title,
        company=payload.company,
        description=payload.description,
        jd_analysis=jd_analysis,
    )

    try:
        raw_text = await client.chat(messages, max_tokens=6500, temperature=0.25)
    except HTTPStatusError as exc:
        detail = exc.response.text[:500]
        raise HTTPException(
            status_code=502,
            detail=f"DeepSeek request failed: {exc.response.status_code} {detail}",
        ) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"DeepSeek request failed: {exc}") from exc

    markdown = normalize_markdown_resume(raw_text)
    output_path = _write_resume_file(
        markdown,
        job_title=payload.job_title,
        company=payload.company,
        profile=profile,
    )
    history_id = None
    try:
        history_id = history_store.append_resume_polish(
            job_title=payload.job_title,
            company=payload.company,
            description=payload.description,
            resume_profile=profile,
            model=client.model,
            jd_analysis=jd_analysis,
            file_path=str(output_path),
        )
    except Exception:
        history_id = None
    return ResumePolishResponse(
        markdown=markdown,
        file_path=str(output_path),
        resume_profile=profile,
        model=client.model,
        jd_analysis=jd_analysis,
        history_id=history_id,
    )


@app.post("/api/history/{history_id}/mark", response_model=HistoryMarkResponse)
async def mark_history(history_id: str, payload: HistoryMarkRequest) -> HistoryMarkResponse:
    ok = history_store.mark(history_id, payload.status, payload.feedback)
    if not ok:
        raise HTTPException(status_code=404, detail="History record not found")
    return HistoryMarkResponse(ok=True)


async def _analyze_jd(
    client: DeepSeekClient,
    *,
    job_title: str,
    company: str,
    description: str,
):
    messages = build_jd_analysis_messages(
        job_title=job_title,
        company=company,
        description=description,
    )
    try:
        raw_text = await client.chat(messages, max_tokens=900, temperature=0.1)
    except Exception:
        return parse_jd_analysis("", description, job_title)
    return parse_jd_analysis(raw_text, description, job_title)


def _write_resume_file(
    markdown: str,
    *,
    job_title: str,
    company: str,
    profile: str,
) -> Path:
    output_dir = Path(os.getenv("BOSS_AGENT_OUTPUT_DIR", str(DEFAULT_OUTPUT_DIR)))
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    company_part = _slugify(company or "unknown-company")
    title_part = _slugify(job_title or "unknown-job")
    filename = f"{timestamp}-{profile}-{company_part}-{title_part}.md"
    output_path = output_dir / filename
    output_path.write_text(markdown, encoding="utf-8")
    return output_path


def _slugify(value: str, max_length: int = 48) -> str:
    normalized = re.sub(r"\s+", "-", value.strip())
    normalized = re.sub(r"[^\w\u4e00-\u9fff.-]+", "-", normalized)
    normalized = normalized.strip("-_.")
    return (normalized or "untitled")[:max_length]
