from typing import Literal

from pydantic import BaseModel, Field


ResumeProfile = Literal["auto", "agent", "fde"]


class JDAnalysis(BaseModel):
    role_type: str = Field(default="")
    main_responsibilities: list[str] = Field(default_factory=list)
    required_skills: list[str] = Field(default_factory=list)
    business_scenarios: list[str] = Field(default_factory=list)
    core_capabilities: list[str] = Field(default_factory=list)
    engineering_requirements: list[str] = Field(default_factory=list)
    bonus_points: list[str] = Field(default_factory=list)
    communication_angle: str = Field(default="")
    avoid_points: list[str] = Field(default_factory=list)


class GreetingRequest(BaseModel):
    job_title: str = Field(default="", max_length=200)
    company: str = Field(default="", max_length=200)
    description: str = Field(..., min_length=20, max_length=12000)
    resume_profile: ResumeProfile = "auto"


class GreetingResponse(BaseModel):
    greeting: str
    resume_profile: Literal["agent", "fde"]
    model: str
    jd_analysis: JDAnalysis
    history_id: str | None = None


class ResumePolishRequest(BaseModel):
    job_title: str = Field(default="", max_length=200)
    company: str = Field(default="", max_length=200)
    description: str = Field(..., min_length=20, max_length=12000)
    resume_profile: ResumeProfile = "auto"


class ResumePolishResponse(BaseModel):
    markdown: str
    file_path: str
    resume_profile: Literal["agent", "fde"]
    model: str
    jd_analysis: JDAnalysis
    history_id: str | None = None


class HistoryMarkRequest(BaseModel):
    status: Literal["copied", "sent", "skipped"]
    feedback: str = Field(default="", max_length=1000)


class HistoryMarkResponse(BaseModel):
    ok: bool


class HealthResponse(BaseModel):
    ok: bool
    deepseek_key_loaded: bool
    agent_resume_loaded: bool
    fde_resume_loaded: bool
