from __future__ import annotations

from typing import Any

import httpx

from .config import Settings

_LEADING_VERBS = (
    "验证一下", "验证", "查询一下", "查询", "查一下", "点评一下", "点评",
    "分析一下", "分析", "求证一下", "求证", "帮我看看", "看看", "研究一下",
    "研究", "查", "聊一聊", "聊聊",
)
_TRAILING_FLUFF = ("怎么样", "如何", "好不好", "行吗", "行不行")
_SEPS = ("的", "，", "。", ",", "？", "?", "！", "!", " ", "；", ";")


def extract_subject(goal: str) -> str:
    """从研究目标中抽取主体词作检索 q：'验证宇树科技的盈利能力' → '宇树科技'。"""
    s = goal.strip()
    for v in _LEADING_VERBS:
        if s.startswith(v):
            s = s[len(v):]
            break
    for sep in _SEPS:
        if sep in s:
            s = s.split(sep)[0]
    for t in _TRAILING_FLUFF:
        if s.endswith(t) and len(s) > len(t):
            s = s[: -len(t)]
    return s.strip()


async def resolve_thscode_via_fuyao(goal: str, settings: Settings) -> dict[str, Any] | None:
    """扶摇标的检索：公司名 → thscode。任何失败（无 Key/超时/无结果）都返回 None，不阻塞主流程。"""
    if not settings.fuyao_api_key:
        return None
    q = extract_subject(goal)
    if len(q) < 2:
        return None
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(
                f"{settings.fuyao_base_url}/api/meta/tickers/search",
                params={"q": q, "asset_type": "a-share"},
                headers={"X-api-key": settings.fuyao_api_key},
            )
            resp.raise_for_status()
            payload = resp.json()
        if payload.get("code") != 0:
            return None
        for item in (payload.get("data") or {}).get("item") or []:
            if item.get("asset_type") == "a-share" and item.get("thscode"):
                return {"thscode": item["thscode"], "name": item.get("name") or ""}
    except Exception:
        return None
    return None
