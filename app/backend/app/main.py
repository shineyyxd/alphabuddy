from __future__ import annotations

import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import aiosqlite
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.errors import GraphRecursionError
from langgraph.store.memory import InMemoryStore
from langgraph.types import Command
from sse_starlette.sse import EventSourceResponse

from .config import Settings, get_settings
from .cost import CostTracker
from .db import init_db
from .events import EventBus
from .graph import Runtime, build_graph, set_runtime
from .guard import check_goal
from .llm import LLMClient
from .models import (
    ApproveRequest, CreateThreadRequest, CreateThreadResponse, RunRequest,
)
from .tools.base import AuditLogger, now_iso
from .tools.registry import ToolRegistry

TERMINAL_EVENTS = {"done", "stopped"}


class AppState:
    settings: Settings
    runtime: Runtime
    graph: Any
    db_path: str


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    settings.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    await init_db(str(settings.sqlite_path))

    audit = AuditLogger(str(settings.sqlite_path))
    registry = ToolRegistry(settings, audit)
    llm = LLMClient(settings.llm_base_url, settings.llm_api_key, settings.llm_model)
    store = InMemoryStore()
    rt = Runtime(
        settings=settings, registry=registry, llm=llm, store=store,
        buses={}, costs={}, pending_approvals={},
    )
    set_runtime(rt)

    async with AsyncSqliteSaver.from_conn_string(str(settings.sqlite_path)) as checkpointer:
        graph = build_graph(checkpointer, store)
        app.state.app = AppState()
        app.state.app.settings = settings
        app.state.app.runtime = rt
        app.state.app.graph = graph
        app.state.app.db_path = str(settings.sqlite_path)
        yield


