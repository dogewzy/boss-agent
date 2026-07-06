from typing import Literal

from pydantic import BaseModel, Field


ResumeProfile = Literal["auto", "agent", "fde"]


class JDAnalysis(BaseModel):
    role_type: str = Field(default="")
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


class HealthResponse(BaseModel):
    ok: bool
    deepseek_key_loaded: bool
    agent_resume_loaded: bool
    fde_resume_loaded: bool
