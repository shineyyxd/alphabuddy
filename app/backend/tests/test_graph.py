import pytest
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.errors import GraphRecursionError
from langgraph.store.memory import InMemoryStore
from langgraph.types import Command

from app.config import get_settings
from app.cost import CostTracker
from app.db import init_db
from app.graph import Runtime, build_graph, set_runtime
from app.llm import LLMClient
from app.tools.base import AuditLogger
from app.tools.registry import ToolRegistry

GOAL = "验证寒武纪盈利改善来自主营业务"


@pytest.fixture()
async def graph_env(tmp_db):
    settings = get_settings()
    await init_db(tmp_db)
    registry = ToolRegistry(settings, AuditLogger(tmp_db))
    llm = LLMClient(settings.llm_base_url, "", settings.llm_model)
    store = InMemoryStore()
    rt = Runtime(
        settings=settings, registry=registry, llm=llm, store=store,
        buses={}, costs={}, pending_approvals={},
    )
    set_runtime(rt)
    async with AsyncSqliteSaver.from_conn_string(tmp_db) as cp:
        yield build_graph(cp, store), rt


def _cfg(thread_id: str, recursion_limit: int = 100) -> dict:
    return {"configurable": {"thread_id": thread_id}, "recursion_limit": recursion_limit}


def _types(rt, tid):
    return [e["type"] for e in rt.bus(tid).events]


async def test_plan_approval_interrupt_and_resume(graph_env):
    graph, rt = graph_env
    tid = "g1"
    out = await graph.ainvoke({"goal": GOAL, "skill": "thesis_check", "thread_id": tid}, _cfg(tid))
    assert "__interrupt__" in out
    snap = await graph.aget_state(_cfg(tid))
    assert snap.next  # 检查点已保存，等待审批

    events = _types(rt, tid)
    assert "plan" in events
    assert "interrupt" in events
    interrupt_ev = next(e for e in rt.bus(tid).events if e["type"] == "interrupt")
    assert interrupt_ev["data"]["kind"] == "plan_approval"
    assert len(interrupt_ev["data"]["plan"]) == 4
    # 计划步绑定了工具与标的
    assert interrupt_ev["data"]["plan"][1]["tool"] == "ifind_fin_indicator"
    assert interrupt_ev["data"]["plan"][1]["params"]["thscode"] == "688256.SH"

    out2 = await graph.ainvoke(Command(resume={"action": "approve"}), _cfg(tid))
    assert "__interrupt__" not in out2
    report = out2["report"]
    assert "## 结论" in report
    assert "## 证据清单" in report
    assert "## 待核实事项" in report
    assert "## 失效条件" in report
    assert "不构成投资建议" in report
    # 关键数值由后端从工具信封渲染
    assert "59.96" in report  # 营业总收入 59.96 亿元
    assert "108.13" in report
    assert "99.9995" in report

    events2 = _types(rt, tid)
    for t in ("step_start", "tool_call_start", "tool_call_result", "step_done",
              "artifact_delta", "artifact_done", "memory_write", "cost"):
        assert t in events2, t
    # 降级提示：fixture 回放
    warns = [e for e in rt.bus(tid).events if e["type"] == "warning"]
    assert any(w["data"]["kind"] == "degraded" for w in warns)

    # 长期记忆已写入，跨线程可检索（新会话问"上次研究的…"）
    items = await rt.store.asearch(("user_memories",), limit=5)
    assert items
    assert any("108.13" in str(it.value.get("summary", "")) for it in items)

    # 审计：4 个计划步各一次工具调用
    logs = await rt.registry.audit.list_for_thread(tid)
    assert len(logs) == 4


async def test_edit_plan_before_approve(graph_env):
    graph, rt = graph_env
    tid = "g2"
    await graph.ainvoke({"goal": GOAL, "skill": "thesis_check", "thread_id": tid}, _cfg(tid))
    edited_plan = [
        {"id": "s1", "title": "获取财务指标", "tool": "ifind_fin_indicator",
         "params": {"thscode": "688256.SH", "report": "2026-2"}},
        {"id": "s2", "title": "获取利润表", "tool": "ifind_fin_statement",
         "params": {"thscode": "688256.SH", "report": "2026-2", "statement": "income"}},
    ]
    out = await graph.ainvoke(
        Command(resume={"action": "edit", "plan": edited_plan}), _cfg(tid)
    )
    assert len(out["plan"]) == 2
    assert all(s["status"] == "done" for s in out["plan"])
    assert "证据清单" in out["report"]


async def test_failed_step_does_not_block_others(graph_env, monkeypatch):
    monkeypatch.setenv("ALLOW_FIXTURE_FALLBACK", "false")
    graph, rt = graph_env
    tid = "g3"
    # fixture 关闭：所有 ifind/fuyao 工具 missing_key，步骤标 failed 但流程走完
    rt.settings = get_settings()
    rt.registry = ToolRegistry(rt.settings, rt.registry.audit)
    await graph.ainvoke({"goal": GOAL, "skill": "thesis_check", "thread_id": tid}, _cfg(tid))
    out = await graph.ainvoke(Command(resume={"action": "approve"}), _cfg(tid))
    assert out["report"]
    assert any(s["status"] == "failed" for s in out["plan"])
    results = [
        e for e in rt.bus(tid).events
        if e["type"] == "tool_call_result" and e["data"]["status"] == "error"
    ]
    assert results
    assert results[0]["data"]["envelope"]["error"]["kind"] == "missing_key"


async def test_step_limit_recursion(graph_env):
    graph, rt = graph_env
    tid = "g4"
    await graph.ainvoke({"goal": GOAL, "skill": "thesis_check", "thread_id": tid}, _cfg(tid))
    # 恢复后 researcher 循环 4 步 + reporter，远超 3 的步数上限
    with pytest.raises(GraphRecursionError):
        await graph.ainvoke(
            Command(resume={"action": "approve"}), _cfg(tid, recursion_limit=3)
        )


async def test_token_budget_stop(graph_env):
    graph, rt = graph_env
    tid = "g5"
    await graph.ainvoke({"goal": GOAL, "skill": "thesis_check", "thread_id": tid}, _cfg(tid))
    # 预算耗尽 → researcher 立即触发停止规则
    rt.costs[tid] = CostTracker(token_budget=0)
    await graph.ainvoke(Command(resume={"action": "approve"}), _cfg(tid))
    stopped = [e for e in rt.bus(tid).events if e["type"] == "stopped"]
    assert stopped
    assert stopped[0]["data"]["reason"] == "token_budget"


async def test_context_compression_event(graph_env, monkeypatch):
    monkeypatch.setenv("COMPRESS_THRESHOLD_CHARS", "100")
    graph, rt = graph_env
    tid = "g6"
    rt.settings = get_settings()
    await graph.ainvoke({"goal": GOAL, "skill": "thesis_check", "thread_id": tid}, _cfg(tid))
    out = await graph.ainvoke(Command(resume={"action": "approve"}), _cfg(tid))
    assert out.get("compressed") is True
    comp = [e for e in rt.bus(tid).events if e["type"] == "compress"]
    assert comp
    assert comp[0]["data"]["before_chars"] > comp[0]["data"]["after_chars"] >= 0