app = FastAPI(title="AlphaBuddy 后端", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _st() -> AppState:
    return app.state.app


async def _db_execute(sql: str, params: tuple = ()) -> None:
    async with aiosqlite.connect(_st().db_path) as db:
        await db.execute(sql, params)
        await db.commit()


async def _get_thread(thread_id: str) -> dict[str, Any] | None:
    async with aiosqlite.connect(_st().db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM threads WHERE thread_id=?", (thread_id,))
        row = await cur.fetchone()
    return dict(row) if row else None


def _visitor(request: Request) -> str:
    """匿名访客标识：X-Visitor-Id 头，缺省 anon（直连 API 不报错）。"""
    return request.headers.get("x-visitor-id") or "anon"


def _check_owner(thread: dict[str, Any], visitor_id: str) -> None:
    # visitor_id 为 NULL 的历史线程不归属任何人，需经 /api/threads/claim 认领
    if thread.get("visitor_id") != visitor_id:
        raise HTTPException(404, "thread 不存在")


async def _set_status(thread_id: str, status: str) -> None:
    await _db_execute(
        "UPDATE threads SET status=?, updated_at=? WHERE thread_id=?",
        (status, now_iso(), thread_id),
    )


def _graph_config(thread_id: str) -> dict[str, Any]:
    settings = _st().settings
    return {
        "configurable": {"thread_id": thread_id},
        # 每个计划步约占 1 个 super-step，叠加 supervisor/planner/reporter 冗余
        "recursion_limit": settings.max_steps * 3 + 20,
    }


async def _derive_status(thread_id: str, stored: str) -> str:
    if stored in {"done", "failed", "interrupted"}:
        return stored
    snap = await _st().graph.aget_state(_graph_config(thread_id))
    if snap and snap.next:
        return "awaiting_approval"
    if snap and snap.values.get("report"):
        return "done"
    if snap and snap.values.get("plan"):
        return "running"
    return stored


@app.post("/api/threads", response_model=CreateThreadResponse)
async def create_thread(req: CreateThreadRequest, request: Request) -> CreateThreadResponse:
    st = _st()
    visitor = _visitor(request)
    thread_id = uuid.uuid4().hex[:12]
    blocked, message = check_goal(req.goal)
    now = now_iso()
    await _db_execute(
        "INSERT INTO threads(thread_id, visitor_id, goal, skill, status, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?)",
        (thread_id, visitor, req.goal, req.skill, "failed" if blocked else "planning", now, now),
    )
    bus = st.runtime.bus(thread_id)
    if blocked:
        bus.emit("warning", {"kind": "guard", "message": message})
        bus.emit("done", {"status": "failed", "summary": "合规拦截：未进入研究计划"})
    return CreateThreadResponse(thread_id=thread_id)


@app.get("/api/threads")
async def list_threads(request: Request) -> dict[str, Any]:
    async with aiosqlite.connect(_st().db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM threads WHERE visitor_id=? ORDER BY created_at DESC",
            (_visitor(request),),
        )
        rows = await cur.fetchall()
    threads = []
    for r in rows:
        d = dict(r)
        d["status"] = await _derive_status(d["thread_id"], d["status"])
        threads.append(d)
    return {"threads": threads}


@app.post("/api/threads/claim")
async def claim_threads(request: Request) -> dict[str, Any]:
    """一次性认领：把 visitor_id IS NULL 的历史线程划归当前访客。"""
    visitor = _visitor(request)
    async with aiosqlite.connect(_st().db_path) as db:
        cur = await db.execute(
            "UPDATE threads SET visitor_id=? WHERE visitor_id IS NULL", (visitor,)
        )
        await db.commit()
        return {"ok": True, "claimed": cur.rowcount}


@app.get("/api/capabilities")
async def capabilities() -> dict[str, Any]:
    return _st().runtime.registry.capabilities()


@app.get("/api/threads/{thread_id}/audit")
async def audit(thread_id: str, request: Request) -> dict[str, Any]:
    thread = await _get_thread(thread_id)
    if not thread:
        raise HTTPException(404, "thread 不存在")
    _check_owner(thread, _visitor(request))
    logs = await _st().runtime.registry.audit.list_for_thread(thread_id)
    return {"thread_id": thread_id, "audit": logs}


@app.get("/api/threads/{thread_id}/state")
async def thread_state(thread_id: str, request: Request) -> dict[str, Any]:
    thread = await _get_thread(thread_id)
    if not thread:
        raise HTTPException(404, "thread 不存在")
    _check_owner(thread, _visitor(request))
    st = _st()
    snap = await st.graph.aget_state(_graph_config(thread_id))
    values: dict[str, Any] = snap.values if snap else {}
    status = await _derive_status(thread_id, thread["status"])
    bus = st.runtime.buses.get(thread_id) or EventBus(thread_id)
    report = values.get("report")
    artifacts = []
    if report:
        artifacts.append({
            "id": "a1", "kind": "report",
            "title": f"研究报告：{thread['goal'][:40]}", "markdown": report,
        })
    cost: CostTracker = st.runtime.costs.get(thread_id) or CostTracker(st.settings.token_budget)
    plan = values.get("plan") or []
    if not plan:
        # 审批中断时计划尚未写入图状态，从 interrupt 事件还原（刷新恢复用）
        for ev in reversed(bus.events):
            if ev["type"] == "interrupt":
                plan = ev["data"].get("plan") or []
                break
    return {
        "thread_id": thread_id,
        "goal": thread["goal"],
        "skill": values.get("skill") or thread["skill"],
        "status": status,
        "plan": plan,
        "events": bus.events,
        "artifacts": artifacts,
        "cost": cost.snapshot().model_dump(),
    }


@app.post("/api/threads/{thread_id}/approve")
async def approve(thread_id: str, req: ApproveRequest, request: Request) -> dict[str, Any]:
    thread = await _get_thread(thread_id)
    if not thread:
        raise HTTPException(404, "thread 不存在")
    _check_owner(thread, _visitor(request))
    if req.action == "edit":
        if not req.plan:
            raise HTTPException(422, "action=edit 时必须携带编辑后的 plan")
        _st().runtime.pending_approvals[thread_id] = {
            "action": "edit", "plan": [s.model_dump() for s in req.plan],
        }
    else:
        _st().runtime.pending_approvals[thread_id] = {"action": "approve"}
    return {"ok": True}


def _sse(event: dict[str, Any]) -> dict[str, str]:
    return {"event": event["type"], "data": json.dumps(event["data"], ensure_ascii=False)}


async def _execute_graph(thread_id: str, thread: dict[str, Any]) -> None:
    st = _st()
    rt = st.runtime
    bus = rt.bus(thread_id)
    config = _graph_config(thread_id)
    try:
        snap = await st.graph.aget_state(config)
        if snap and snap.next:
            decision = rt.pending_approvals.pop(thread_id)
            await st.graph.ainvoke(Command(resume=decision), config)
        else:
            await st.graph.ainvoke(
                {
                    "goal": thread["goal"], "skill": thread["skill"],
                    "thread_id": thread_id,
                    "visitor_id": thread.get("visitor_id") or "anon",
                },
                config,
            )
        snap = await st.graph.aget_state(config)
        if snap and snap.next:
            await _set_status(thread_id, "awaiting_approval")
        elif (snap.values or {}).get("stop_reason"):
            await _set_status(thread_id, "interrupted")
        else:
            await _set_status(thread_id, "done")
            bus.emit("done", {"status": "done", "summary": "研究完成，产物已生成"})
    except Exception as exc:
        if isinstance(exc, GraphRecursionError):
            bus.emit("stopped", {"reason": "step_limit"})
            await _set_status(thread_id, "interrupted")
        else:
            bus.emit("done", {"status": "failed", "summary": f"执行异常：{exc}"})
            await _set_status(thread_id, "failed")
    finally:
        bus.emit("_end", {})


@app.post("/api/threads/{thread_id}/run")
async def run_thread(thread_id: str, req: RunRequest, request: Request) -> EventSourceResponse:
    thread = await _get_thread(thread_id)
    if not thread:
        raise HTTPException(404, "thread 不存在")
    _check_owner(thread, _visitor(request))
    st = _st()
    rt = st.runtime
    bus = rt.bus(thread_id)

    stored = thread["status"]
    snap = await st.graph.aget_state(_graph_config(thread_id))
    interrupted = bool(snap and snap.next)
    finished = stored in {"done", "failed"} or (stored == "interrupted" and not interrupted)

    if finished or (interrupted and thread_id not in rt.pending_approvals):
        # 已结束 / 等待审批：只回放历史事件，不推进图
        async def replay() -> AsyncIterator[dict[str, str]]:
            for ev in bus.events:
                if ev["type"] != "_end":
                    yield _sse(ev)

        return EventSourceResponse(replay())

    await _set_status(thread_id, "running")

    async def event_stream() -> AsyncIterator[dict[str, str]]:
        start = len(bus.events)
        bus.emit("run_started", {"thread_id": thread_id, "skill": thread["skill"] or "auto"})
        task = asyncio.create_task(_execute_graph(thread_id, thread))
        try:
            async for ev in bus.subscribe(start=start):
                if ev["type"] == "_end":
                    return
                yield _sse(ev)
                if ev["type"] in TERMINAL_EVENTS:
                    return
        finally:
            if not task.done():
                task.cancel()
            else:
                _ = task.exception() if not task.cancelled() else None

    return EventSourceResponse(event_stream())
