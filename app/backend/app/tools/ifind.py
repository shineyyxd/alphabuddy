from __future__ import annotations

import json
from typing import Any

from ..models import ToolEnvelope
from .base import BaseAPIClient, err_envelope, validate_thscode


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
        timeout = self.settings.tool_timeout_seconds
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

    async def _resolve_tool(self, candidates: list[str]) -> str:
        if self._tool_names is None:
            resp = await self._rpc("tools/list")
            tools = (resp.get("result") or {}).get("tools") or []
            self._tool_names = [t.get("name", "") for t in tools]
        for cand in candidates:
            for name in self._tool_names:
                if cand in name:
                    return name
        return candidates[0]

    async def _call_tool(self, candidates: list[str], arguments: dict[str, Any]) -> dict[str, Any]:
        await self._ensure_initialized()
        name = await self._resolve_tool(candidates)
        resp = await self._rpc("tools/call", {"name": name, "arguments": arguments})
        return extract_tool_json(resp)

    async def fin_indicator(self, thscode: str, report: str) -> ToolEnvelope:
        if msg := validate_thscode(thscode):
            return err_envelope(source=self.source, kind="bad_params", message=msg, auth=self._auth_hint())
        caliber = (
            "iFinD 财务指标：营收/归母净利/扣非归母净利同比，净利率、毛利率、研发费用率"
            f"（本期与上年同期），报告期 {report}"
        )

        async def fetch() -> dict[str, Any]:
            return await self._call_tool(
                ["fin_indicator", "financial_indicator", "指标"],
                {"thscode": thscode, "report": report},
            )

        return await self._call(
            tool="ifind_fin_indicator", fixture_key=f"{thscode}_{report}", fetcher=fetch,
            normalize=_norm, as_of_hint=report, unit="%", caliber=caliber,
        )

    async def fin_statement(self, thscode: str, report: str, statement: str = "income") -> ToolEnvelope:
        if msg := validate_thscode(thscode):
            return err_envelope(source=self.source, kind="bad_params", message=msg, auth=self._auth_hint())
        caliber = f"iFinD 合并财务报表（{statement}），报告期 {report}，含上年同期对照"

        async def fetch() -> dict[str, Any]:
            return await self._call_tool(
                ["fin_statement", "financial_statement", "报表"],
                {"thscode": thscode, "report": report, "statement": statement},
            )

        return await self._call(
            tool="ifind_fin_statement", fixture_key=f"{thscode}_{report}_{statement}",
            fetcher=fetch, normalize=_norm, as_of_hint=report,
            unit="元", caliber=caliber,
        )

    async def announcement(self, thscode: str, limit: int = 5) -> ToolEnvelope:
        if msg := validate_thscode(thscode):
            return err_envelope(source=self.source, kind="bad_params", message=msg, auth=self._auth_hint())

        async def fetch() -> dict[str, Any]:
            return await self._call_tool(
                ["announcement", "公告"], {"thscode": thscode, "limit": limit},
            )

        return await self._call(
            tool="ifind_announcement", fixture_key=thscode, fetcher=fetch,
            normalize=_norm, unit="条", caliber="上市公司公告列表（标题/日期/PDF 链接）",
        )

    async def news(self, thscode: str, limit: int = 5) -> ToolEnvelope:
        if msg := validate_thscode(thscode):
            return err_envelope(source=self.source, kind="bad_params", message=msg, auth=self._auth_hint())

        async def fetch() -> dict[str, Any]:
            return await self._call_tool(["news", "新闻"], {"thscode": thscode, "limit": limit})

        return await self._call(
            tool="ifind_news", fixture_key=thscode, fetcher=fetch,
            normalize=_norm, unit="条", caliber="个股相关新闻列表",
        )

    def _auth_hint(self) -> str:
        if self.has_key:
            return "ok"
        return "fixture" if self.settings.allow_fixture_fallback else "missing_key"
