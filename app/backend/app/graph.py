from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, TypedDict

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.errors import GraphRecursionError
from langgraph.graph import END, StateGraph
from langgraph.store.base import BaseStore
from langgraph.types import interrupt

from .config import Settings
from .cost import CostTracker
from .events import EventBus
from .llm import LLMClient, LLMUnavailableError
from .skills import ALIASES, DEFAULT_REPORT, SKILLS, match_skill
from .tools.registry import ToolRegistry

THSCODE_RE = re.compile(r"\d{6}\.(?:SH|SZ|BJ)", re.IGNORECASE)
MEMORY_NAMESPACE = ("user_memories",)


class ResearchState(TypedDict, total=False):
    goal: str
    skill: str
    thread_id: str
    plan: list[dict[str, Any]]
    step_idx: int
    context_blob: str
    report: str
    memory_hits: list[str]
    compressed: bool
    stop_reason: str | None


@dataclass
class Runtime:
    settings: Settings
    registry: ToolRegistry
    llm: LLMClient
    store: BaseStore
    buses: dict[str, EventBus]
    costs: dict[str, CostTracker]
    pending_approvals: dict[str, dict[str, Any]]

    def bus(self, thread_id: str) -> EventBus:
        if thread_id not in self.buses:
            self.buses[thread_id] = EventBus(thread_id)
        return self.buses[thread_id]

    def cost(self, thread_id: str) -> CostTracker:
        if thread_id not in self.costs:
            self.costs[thread_id] = CostTracker(self.settings.token_budget)
        return self.costs[thread_id]


_runtime: Runtime | None = None


def set_runtime(rt: Runtime) -> None:
    global _runtime
    _runtime = rt


def get_runtime() -> Runtime:
    assert _runtime is not None, "runtime 未初始化"
    return _runtime


def extract_thscode(goal: str) -> str | None:
    if m := THSCODE_RE.search(goal):
        return m.group(0).upper()
    for alias, code in ALIASES.items():
        if alias in goal:
            return code
    return None


def _llm_invoke_with_retry(rt: Runtime, system: str, user: str, thread_id: str) -> str | None:
    """LLM 调用，失败重试一次；不可用/再失败返回 None（调用方走降级模板）。"""
    if not rt.llm.available:
        return None
    for attempt in range(2):
        try:
            resp = rt.llm.invoke(system, user)
            cost = rt.cost(thread_id)
            cost.record_llm(resp.tokens_in, resp.tokens_out)
            rt.bus(thread_id).emit("cost", cost.snapshot().model_dump())
            return resp.content
        except LLMUnavailableError:
            return None
        except Exception:
            if attempt == 1:
                rt.bus(thread_id).emit("warning", {
                    "kind": "degraded",
                    "message": "LLM 调用失败（已重试一次），改用内置模板生成文字",
                })
    return None


async def supervisor(state: ResearchState) -> dict[str, Any]:
    rt = get_runtime()
    thread_id = state["thread_id"]
    goal = state["goal"]
    bus = rt.bus(thread_id)

    memory_hits: list[str] = []
    try:
        items = await rt.store.asearch(MEMORY_NAMESPACE, limit=5)
        thscode = extract_thscode(goal)
        for it in items:
            val = it.value or {}
            if thscode and thscode in json.dumps(val, ensure_ascii=False):
                memory_hits.append(str(val.get("summary", "")))
        if not memory_hits and any(k in goal for k in ("上次", "之前", "历史")):
            memory_hits = [str((it.value or {}).get("summary", "")) for it in items]
    except Exception:
        pass

    skill = state.get("skill") or match_skill(goal)
    return {"skill": skill, "memory_hits": memory_hits}


def _default_params(tool: str, thscode: str | None) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if thscode:
        params["thscode"] = thscode
    if tool in {"ifind_fin_indicator", "ifind_fin_statement"}:
        params["report"] = DEFAULT_REPORT
    if tool == "ifind_fin_statement":
        params["statement"] = "income"
    return params


