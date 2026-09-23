from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Skill = Literal["thesis_check", "earnings_review", "watchlist_brief"]
ThreadStatus = Literal[
    "planning", "awaiting_approval", "running", "interrupted", "done", "failed"
]
StepStatus = Literal["pending", "running", "done", "failed", "skipped"]
ToolStatus = Literal["ok", "empty", "error", "degraded"]
AuthStatus = Literal["ok", "missing_key", "fixture"]


class CreateThreadRequest(BaseModel):
    goal: str = Field(min_length=1)
    skill: Skill | None = None


class CreateThreadResponse(BaseModel):
    thread_id: str


class ThreadSummary(BaseModel):
    thread_id: str
    goal: str
    skill: Skill | None
    status: ThreadStatus
    created_at: str
    updated_at: str


class RunRequest(BaseModel):
    resume_token: str | None = None


class PlanStepIn(BaseModel):
    id: str
    title: str
    tool: str
    params: dict[str, Any] = Field(default_factory=dict)


class ApproveRequest(BaseModel):
    action: Literal["approve", "edit"]
    plan: list[PlanStepIn] | None = None


class ToolError(BaseModel):
    kind: str
    message: str


class ToolEnvelope(BaseModel):
    data: dict[str, Any] | None = None
    source: str
    as_of: str | None = None
    unit: str | None = None
    caliber: str | None = None
    fetched_at: str
    auth: AuthStatus
    error: ToolError | None = None


class CostInfo(BaseModel):
    tokens_in: int = 0
    tokens_out: int = 0
    llm_calls: int = 0
    tool_calls: int = 0
    elapsed_ms: int = 0
    budget_remaining: int = 0


class PlanStep(BaseModel):
    id: str
    title: str
    tool: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    status: StepStatus = "pending"
    results: list[dict[str, Any]] = Field(default_factory=list)


class Artifact(BaseModel):
    id: str
    kind: str
    title: str
    markdown: str
