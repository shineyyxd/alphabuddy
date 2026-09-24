from __future__ import annotations

import json
import re
from typing import Any

from ..models import ToolEnvelope
from .base import BaseAPIClient, err_envelope, validate_thscode

# iFinD MCP 实测（2026-09-24 tools/list）：全部为自然语言 query 风格工具。
# ifind_fin_indicator / ifind_fin_statement → get_stock_financials
# ifind_announcement → get_stock_events
_TOOL_FINANCIALS = "get_stock_financials"
_TOOL_EVENTS = "get_stock_events"

_PERIOD_CN = {"1": "一季报", "2": "半年报", "3": "三季报", "4": "年报"}
_PERIOD_MD = {"1": "0331", "2": "0630", "3": "0930", "4": "1231"}

# 表头（去掉单位后缀后）→ (标准字段 key, 单位类别)。顺序敏感：先长后短。
_COL_RULES: list[tuple[str, str, str]] = [
    ("归属母公司股东的净利润-扣除非经常损益(同比增长率", "deducted_net_profit_yoy", "pct"),
    ("扣除非经常性损益后的归属母公司股东净利润", "deducted_net_profit", "yuan"),
    ("归属母公司股东的净利润(同比增长率", "parent_holder_net_profit_yoy", "pct"),
    ("归属于母公司所有者的净利润", "parent_holder_net_profit", "yuan"),
    ("营业总收入(同比增长率", "operating_income_yoy", "pct"),
    ("营业收入-主营业务", "main_business_income", "yuan"),
    ("营业总收入", "operating_income", "yuan"),
    ("销售净利率", "net_margin", "pct"),
    ("销售毛利率", "gross_margin", "pct"),
    ("研发费用／营业总收入", "rd_expense_ratio", "pct"),
    ("研发费用(同比增长率", "_skip", "pct"),
    ("研发费用", "research_and_development_expenses", "yuan"),
    ("投资收益", "investment_income", "yuan"),
    ("其他收益", "other_income", "yuan"),
    ("资产减值损失", "asset_impairment_loss", "yuan"),
    ("营业成本", "operating_costs", "yuan"),
    ("营业利润", "operating_profit", "yuan"),
    ("净利润(同比增长率", "_skip", "pct"),
    ("净利润", "net_profit", "yuan"),
    ("营业收入(同比增长率", "_skip", "pct"),
    ("营业收入", "operating_income_alt", "yuan"),
]

_UNIT_SUFFIX_RE = re.compile(r"（单位：[^）]*）")
_VALUE_RE = re.compile(r"^(-?[\d.]+)(亿|万)?$")
_DATE_RE = re.compile(r"(20\d{2})[-/]?(\d{2})[-/]?(\d{2})")


def _parse_mcp_payload(body: str, content_type: str) -> dict[str, Any]:
    """streamable-http 可能返回 application/json 或 text/event-stream。"""
    if "text/event-stream" in content_type:
        for line in body.splitlines():
            if line.startswith("data:"):
                return json.loads(line[5:].strip())
        raise RuntimeError("SSE 响应中没有 data 帧")
    return json.loads(body)


def extract_tool_json(rpc_resp: dict[str, Any]) -> dict[str, Any]:
    """从 tools/call 的 JSON-RPC 响应中取出工具文本负载并解析为 JSON。"""
    result = rpc_resp.get("result") or {}
    if result.get("isError"):
        content = result.get("content") or []
        text = content[0].get("text", "") if content else ""
        raise RuntimeError(f"MCP 工具返回错误: {text[:200]}")
    content = result.get("content") or []
    for part in content:
        if part.get("type") == "text":
            return json.loads(part["text"])
    structured = result.get("structuredContent")
    if isinstance(structured, dict):
        return structured
    raise RuntimeError("MCP 工具响应中没有可用的文本内容")


def _norm(raw: dict[str, Any]) -> dict[str, Any]:
    # 真实路径 fetch() 已提取文本负载；fixture 回放的是完整 JSON-RPC 响应，需同样提取
    if "result" in raw and isinstance(raw.get("result"), dict):
        return extract_tool_json(raw)
    return raw


def _period_names(report: str) -> tuple[str, str, str, str]:
    """report 如 '2026-2' → (当前期中文名, 上年同期中文名, 当前期日期 20260630, 上年同期日期)。"""
    year, _, period = report.partition("-")
    cn = _PERIOD_CN.get(period, "年报")
    md = _PERIOD_MD.get(period, "1231")
    return (
        f"{year}年{cn}", f"{int(year) - 1}年{cn}",
        f"{year}{md}", f"{int(year) - 1}{md}",
    )


