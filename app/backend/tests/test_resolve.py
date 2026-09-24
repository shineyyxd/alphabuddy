import httpx
import pytest
import respx

from app.config import get_settings
from app.resolve import extract_subject, resolve_thscode_via_fuyao

SEARCH_URL = "https://fuyao.aicubes.cn/api/meta/tickers/search"

YUSHU_PAYLOAD = {
    "code": 0,
    "message": "success",
    "data": {
        "timestamp": 1790236800000,
        "item": [
            {
                "thscode": "688836.SH",
                "ticker": "688836",
                "name": "宇树科技-W",
                "exchange": "SH",
                "asset_type": "a-share",
                "currency": "CNY",
                "list_date": "2026-08-19",
            }
        ],
    },
}


def test_extract_subject():
    assert extract_subject("验证宇树科技的盈利能力") == "宇树科技"
    assert extract_subject("宇树科技怎么样") == "宇树科技"
    assert extract_subject("查一下宇树科技") == "宇树科技"
    assert extract_subject("点评贵州茅台 2026 中报业绩") == "贵州茅台"
    assert extract_subject("688256.SH 中报点评") == "688256.SH"


async def test_resolve_success(monkeypatch):
    monkeypatch.setenv("FUYAO_API_KEY", "test-key")
    with respx.mock:
        respx.get(url__startswith=SEARCH_URL).respond(200, json=YUSHU_PAYLOAD)
        hit = await resolve_thscode_via_fuyao("验证宇树科技的盈利能力", get_settings())
    assert hit == {"thscode": "688836.SH", "name": "宇树科技-W"}


async def test_resolve_no_result(monkeypatch):
    monkeypatch.setenv("FUYAO_API_KEY", "test-key")
    with respx.mock:
        respx.get(url__startswith=SEARCH_URL).respond(
            200, json={"code": 0, "data": {"item": []}}
        )
        assert await resolve_thscode_via_fuyao("验证某某未上市公司的盈利能力", get_settings()) is None


async def test_resolve_api_error(monkeypatch):
    monkeypatch.setenv("FUYAO_API_KEY", "test-key")
    with respx.mock:
        respx.get(url__startswith=SEARCH_URL).respond(500)
        assert await resolve_thscode_via_fuyao("验证宇树科技的盈利能力", get_settings()) is None


async def test_resolve_timeout(monkeypatch):
    monkeypatch.setenv("FUYAO_API_KEY", "test-key")
    with respx.mock:
        respx.get(url__startswith=SEARCH_URL).mock(side_effect=httpx.ConnectTimeout("boom"))
        assert await resolve_thscode_via_fuyao("验证宇树科技的盈利能力", get_settings()) is None


async def test_resolve_no_key():
    # conftest 已清空 FUYAO_API_KEY：无 Key 直接返回 None，不发请求
    assert await resolve_thscode_via_fuyao("验证宇树科技的盈利能力", get_settings()) is None


async def test_supervisor_resolves_and_emits(graph_env, monkeypatch):
    monkeypatch.setenv("FUYAO_API_KEY", "test-key")
    graph, rt = graph_env
    import dataclasses

    rt.settings = dataclasses.replace(rt.settings, fuyao_api_key="test-key")
    with respx.mock:
        respx.get(url__startswith=SEARCH_URL).respond(200, json=YUSHU_PAYLOAD)
        tid = "r1"
        out = await graph.ainvoke(
            {"goal": "验证宇树科技的盈利能力", "skill": "thesis_check", "thread_id": tid},
            {"configurable": {"thread_id": tid}, "recursion_limit": 100},
        )
    assert "__interrupt__" in out
    resolved = [e for e in rt.bus(tid).events if e["type"] == "warning" and e["data"].get("kind") == "resolved"]
    assert resolved
    assert resolved[0]["data"]["thscode"] == "688836.SH"
    interrupt_ev = next(e for e in rt.bus(tid).events if e["type"] == "interrupt")
    assert interrupt_ev["data"]["plan"][1]["params"]["thscode"] == "688836.SH"


async def test_supervisor_resolve_failure_degrades(graph_env):
    # 无 Key（conftest 清空）：解析失败 → resolve_note 进报告待核实，不阻塞
    graph, rt = graph_env
    tid = "r2"
    from langgraph.types import Command

    await graph.ainvoke(
        {"goal": "验证某未上市小公司的盈利能力", "skill": "thesis_check", "thread_id": tid},
        {"configurable": {"thread_id": tid}, "recursion_limit": 100},
    )
    out = await graph.ainvoke(
        Command(resume={"action": "approve"}),
        {"configurable": {"thread_id": tid}, "recursion_limit": 100},
    )
    assert out["report"]
    assert "未能将" in out["report"] and "建议改用股票代码输入" in out["report"]