async def planner(state: ResearchState) -> dict[str, Any]:
    rt = get_runtime()
    thread_id = state["thread_id"]
    bus = rt.bus(thread_id)
    card = SKILLS[state["skill"]]
    thscode = extract_thscode(state["goal"])

    steps = [
        {
            "id": f"s{i + 1}",
            "title": title,
            "tool": tool,
            "params": _default_params(tool, thscode),
            "status": "pending",
        }
        for i, (title, tool) in enumerate(card.plan_steps)
    ]

    # interrupt 恢复时节点整体重跑，已发过的事件不重复发
    if not any(e["type"] == "plan" for e in bus.events):
        bus.emit("plan", {"steps": [{k: s[k] for k in ("id", "title", "tool")} for s in steps]})
        bus.emit("interrupt", {"kind": "plan_approval", "plan": steps})

    decision = interrupt({"kind": "plan_approval", "plan": steps})
    if isinstance(decision, dict) and decision.get("action") == "edit" and decision.get("plan"):
        edited = []
        for i, s in enumerate(decision["plan"]):
            tool = s.get("tool")
            edited.append({
                "id": str(s.get("id") or f"s{i + 1}"),
                "title": str(s.get("title") or ""),
                "tool": tool,
                # 客户端编辑计划可能不带 params，按工具补默认参数
                "params": dict(s.get("params") or {}) or _default_params(tool, thscode),
                "status": "pending",
            })
        steps = edited
    return {"plan": steps, "step_idx": 0}