def _strip_unit(header: str) -> str:
    return _UNIT_SUFFIX_RE.sub("", header).strip()


def _parse_cell(cell: str, kind: str) -> float | None:
    cell = cell.strip()
    m = _VALUE_RE.match(cell)
    if not m:
        return None
    v = float(m.group(1))
    if kind == "yuan":
        if m.group(2) == "亿":
            v *= 1e8
        elif m.group(2) == "万":
            v *= 1e4
    return v


def parse_answer_table(answer: str) -> list[dict[str, Any]]:
    """把 iFinD answer 的 markdown 表格解析为 [{日期, 证券代码, key: value}]，跳过单季度列。"""
    lines = [ln for ln in answer.splitlines() if ln.strip().startswith("|")]
    if len(lines) < 3:
        return []
    headers = [c.strip() for c in lines[0].strip().strip("|").split("|")]
    col_map: list[tuple[str, str] | None] = []
    for h in headers:
        name = _strip_unit(h)
        if name.startswith("单季度") or name.startswith("单季度-"):
            col_map.append(None)
            continue
        hit = next(((k, kind) for pat, k, kind in _COL_RULES if name.startswith(pat)), None)
        col_map.append(hit)
    rows: list[dict[str, Any]] = []
    for ln in lines[2:]:
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if len(cells) != len(headers):
            continue
        row: dict[str, Any] = {}
        for cell, mapped, raw_h in zip(cells, col_map, headers):
            col = _strip_unit(raw_h) if raw_h else ""
            if col == "日期":
                row["日期"] = cell
            elif col == "证券代码":
                row["证券代码"] = cell
            elif mapped:
                key, kind = mapped
                if key != "_skip" and key not in row:
                    v = _parse_cell(cell, kind)
                    if v is not None:
                        row[key] = v
        if row.get("日期"):
            rows.append(row)
    return rows


def _validate_symbol(rows: list[dict[str, Any]], thscode: str) -> None:
    """iFinD 自然语言引擎会把不存在的代码模糊匹配到相近真实标的——必须显式拦截。"""
    codes = {str(r.get("证券代码", "")).upper() for r in rows if r.get("证券代码")}
    if codes and thscode.upper() not in codes:
        raise RuntimeError(
            f"iFinD 返回的证券代码 {sorted(codes)} 与请求 {thscode} 不一致"
            "（疑似模糊匹配），按标的不存在处理"
        )


def _row_for(rows: list[dict[str, Any]], date: str) -> dict[str, Any]:
    for r in rows:
        if str(r.get("日期")) == date:
            return r
    return {}


def _real_answer(payload: dict[str, Any]) -> str:
    if payload.get("code") not in (None, 0, 1):
        raise RuntimeError(f"iFinD 业务错误: {payload.get('msg')} {payload.get('subMsg') or ''}".strip())
    data = payload.get("data")
    if isinstance(data, dict):
        return str(data.get("answer") or "")
    return ""


def _metric(key: str, label: str, value: Any, unit: str,
            yoy: float | None = None, prior: float | None = None) -> dict[str, Any]:
    m: dict[str, Any] = {"key": key, "label": label, "value": value, "unit": unit}
    if yoy is not None:
        m["yoy_pct"] = round(yoy, 4)
    if prior is not None:
        m["prior"] = round(prior, 4)
    return m


