from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from app.schemas import JDAnalysis


HistoryStatus = Literal["generated", "copied", "sent", "skipped"]


class HistoryStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def append_greeting(
        self,
        *,
        job_title: str,
        company: str,
        description: str,
        resume_profile: str,
        model: str,
        jd_analysis: JDAnalysis,
        greeting: str,
    ) -> str:
        record_id = self._new_id()
        self._execute(
            """
            INSERT INTO interactions (
                id, created_at, event_type, status, job_title, company, description,
                description_hash, resume_profile, model, jd_analysis_json, output_text
            )
            VALUES (?, ?, 'greeting', 'generated', ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record_id,
                self._now(),
                job_title,
                company,
                description,
                self._hash(description),
                resume_profile,
                model,
                self._dump_analysis(jd_analysis),
                greeting,
            ),
        )
        return record_id

    def append_resume_polish(
        self,
        *,
        job_title: str,
        company: str,
        description: str,
        resume_profile: str,
        model: str,
        jd_analysis: JDAnalysis,
        file_path: str,
    ) -> str:
        record_id = self._new_id()
        self._execute(
            """
            INSERT INTO interactions (
                id, created_at, event_type, status, job_title, company, description,
                description_hash, resume_profile, model, jd_analysis_json, output_file_path
            )
            VALUES (?, ?, 'resume_polish', 'generated', ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record_id,
                self._now(),
                job_title,
                company,
                description,
                self._hash(description),
                resume_profile,
                model,
                self._dump_analysis(jd_analysis),
                file_path,
            ),
        )
        return record_id

    def mark(self, record_id: str, status: HistoryStatus, feedback: str = "") -> bool:
        column = {
            "copied": "copied_at",
            "sent": "sent_at",
            "skipped": "updated_at",
            "generated": "updated_at",
        }[status]
        with self._connect() as conn:
            cursor = conn.execute(
                f"""
                UPDATE interactions
                SET status = ?, {column} = ?, feedback = COALESCE(NULLIF(?, ''), feedback)
                WHERE id = ?
                """,
                (status, self._now(), feedback, record_id),
            )
            return cursor.rowcount > 0

    def similar_greetings(self, jd_analysis: JDAnalysis, limit: int = 3) -> list[dict[str, Any]]:
        target_terms = self._analysis_terms(jd_analysis)
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, created_at, status, job_title, company, resume_profile,
                       jd_analysis_json, output_text
                FROM interactions
                WHERE event_type = 'greeting' AND output_text IS NOT NULL AND output_text != ''
                ORDER BY created_at DESC
                LIMIT 120
                """
            ).fetchall()

        scored: list[tuple[int, dict[str, Any]]] = []
        target_is_coding = self._is_coding_role(jd_analysis)
        for row in rows:
            analysis = self._load_analysis(row["jd_analysis_json"])
            if self._is_coding_role(analysis) and not target_is_coding:
                continue
            terms = self._analysis_terms(analysis)
            score = len(target_terms & terms)
            if row["status"] == "sent":
                score += 2
            elif row["status"] == "copied":
                score += 1
            if analysis.role_type and analysis.role_type == jd_analysis.role_type:
                score += 2
            if score < 5:
                continue
            scored.append(
                (
                    score,
                    {
                        "id": row["id"],
                        "created_at": row["created_at"],
                        "status": row["status"],
                        "job_title": row["job_title"],
                        "company": row["company"],
                        "resume_profile": row["resume_profile"],
                        "jd_analysis": analysis,
                        "greeting": row["output_text"],
                    },
                )
            )
        scored.sort(key=lambda item: item[0], reverse=True)
        return [item[1] for item in scored[:limit]]

    def _init_schema(self) -> None:
        self._execute(
            """
            CREATE TABLE IF NOT EXISTS interactions (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                updated_at TEXT,
                event_type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'generated',
                job_title TEXT,
                company TEXT,
                description TEXT NOT NULL,
                description_hash TEXT NOT NULL,
                resume_profile TEXT,
                model TEXT,
                jd_analysis_json TEXT,
                output_text TEXT,
                output_file_path TEXT,
                copied_at TEXT,
                sent_at TEXT,
                feedback TEXT
            )
            """
        )
        self._execute(
            "CREATE INDEX IF NOT EXISTS idx_interactions_type_created ON interactions(event_type, created_at)"
        )
        self._execute(
            "CREATE INDEX IF NOT EXISTS idx_interactions_description_hash ON interactions(description_hash)"
        )
        self._execute("CREATE INDEX IF NOT EXISTS idx_interactions_status ON interactions(status)")

    def _execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        with self._connect() as conn:
            conn.execute(sql, params)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 5000")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    @staticmethod
    def _new_id() -> str:
        return uuid.uuid4().hex

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _hash(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @staticmethod
    def _dump_analysis(jd_analysis: JDAnalysis) -> str:
        return json.dumps(jd_analysis.model_dump(), ensure_ascii=False)

    @staticmethod
    def _load_analysis(value: str | None) -> JDAnalysis:
        if not value:
            return JDAnalysis()
        try:
            return JDAnalysis.model_validate(json.loads(value))
        except Exception:
            return JDAnalysis()

    @staticmethod
    def _analysis_terms(jd_analysis: JDAnalysis) -> set[str]:
        values = [
            jd_analysis.role_type,
            jd_analysis.communication_angle,
            *jd_analysis.main_responsibilities,
            *jd_analysis.required_skills,
            *jd_analysis.business_scenarios,
            *jd_analysis.core_capabilities,
            *jd_analysis.engineering_requirements,
            *jd_analysis.bonus_points,
        ]
        terms: set[str] = set()
        for value in values:
            normalized = value.strip().lower()
            if normalized:
                terms.add(normalized)
            for part in normalized.replace("/", " ").replace("、", " ").split():
                if part:
                    terms.add(part)
        return terms

    @staticmethod
    def _is_coding_role(jd_analysis: JDAnalysis) -> bool:
        text = " ".join(
            [
                jd_analysis.role_type,
                *jd_analysis.main_responsibilities,
                *jd_analysis.business_scenarios,
            ]
        ).lower()
        return any(keyword in text for keyword in ["coding", "研发效能", "代码生成", "pr 自动化", "pr自动化"])


def default_history_store(project_root: Path) -> HistoryStore:
    db_path = Path(os.getenv("BOSS_AGENT_HISTORY_DB", str(project_root / "data" / "boss_agent.sqlite3")))
    return HistoryStore(db_path)
