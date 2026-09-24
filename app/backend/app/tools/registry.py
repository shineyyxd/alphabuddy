from __future__ import annotations

import time
from typing import Any, Awaitable, Callable

from ..config import Settings
from ..cost import CostTracker
from ..models import ToolEnvelope
from .base import AuditLogger, BaseAPIClient, FixtureStore, err_envelope
from .fuyao import FuyaoClient
from .ifind import IFinDMCPClient

ToolFn = Callable[..., Awaitable[ToolEnvelope]]

RETURNS = ["data", "source", "as_of", "unit", "caliber"]


class ToolRegistry:
    def __init__(self, settings: Settings, audit: AuditLogger) -> None:
        fixtures = FixtureStore(settings.fixture_dir)
        fuyao = FuyaoClient(settings, fixtures)
        ifind = IFinDMCPClient(settings, fixtures)
        self.clients: dict[str, BaseAPIClient] = {"fuyao": fuyao, "ifind": ifind}
        self.audit = audit
        self._specs: list[dict[str, Any]] = [
            {
                "name": "fuyao_quote_snapshot",
                "display_name": "行情快照（扶摇）",
                "description": "A 股行情快照：最新价、涨跌幅、开高低收、成交量额",
                "source": "fuyao",
                "params_schema": {
                    "type": "object",
                    "properties": {"thscode": {"type": "string", "description": "如 688256.SH"}},
                    "required": ["thscode"],
                },
                "fn": fuyao.quote_snapshot,
            },
            {
                "name": "fuyao_valuation",
                "display_name": "估值快照（扶摇）",
                "description": "PE(TTM/MRQ)、PB(MRQ)、PS(TTM)、PCF(TTM) 五指标估值快照",
                "source": "fuyao",
                "params_schema": {
                    "type": "object",
                    "properties": {"thscode": {"type": "string"}},
                    "required": ["thscode"],
                },
                "fn": fuyao.valuation,
            },
            {
                "name": "ifind_fin_indicator",
                "display_name": "财务指标（iFinD）",
                "description": "营收/归母/扣非归母同比，净利率、毛利率、研发费用率等，本期与上年同期",
                "source": "ifind",
                "params_schema": {
                    "type": "object",
                    "properties": {
                        "thscode": {"type": "string"},
                        "report": {"type": "string", "description": "如 2026-2（2=中报）"},
                    },
                    "required": ["thscode", "report"],
                },
                "fn": ifind.fin_indicator,
            },
            {
                "name": "ifind_fin_statement",
                "display_name": "财务报表（iFinD）",
                "description": "合并三大报表（利润表/资产负债表/现金流量表），含上年同期对照",
                "source": "ifind",
                "params_schema": {
                    "type": "object",
                    "properties": {
                        "thscode": {"type": "string"},
                        "report": {"type": "string"},
                        "statement": {"type": "string", "enum": ["income", "balance", "cashflow"], "default": "income"},
                    },
                    "required": ["thscode", "report"],
                },
                "fn": ifind.fin_statement,
            },
            {
                "name": "ifind_announcement",
                "display_name": "公告列表（iFinD）",
                "description": "上市公司公告标题 + PDF 链接，为待核实事项提供原始材料线索",
                "source": "ifind",
                "params_schema": {
                    "type": "object",
                    "properties": {"thscode": {"type": "string"}, "limit": {"type": "integer", "default": 5}},
                    "required": ["thscode"],
                },
                "fn": ifind.announcement,
            },
            # ifind_news 已移除：iFinD MCP 实测无新闻类工具（2026-09-24 tools/list）
        ]
        self._by_name = {s["name"]: s for s in self._specs}

    def capabilities(self) -> dict[str, Any]:
        return {
            "tools": [
                {
                    "name": s["name"],
                    "display_name": s["display_name"],
                    "description": s["description"],
                    "source": s["source"],
                    "params_schema": s["params_schema"],
                    "returns": RETURNS,
                }
                for s in self._specs
            ]
        }

    def has(self, name: str) -> bool:
        return name in self._by_name

    async def call(
        self,
        name: str,
        params: dict[str, Any],
        *,
        thread_id: str = "",
        cost: CostTracker | None = None,
        visitor_id: str = "",
    ) -> tuple[ToolEnvelope, int]:
        spec = self._by_name.get(name)
        if spec is None:
            raise KeyError(f"未知工具: {name}")
        fn: ToolFn = spec["fn"]
        start = time.monotonic()
        try:
            envelope = await fn(**params)
        except TypeError as exc:
            # 参数不匹配（如编辑后的计划缺参数）→ 错误信封，不打断整个研究流程
            envelope = err_envelope(
                source=spec.get("source", "unknown"),
                kind="bad_params",
                message=f"工具参数不匹配: {exc}",
                auth="ok",
            )
        latency_ms = int((time.monotonic() - start) * 1000)
        status = "ok" if envelope.error is None else "error"
        if envelope.error is None and not envelope.data:
            status = "empty"
        await self.audit.log(
            thread_id=thread_id or "unknown",
            tool=name,
            params=params,
            latency_ms=latency_ms,
            auth=envelope.auth,
            status=status,
            error=envelope.error.message if envelope.error else None,
            visitor_id=visitor_id,
        )
        if cost is not None:
            cost.record_tool()
        return envelope, latency_ms