def normalize_indicator(payload: dict[str, Any], report: str) -> dict[str, Any]:
    if "metrics" in payload:  # fixture 形状，直接透传
        return payload
    answer = _real_answer(payload)
    _cur_cn, _prior_cn, cur_date, prior_date = _period_names(report)
    rows = parse_answer_table(answer)
    _validate_symbol(rows, payload.get("_thscode", ""))
    cur = _row_for(rows, cur_date)
    prior = _row_for(rows, prior_date)
    metrics: list[dict[str, Any]] = []
    if cur:
        oi, oi_yoy = cur.get("operating_income"), cur.get("operating_income_yoy")
        np_, np_yoy = cur.get("parent_holder_net_profit"), cur.get("parent_holder_net_profit_yoy")
        dnp, dnp_yoy = cur.get("deducted_net_profit"), cur.get("deducted_net_profit_yoy")
        if oi is not None:
            metrics.append(_metric("operating_income", "营业总收入", oi, "元", oi_yoy, prior.get("operating_income")))
        if np_ is not None:
            metrics.append(_metric("parent_holder_net_profit", "归母净利润", np_, "元", np_yoy, prior.get("parent_holder_net_profit")))
        if dnp is not None:
            metrics.append(_metric("deducted_net_profit", "扣非归母净利润", dnp, "元", dnp_yoy))
        if dnp_yoy is not None:
            metrics.append(_metric("deducted_net_profit_yoy", "扣非归母净利润同比", round(dnp_yoy, 4), "%"))
        main = cur.get("main_business_income")
        if main is not None and oi:
            metrics.append(_metric("main_business_income_ratio", "主营业务收入占营业总收入比例",
                                   round(main / oi * 100, 4), "%"))
        for key, label in (("net_margin", "净利率"), ("gross_margin", "毛利率"), ("rd_expense_ratio", "研发费用率")):
            if cur.get(key) is not None:
                metrics.append(_metric(key, label, round(cur[key], 4), "%", prior=prior.get(key)))
        for key, label in (("investment_income", "投资收益"), ("other_income", "其他收益"),
                           ("asset_impairment_loss", "资产减值损失")):
            if cur.get(key) is not None:
                metrics.append(_metric(key, label, cur[key], "元"))
    return {
        "metrics": metrics,
        "raw_answer": answer[:2000],
        "period_row": cur_date,
        "source_note": "iFinD get_stock_financials 真实返回解析",
    }


_STATEMENT_KEYS = (
    "operating_income", "main_business_income", "operating_costs",
    "research_and_development_expenses", "investment_income", "other_income",
    "asset_impairment_loss", "operating_profit", "net_profit", "parent_holder_net_profit",
)


def normalize_statement(payload: dict[str, Any], report: str) -> dict[str, Any]:
    if "current" in payload:  # fixture 形状
        return payload
    answer = _real_answer(payload)
    _c, _p, cur_date, prior_date = _period_names(report)
    rows = parse_answer_table(answer)
    _validate_symbol(rows, payload.get("_thscode", ""))

    def pick(date: str) -> dict[str, Any]:
        row = _row_for(rows, date)
        out: dict[str, Any] = {}
        if row:
            m = _DATE_RE.match(date)
            out["period_end"] = f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else date
            for k in _STATEMENT_KEYS:
                if row.get(k) is not None:
                    out[k] = row[k]
        return out

    return {
        "current": pick(cur_date),
        "prior_year_same_period": pick(prior_date),
        "raw_answer": answer[:2000],
        "source_note": "iFinD get_stock_financials 真实返回解析",
    }


def normalize_events(payload: dict[str, Any]) -> dict[str, Any]:
    if "announcements" in payload:  # fixture 形状
        return payload
    answer = _real_answer(payload)
    lines = [ln for ln in answer.splitlines() if ln.strip().startswith("|")]
    events: list[dict[str, Any]] = []
    if len(lines) >= 3:
        headers = [_strip_unit(c) for c in lines[0].strip().strip("|").split("|")]
        for ln in lines[2:]:
            cells = [c.strip() for c in ln.strip().strip("|").split("|")]
            if len(cells) == len(headers):
                events.append(dict(zip(headers, cells)))
        codes = {str(e.get("证券代码", "")).upper() for e in events if e.get("证券代码")}
        want = (payload.get("_thscode") or "").upper()
        if codes and want and want not in codes:
            raise RuntimeError(
                f"iFinD 返回的证券代码 {sorted(codes)} 与请求 {want} 不一致（疑似模糊匹配），按标的不存在处理"
            )
    as_of = None
    if m := _DATE_RE.search(answer):
        as_of = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return {
        "events": events,
        "raw_answer": answer[:1500],
        "as_of_guess": as_of,
        "source_note": "iFinD get_stock_events 真实返回（披露事件日期，无公告全文列表）",
    }


