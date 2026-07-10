from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from app.schemas import ResumeProfile


SelectedProfile = Literal["agent", "fde"]

DEFAULT_AGENT_RESUME_PATHS = [
    Path("resumes/agent-resume.md"),
    Path("/Users/wangzhenyan/Downloads/王禛彦-Agent开发工程师-简历-AI技能栈强化版.md"),
]
DEFAULT_FDE_RESUME_PATHS = [
    Path("resumes/fde-resume.md"),
    Path("/Users/wangzhenyan/Downloads/王禛彦-FDE现场部署工程师-Agent项目技术负责人-简历.md"),
]


@dataclass(frozen=True)
class ResumeBundle:
    agent: str
    fde: str


class ResumeStore:
    def __init__(self) -> None:
        self.agent_path = self._resolve_resume_path(
            "BOSS_AGENT_RESUME_AGENT_PATH",
            DEFAULT_AGENT_RESUME_PATHS,
        )
        self.fde_path = self._resolve_resume_path(
            "BOSS_AGENT_RESUME_FDE_PATH",
            DEFAULT_FDE_RESUME_PATHS,
        )

    def load(self) -> ResumeBundle:
        return ResumeBundle(
            agent=self._read_resume(self.agent_path),
            fde=self._read_resume(self.fde_path),
        )

    def status(self) -> tuple[bool, bool]:
        return self.agent_path.exists(), self.fde_path.exists()

    def select_profile(
        self,
        requested: ResumeProfile,
        *,
        job_title: str,
        description: str,
    ) -> SelectedProfile:
        if requested in ("agent", "fde"):
            return requested

        text = f"{job_title}\n{description}".lower()
        fde_score = self._score(
            text,
            [
                "fde",
                "field",
                "现场",
                "部署",
                "交付",
                "客户",
                "实施",
                "售前",
                "解决方案",
                "项目负责人",
                "项目经理",
                "ai ready",
                "知识库",
                "企业应用落地",
            ],
        )
        agent_score = self._score(
            text,
            [
                "agent",
                "大模型",
                "llm",
                "langchain",
                "langgraph",
                "tool calling",
                "function calling",
                "rag",
                "prompt",
                "python",
                "后端",
                "工程化",
                "自动化",
            ],
        )
        return "fde" if fde_score > agent_score + 1 else "agent"

    @staticmethod
    def _score(text: str, keywords: list[str]) -> int:
        return sum(1 for keyword in keywords if keyword.lower() in text)

    @staticmethod
    def _read_resume(path: Path) -> str:
        if not path.exists():
            raise FileNotFoundError(f"Resume file not found: {path}")
        return path.read_text(encoding="utf-8").strip()

    @staticmethod
    def _resolve_resume_path(env_name: str, candidates: list[Path]) -> Path:
        env_value = os.getenv(env_name)
        if env_value:
            return Path(env_value)
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return candidates[0]
