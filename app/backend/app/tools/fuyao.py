from __future__ import annotations

from typing import Any

from ..models import ToolEnvelope
from .base import BaseAPIClient, err_envelope, validate_thscode


def _first_item(raw: dict[str, Any]) -> dict[str, Any]:
    data = raw.get("data") or {}
    items = data.get("item") or []
    return items[0] if items else {}


class FuyaoClient(BaseAPIClient):
    """扶摇 REST API（同花顺）：X-api-key 鉴权，ApiResponse 信封。"""

    source = "fuyao"

    @property
    def has_key(self) -> bool:
        return bool(self.settings.fuyao_api_key)

    async def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        raw = await self._request(
            "GET",
            f"{self.settings.fuyao_base_url}{path}",
            params=params,
            headers={"X-api-key": self.settings.fuyao_api_key},
        )
        code = raw.get("code")
        if code != 0:
            raise RuntimeError(f"扶摇业务错误 code={code}: {raw.get('message')}")
        return raw

    async def quote_snapshot(self, thscode: str) -> ToolEnvelope:
        if msg := validate_thscode(thscode):
            return err_envelope(source=self.source, kind="bad_params", message=msg, auth=self._auth_hint())

        async def fetch() -> dict[str, Any]:
            return await self._get("/api/a-share/prices/snapshot", {"thscodes": thscode})

        def normalize(raw: dict[str, Any]) -> dict[str, Any]:
            return {"snapshot": _first_item(raw)}

        return await self._call(
            tool="fuyao_quote_snapshot", fixture_key=thscode, fetcher=fetch,
            normalize=normalize, unit="元", caliber="A 股行情快照（最新价/涨跌幅/开高低收，前收盘）",
        )

    async def valuation(self, thscode: str) -> ToolEnvelope:
        if msg := validate_thscode(thscode):
            return err_envelope(source=self.source, kind="bad_params", message=msg, auth=self._auth_hint())

        async def fetch() -> dict[str, Any]:
            return await self._get("/api/a-share/valuations/snapshot", {"thscodes": thscode})

        def normalize(raw: dict[str, Any]) -> dict[str, Any]:
            return {"valuation": _first_item(raw)}

        return await self._call(
            tool="fuyao_valuation", fixture_key=thscode, fetcher=fetch,
            normalize=normalize, unit="倍", caliber="估值快照：PE(TTM/MRQ)、PB(MRQ)、PS(TTM)、PCF(TTM)",
        )

    def _auth_hint(self) -> str:
        if self.has_key:
            return "ok"
        return "fixture" if self.settings.allow_fixture_fallback else "missing_key"