class IFinDMCPClient(BaseAPIClient):
    """iFinD streamable-http MCP：Bearer token 鉴权，JSON-RPC initialize/tools-list/tools-call。"""

    source = "ifind"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._session_id: str | None = None
        self._tool_names: list[str] | None = None

    @property
    def has_key(self) -> bool:
        return bool(self.settings.ifind_auth_token)

    @property
    def timeout_seconds(self) -> float:
        # iFinD 自然语言查询实测 6–9s，10s 上限过紧，单独放宽
        return self.settings.ifind_tool_timeout_seconds

    async def _rpc(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        import httpx

        headers = {
            "Authorization": f"Bearer {self.settings.ifind_auth_token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
        timeout = self.timeout_seconds
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(self.settings.ifind_mcp_url, json=payload, headers=headers)
            resp.raise_for_status()
            if sid := resp.headers.get("mcp-session-id"):
                self._session_id = sid
            body = _parse_mcp_payload(resp.text, resp.headers.get("content-type", ""))
        if "error" in body:
            raise RuntimeError(f"MCP RPC 错误: {body['error']}")
        return body

    async def _ensure_initialized(self) -> None:
        if self._session_id is None:
            await self._rpc("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "xbuddy", "version": "0.1.0"},
            })
            try:
                await self._rpc("notifications/initialized")
            except Exception:
                pass

    async def _call_tool(self, tool_name: str, query: str, thscode: str = "") -> dict[str, Any]:
        await self._ensure_initialized()
        resp = await self._rpc("tools/call", {"name": tool_name, "arguments": {"query": query}})
        payload = extract_tool_json(resp)
        payload["_thscode"] = thscode
        return payload

    async def fin_indicator(self, thscode: str, report: str) -> ToolEnvelope:
        if msg := validate_thscode(thscode):
            return err_envelope(source=self.source, kind="bad_params", message=msg, auth=self._auth_hint())
        cur_cn, prior_cn, _cd, _pd = _period_names(report)
        caliber = f"iFinD 财务指标（{cur_cn}，含同比与上年同期对照），报告期 {report}"
        query = (
            f"{thscode} {cur_cn}与{prior_cn} 营业总收入、主营业务收入、归母净利润、"
            "扣非归母净利润、净利率、毛利率、研发费用率、投资收益、其他收益、资产减值损失，"
            "及营业总收入/归母净利润/扣非归母净利润同比增速"
        )

        async def fetch() -> dict[str, Any]:
            return await self._call_tool(_TOOL_FINANCIALS, query, thscode)

        return await self._call(
            tool="ifind_fin_indicator", fixture_key=f"{thscode}_{report}", fetcher=fetch,
            normalize=lambda raw: normalize_indicator(_norm(raw), report),
            as_of_hint=report, unit="%", caliber=caliber,
        )

    async def fin_statement(self, thscode: str, report: str, statement: str = "income") -> ToolEnvelope:
        if msg := validate_thscode(thscode):
            return err_envelope(source=self.source, kind="bad_params", message=msg, auth=self._auth_hint())
        cur_cn, prior_cn, _cd, _pd = _period_names(report)
        caliber = f"iFinD 合并利润表（{cur_cn}，含上年同期对照），报告期 {report}"
        query = (
            f"{thscode} {cur_cn}与{prior_cn} 利润表 营业总收入、主营业务收入、营业成本、"
            "研发费用、投资收益、其他收益、资产减值损失、营业利润、净利润、归母净利润"
        )

        async def fetch() -> dict[str, Any]:
            return await self._call_tool(_TOOL_FINANCIALS, query, thscode)

        return await self._call(
            tool="ifind_fin_statement", fixture_key=f"{thscode}_{report}_{statement}",
            fetcher=fetch, normalize=lambda raw: normalize_statement(_norm(raw), report),
            as_of_hint=report, unit="元", caliber=caliber,
        )

    async def announcement(self, thscode: str, limit: int = 5) -> ToolEnvelope:
        if msg := validate_thscode(thscode):
            return err_envelope(source=self.source, kind="bad_params", message=msg, auth=self._auth_hint())

        async def fetch() -> dict[str, Any]:
            return await self._call_tool(
                _TOOL_EVENTS, f"{thscode} 定期报告预计与实际披露日期、业绩预告等公开披露事件", thscode,
            )

        def norm(raw: dict[str, Any]) -> dict[str, Any]:
            return normalize_events(_norm(raw))

        envelope = await self._call(
            tool="ifind_announcement", fixture_key=thscode, fetcher=fetch,
            normalize=norm, unit="条", caliber="iFinD 公开披露事件（定期报告披露日期等）",
        )
        # 真实返回中能抽出披露日期时提升到信封 as_of（公告原文列表仅 fixture 提供）
        if envelope.error is None and not envelope.as_of and envelope.data:
            envelope.as_of = envelope.data.get("as_of_guess")
        return envelope

    def _auth_hint(self) -> str:
        if self.has_key:
            return "ok"
        return "fixture" if self.settings.allow_fixture_fallback else "missing_key"
