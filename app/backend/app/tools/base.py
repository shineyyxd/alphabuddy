from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import aiosqlite
import httpx

from ..config import Settings
from ..models import AuthStatus, ToolEnvelope, ToolError


def now_iso() -> str:
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def ok_envelope(
    *,
    data: dict[str, Any],
    source: str,
    as_of: str | None,
    unit: str,
    caliber: str,
    auth: AuthStatus,
) -> ToolEnvelope:
    return ToolEnvelope(
        data=data, source=source, as_of=as_of, unit=unit, caliber=caliber,
        fetched_at=now_iso(), auth=auth, error=None,
    )


def err_envelope(
    *,
    source: str,
    kind: str,
    message: str,
    auth: AuthStatus,
    as_of: str | None = None,
    unit: str | None = None,
    caliber: str | None = None,
) -> ToolEnvelope:
    return ToolEnvelope(
        data=None, source=source, as_of=as_of, unit=unit, caliber=caliber,
        fetched_at=now_iso(), auth=auth, error=ToolError(kind=kind, message=message),
    )


_THSCODE_RE = re.compile(r"^\d{6}\.(SH|SZ|BJ)$", re.IGNORECASE)


def validate_thscode(thscode: str) -> str | None:
    if not _THSCODE_RE.match(thscode.strip()):
        return f"thscode「{thscode}」格式非法，应为六位数字加 .SH/.SZ/.BJ 后缀"
    return None


def ms_to_date(ms: int | float | None) -> str | None:
    if ms is None:
        return None
    return datetime.fromtimestamp(float(ms) / 1000).astimezone().strftime("%Y-%m-%d")


class FixtureStore:
    def __init__(self, fixture_dir: Path) -> None:
        self.dir = fixture_dir

    def load(self, tool: str, key: str) -> dict[str, Any] | None:
        safe_key = re.sub(r"[^0-9A-Za-z_\-.]", "_", key)
        path = self.dir / tool / f"{safe_key}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))


class AuditLogger:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    async def log(
        self,
        *,
        thread_id: str,
        tool: str,
        params: dict[str, Any],
        latency_ms: int,
        auth: str,
        status: str,
        error: str | None,
    ) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO tool_audit(thread_id, ts, tool, params, latency_ms, auth, status, error)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (thread_id, now_iso(), tool, json.dumps(params, ensure_ascii=False),
                 latency_ms, auth, status, error),
            )
            await db.commit()

    async def list_for_thread(self, thread_id: str) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT ts, tool, params, latency_ms, auth, status, error"
                " FROM tool_audit WHERE thread_id=? ORDER BY id",
                (thread_id,),
            )
            rows = await cur.fetchall()
        return [
            {
                "ts": r["ts"], "tool": r["tool"],
                "params": json.loads(r["params"]), "latency_ms": r["latency_ms"],
                "auth": r["auth"], "status": r["status"], "error": r["error"],
            }
            for r in rows
        ]


class BaseAPIClient:
    """三态数据源客户端：ok（真调通）/ fixture（回放）/ missing_key（显式降级）。"""

    source: str = ""

    def __init__(self, settings: Settings, fixtures: FixtureStore) -> None:
        self.settings = settings
        self.fixtures = fixtures

    @property
    def has_key(self) -> bool:  # pragma: no cover - overridden
        return False

    async def _request(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        timeout = self.settings.tool_timeout_seconds
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.request(method, url, **kwargs)
            resp.raise_for_status()
            return resp.json()

    async def _call(
        self,
        *,
        tool: str,
        fixture_key: str,
        fetcher,
        normalize,
        as_of_hint: str | None = None,
        unit: str = "",
        caliber: str = "",
    ) -> ToolEnvelope:
        """统一调用骨架：无 key → missing_key/fixture；有 key → 真调，失败时按开关降级。"""
        if not self.has_key:
            if self.settings.allow_fixture_fallback:
                fx = self.fixtures.load(tool, fixture_key)
                if fx is not None:
                    data = normalize(fx)
                    return ok_envelope(
                        data=data, source=self.source,
                        as_of=_guess_as_of(fx) or as_of_hint, unit=unit,
                        caliber=caliber, auth="fixture",
                    )
            return err_envelope(
                source=self.source, kind="missing_key",
                message=f"{self.source} 凭证未配置（missing_key），且未命中 fixture 回放数据",
                auth="missing_key", as_of=as_of_hint, unit=unit or None, caliber=caliber or None,
            )
        try:
            raw = await asyncio.wait_for(fetcher(), timeout=self.settings.tool_timeout_seconds)
        except asyncio.TimeoutError:
            return await self._degrade(
                tool, fixture_key, normalize, "timeout",
                f"调用超时（>{self.settings.tool_timeout_seconds:.0f}s）", as_of_hint, unit, caliber,
            )
        except Exception as exc:  # 网络错误 / HTTP 错误 / 业务错误统一走降级判定
            return await self._degrade(
                tool, fixture_key, normalize, "api_error", str(exc), as_of_hint, unit, caliber,
            )
        return ok_envelope(
            data=normalize(raw), source=self.source,
            as_of=_guess_as_of(raw) or as_of_hint, unit=unit, caliber=caliber, auth="ok",
        )

    async def _degrade(
        self, tool, fixture_key, normalize, kind, message, as_of_hint, unit, caliber,
    ) -> ToolEnvelope:
        if self.settings.allow_fixture_fallback:
            fx = self.fixtures.load(tool, fixture_key)
            if fx is not None:
                return ok_envelope(
                    data=normalize(fx), source=self.source,
                    as_of=_guess_as_of(fx) or as_of_hint, unit=unit, caliber=caliber,
                    auth="fixture",
                )
        return err_envelope(
            source=self.source, kind=kind, message=message, auth="ok",
            as_of=as_of_hint, unit=unit or None, caliber=caliber or None,
        )


def _guess_as_of(raw: dict[str, Any]) -> str | None:
    # JSON-RPC / MCP 风格 {result:{content:[{text:"<json>"}]}} 逐层解包
    if isinstance(raw, dict) and isinstance(raw.get("result"), dict):
        raw = raw["result"]
    content = raw.get("content") if isinstance(raw, dict) else None
    if isinstance(content, list) and content and isinstance(content[0], dict):
        text = content[0].get("text")
        if isinstance(text, str):
            try:
                raw = json.loads(text)
            except (json.JSONDecodeError, TypeError):
                pass
    data = raw.get("data") if isinstance(raw, dict) else None
    if data is None and isinstance(raw, dict):
        data = raw
    if isinstance(data, dict):
        ts = data.get("timestamp")
        if ts:
            return ms_to_date(ts)
        items = data.get("item")
        if isinstance(items, list) and items:
            pe = items[0].get("period_end_ms")
            if pe:
                return ms_to_date(pe)
        if data.get("period_end"):
            return str(data["period_end"])
        anns = data.get("announcements")
        if isinstance(anns, list) and anns and isinstance(anns[0], dict) and anns[0].get("date"):
            return str(anns[0]["date"])
        if data.get("report"):
            return str(data["report"])
    return None