async def researcher(state: ResearchState) -> dict[str, Any]:
    rt = get_runtime()
    settings = rt.settings
    thread_id = state["thread_id"]
    bus = rt.bus(thread_id)
    cost = rt.cost(thread_id)

    if cost.over_budget:
        return {"stop_reason": "token_budget"}

    plan = [dict(s) for s in state["plan"]]
    idx = state.get("step_idx", 0)
    if idx >= len(plan):
        return {}
    step = plan[idx]
    step["status"] = "running"
    bus.emit("step_start", {"step_id": step["id"], "title": step["title"]})

    tool = step.get("tool")
    params = step.get("params") or {}
    step_status = "done"

    if not tool or not rt.registry.has(tool):
        step["status"] = "skipped"
        bus.emit("step_done", {"step_id": step["id"], "status": "skipped"})
        plan[idx] = step
        return {"plan": plan, "step_idx": idx + 1}

    call_id = f"{step['id']}-c1"
    bus.emit("tool_call_start", {"step_id": step["id"], "call_id": call_id, "tool": tool, "params": params})
    envelope, _latency = await rt.registry.call(tool, params, thread_id=thread_id, cost=cost)
    env = envelope.model_dump()

    if envelope.error is not None:
        result_status = "error"
        step_status = "failed"
    elif not envelope.data:
        result_status = "empty"
    else:
        result_status = "ok"
    if envelope.auth == "fixture":
        bus.emit("warning", {
            "kind": "degraded",
            "message": f"工具 {tool} 使用 fixture 回放数据（未配置真实数据源 Key）",
        })
    bus.emit("tool_call_result", {
        "step_id": step["id"], "call_id": call_id, "tool": tool,
        "status": result_status, "envelope": env,
    })
    bus.emit("cost", cost.snapshot().model_dump())

    step["results"] = [env]
    step["status"] = step_status
    bus.emit("step_done", {"step_id": step["id"], "status": step_status})
    plan[idx] = step

    # 双源冲突检测：指标表 vs 利润表的营业收入
    conflict = _detect_conflict(plan)
    if conflict:
        bus.emit("conflict", {"step_id": step["id"], **conflict})

    update: dict[str, Any] = {"plan": plan, "step_idx": idx + 1}
    blob = state.get("context_blob", "")
    if envelope.data is not None:
        chunk = json.dumps({"step": step["title"], "tool": tool, "envelope": env}, ensure_ascii=False)
        blob = f"{blob}\n{chunk}" if blob else chunk

    # 上下文压缩：超阈值时摘要压缩（每轮只压一次）
    if not state.get("compressed") and len(blob) > settings.compress_threshold_chars:
        before = len(blob)
        summary = _llm_invoke_with_retry(
            rt,
            "你是研究助理，将以下工具返回 JSON 压缩为要点摘要，保留所有数值字段。",
            blob,
            thread_id,
        )
        if summary is None:
            summary = blob[: settings.compress_threshold_chars // 2]
        blob = f"[已压缩摘要] {summary}"
        update["compressed"] = True
        bus.emit("compress", {"before_chars": before, "after_chars": len(blob)})
    update["context_blob"] = blob
    return update


def _detect_conflict(plan: list[dict[str, Any]]) -> dict[str, Any] | None:
    ind_value: float | None = None
    ind_asof: str | None = None
    stmt_value: float | None = None
    stmt_asof: str | None = None
    for step in plan:
        for env in step.get("results") or []:
            data = env.get("data") or {}
            if env.get("source") == "ifind" and "metrics" in data:
                for m in data["metrics"]:
                    if m.get("key") == "operating_income" and m.get("value") is not None:
                        ind_value = float(m["value"])
                        ind_asof = env.get("as_of")
            if env.get("source") == "ifind" and "current" in data:
                cur = data["current"] or {}
                if cur.get("operating_income") is not None:
                    stmt_value = float(cur["operating_income"])
                    stmt_asof = env.get("as_of")
    if ind_value is not None and stmt_value is not None and ind_value > 0:
        if abs(ind_value - stmt_value) / ind_value > 0.005:
            return {
                "field": "operating_income",
                "sources": [
                    {"source": "ifind_fin_indicator", "value": ind_value, "as_of": ind_asof},
                    {"source": "ifind_fin_statement", "value": stmt_value, "as_of": stmt_asof},
                ],
            }
    return None


def _find_envelopes(plan: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for step in plan:
        out.extend(step.get("results") or [])
    return out


def _metric(plan: list[dict[str, Any]], key: str) -> dict[str, Any] | None:
    for env in _find_envelopes(plan):
        data = env.get("data") or {}
        for m in data.get("metrics") or []:
            if m.get("key") == key:
                return m
    return None


def _fmt_yi(value: float | int | None) -> str:
    if value is None:
        return "未披露"
    return f"{value / 1e8:.2f}亿"


async def reporter(state: ResearchState) -> dict[str, Any]:
    rt = get_runtime()
    thread_id = state["thread_id"]
    bus = rt.bus(thread_id)
    cost = rt.cost(thread_id)
    if cost.over_budget:
        return {"stop_reason": "token_budget"}

    plan = state["plan"]
    skill = state["skill"]
    goal = state["goal"]
    markdown = _render_report(rt, state, plan)

    bus.emit("artifact_delta", {"artifact_id": "a1", "kind": "report", "delta": markdown})
    title = f"{SKILLS[skill].display_name}报告：{goal[:40]}"
    bus.emit("artifact_done", {"artifact_id": "a1", "kind": "report", "title": title, "markdown": markdown})

    thscode = extract_thscode(goal) or "unknown"
    summary = _memory_summary(plan, goal, thscode)
    key = f"{thscode}_{skill}"
    try:
        await rt.store.aput(MEMORY_NAMESPACE, key, {
            "summary": summary, "thread_id": thread_id, "goal": goal, "thscode": thscode,
        })
        bus.emit("memory_write", {"key": key, "summary": summary})
    except Exception:
        pass
    return {"report": markdown}


def _memory_summary(plan: list[dict[str, Any]], goal: str, thscode: str) -> str:
    oi = _metric(plan, "operating_income")
    np_ = _metric(plan, "parent_holder_net_profit")
    rd = _metric(plan, "rd_expense_ratio")
    parts = [f"研究目标：{goal}"]
    if oi:
        parts.append(f"营业总收入{_fmt_yi(oi.get('value'))}元（同比+{oi.get('yoy_pct')}%）")
    if np_:
        parts.append(f"归母净利{_fmt_yi(np_.get('value'))}元（同比+{np_.get('yoy_pct')}%）")
    if rd:
        parts.append(f"研发费用率{rd.get('value')}%（上年{rd.get('prior')}%）")
    return "；".join(parts)


def _evidence_rows(plan: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """从工具信封渲染证据清单——数字只来自 envelope，不经过 LLM。"""
    rows: list[dict[str, Any]] = []

    def add(metric: str, value: Any, unit: str | None, env: dict[str, Any], extra: str = "") -> None:
        if value is None:
            return
        rows.append({
            "metric": metric, "value": value, "unit": unit or env.get("unit") or "",
            "source": env.get("source"), "as_of": env.get("as_of"),
            "caliber": (env.get("caliber") or "") + extra, "auth": env.get("auth"),
        })

    for env in _find_envelopes(plan):
        data = env.get("data") or {}
        if snap := data.get("snapshot"):
            add("最新价", snap.get("last_price"), "元", env)
            add("涨跌幅", snap.get("price_change_ratio_pct"), "%", env)
        if val := data.get("valuation"):
            for k, label in (("pe_ttm", "PE(TTM)"), ("pb_mrq", "PB(MRQ)"), ("ps_ttm", "PS(TTM)")):
                add(label, val.get(k), "倍", env)
        for m in data.get("metrics") or []:
            if m.get("value") is None and m.get("yoy_pct") is None:
                continue
            label = m.get("label", m.get("key", ""))
            if m.get("value") is not None:
                shown: Any = m["value"]
                unit = m.get("unit")
                if unit == "元":
                    shown = round(m["value"] / 1e8, 4)
                    unit = "亿元"
                suffix = f"；同比 {m['yoy_pct']}%" if m.get("yoy_pct") is not None else ""
                if m.get("prior") is not None:
                    suffix += f"；上年同期 {m['prior']}{m.get('unit', '')}"
                add(label, shown, unit, env, suffix)
            elif m.get("yoy_pct") is not None:
                add(label, m["yoy_pct"], "%", env)
        if (cur := data.get("current")) and isinstance(cur, dict):
            for k, label in (
                ("main_business_income", "主营业务收入"), ("investment_income", "投资收益"),
                ("other_income", "其他收益"), ("asset_impairment_loss", "资产减值损失"),
            ):
                if cur.get(k) is not None:
                    add(f"{label}（利润表）", round(cur[k] / 1e8, 4), "亿元", env)
    return rows


def _render_report(rt: Runtime, state: ResearchState, plan: list[dict[str, Any]]) -> str:
    skill = state["skill"]
    rows = _evidence_rows(plan)
    used_fixture = any(r.get("auth") == "fixture" for r in rows)
    missing = [s for s in plan if s.get("status") == "failed"]

    conclusion = _render_conclusion(rt, state, plan, rows)

    lines: list[str] = []
    lines.append(f"# {SKILLS[skill].display_name}报告")
    lines.append("")
    lines.append(f"> 研究目标：{state['goal']}")
    if state.get("memory_hits"):
        lines.append(f"> 关联历史记忆：{' / '.join(state['memory_hits'])}")
    lines.append("")
    lines.append("## 结论")
    lines.append("")
    lines.append(conclusion)
    lines.append("")
    lines.append("## 证据清单")
    lines.append("")
    if rows:
        lines.append("| 指标 | 数值 | 单位 | 来源 | 时点 | 口径 |")
        lines.append("|---|---|---|---|---|---|")
        for r in rows:
            lines.append(
                f"| {r['metric']} | {r['value']} | {r['unit']} | {r['source']} "
                f"| {r['as_of'] or '—'} | {r['caliber']} |"
            )
    else:
        lines.append("（未取得任何工具数据，无法形成证据清单）")
    lines.append("")
    lines.append("## 待核实事项")
    lines.append("")
    for item in _verify_items(plan, rows, used_fixture, missing):
        lines.append(f"- {item}")
    lines.append("")
    lines.append("## 失效条件")
    lines.append("")
    for item in _invalidation_items(skill):
        lines.append(f"- {item}")
    lines.append("")
    lines.append("---")
    lines.append("*仅做事实研究，不构成投资建议。*")
    return "\n".join(lines)


def _render_conclusion(rt: Runtime, state: ResearchState, plan: list[dict[str, Any]], rows: list[dict[str, Any]]) -> str:
    thread_id = state["thread_id"]
    evidence_json = json.dumps(rows, ensure_ascii=False)
    prose = _llm_invoke_with_retry(
        rt,
        "你是投资研究助理。根据给定证据 JSON 撰写研究结论解读（200 字内）。"
        "禁止出现证据中不存在的数字；只做事实归纳，不做买卖建议、不做涨跌预测。",
        f"研究目标：{state['goal']}\n证据：{evidence_json}",
        thread_id,
    )
    if prose:
        return prose.strip()
    # 无 LLM：模板化结论，数字全部从证据渲染
    if state["skill"] == "thesis_check":
        oi = _metric(plan, "operating_income")
        np_ = _metric(plan, "parent_holder_net_profit")
        deduct = _metric(plan, "deducted_net_profit_yoy")
        main_ratio = _metric(plan, "main_business_income_ratio")
        if not any([oi, np_, deduct, main_ratio]):
            return "工具数据不足，无法验证命题；请检查数据源配置后重试。"
        supported = (
            main_ratio is not None and (main_ratio.get("value") or 0) >= 99
            and deduct is not None and np_ is not None
            and (deduct.get("value") or 0) >= (np_.get("yoy_pct") or 0)
        )
        parts = ["本期财报数据显示："]
        if oi:
            parts.append(f"营业总收入 {_fmt_yi(oi.get('value'))}元，同比 +{oi.get('yoy_pct')}%；")
        if np_:
            parts.append(f"归母净利润 {_fmt_yi(np_.get('value'))}元，同比 +{np_.get('yoy_pct')}%；")
        if deduct:
            parts.append(f"扣非归母净利润同比 +{deduct.get('value')}%；")
        if main_ratio:
            parts.append(f"主营业务收入占营业总收入比例 {main_ratio.get('value')}%。")
        if supported:
            parts.append("主营占比接近 100% 且扣非增速不低于归母增速，命题「盈利改善来自主营业务」获得本期财报数据支持（详见证据清单）。")
        else:
            parts.append("现有指标不足以支持命题「盈利改善全部来自主营业务」，需进一步核实非经常性损益与利润结构。")
        return "".join(parts)
    return "各步骤取数结果见证据清单；LLM 未配置，未生成解读文字。"


def _verify_items(plan: list[dict[str, Any]], rows: list[dict[str, Any]], used_fixture: bool, missing: list[dict[str, Any]]) -> list[str]:
    items: list[str] = []
    if used_fixture:
        items.append("本次数据为 fixture 回放样例（未配置真实数据源 Key），结论需以真实数据源复核")
    deduct = _metric(plan, "deducted_net_profit_yoy")
    if deduct and deduct.get("value") is not None:
        items.append("扣非归母净利润绝对额未取到（仅同比增速），需查半年报原文核对")
    impairment = _metric(plan, "asset_impairment_loss")
    if impairment and impairment.get("value"):
        items.append(f"资产减值损失 {_fmt_yi(impairment['value'])}元 的构成明细（存货/无形资产等）需查报表附注")
    for env in _find_envelopes(plan):
        anns = (env.get("data") or {}).get("announcements") or []
        for a in anns[:2]:
            items.append(f"核对公告原文：{a.get('title')}（{a.get('date')}）{a.get('pdf_url')}")
    for s in missing:
        items.append(f"步骤「{s.get('title')}」取数失败，相关结论待补数后复核")
    if not items:
        items.append("暂无")
    return items


def _invalidation_items(skill: str) -> list[str]:
    if skill == "thesis_check":
        return [
            "后续报告期主营业务收入占比显著低于本期水平",
            "扣非归母净利增速明显低于归母净利增速，或出现大额非经常性损益",
            "毛利率/净利率大幅回落，或新增大额资产减值",
            "研发费用率进一步大幅下降引发增长可持续性疑问",
        ]
    if skill == "earnings_review":
        return [
            "下一报告期营收/利润增速显著放缓",
            "减值损失扩大或毛利率持续下滑",
        ]
    return ["标的公告重大不利事项（减持、诉讼、业绩变脸）"]


async def stopped(state: ResearchState) -> dict[str, Any]:
    rt = get_runtime()
    reason = state.get("stop_reason") or "step_limit"
    rt.bus(state["thread_id"]).emit("stopped", {"reason": reason})
    return {}


def _route_after_researcher(state: ResearchState) -> str:
    if state.get("stop_reason"):
        return "stopped"
    if state.get("step_idx", 0) < len(state.get("plan", [])):
        return "researcher"
    return "reporter"


def _route_after_reporter(state: ResearchState) -> str:
    if state.get("stop_reason"):
        return "stopped"
    return END


def build_graph(checkpointer: BaseCheckpointSaver[Any], store: BaseStore) -> Any:
    builder = StateGraph(ResearchState)
    builder.add_node("supervisor", supervisor)
    builder.add_node("planner", planner)
    builder.add_node("researcher", researcher)
    builder.add_node("reporter", reporter)
    builder.add_node("stopped", stopped)
    builder.set_entry_point("supervisor")
    builder.add_edge("supervisor", "planner")
    builder.add_edge("planner", "researcher")
    builder.add_conditional_edges("researcher", _route_after_researcher, {
        "researcher": "researcher", "reporter": "reporter", "stopped": "stopped",
    })
    builder.add_conditional_edges("reporter", _route_after_reporter, {END: END, "stopped": "stopped"})
    builder.add_edge("stopped", END)
    return builder.compile(checkpointer=checkpointer, store=store)


__all__ = [
    "ResearchState", "Runtime", "build_graph", "set_runtime", "get_runtime",
    "extract_thscode", "GraphRecursionError",
]
