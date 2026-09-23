import pytest

from app.config import get_settings
from app.db import init_db
from app.tools.base import AuditLogger
from app.tools.registry import ToolRegistry


@pytest.fixture()
async def registry(tmp_db):
    await init_db(tmp_db)
    return ToolRegistry(get_settings(), AuditLogger(tmp_db))


async def test_fuyao_snapshot_fixture_envelope(registry):
    env, latency = await registry.call(
        "fuyao_quote_snapshot", {"thscode": "688256.SH"}, thread_id="t1"
    )
    assert env.error is None
    assert env.auth == "fixture"
    assert env.source == "fuyao"
    assert env.unit == "元"
    assert env.caliber
    assert env.as_of
    assert env.fetched_at
    assert env.data["snapshot"]["thscode"] == "688256.SH"
    assert env.data["snapshot"]["last_price"] > 0
    assert latency >= 0


async def test_ifind_indicator_fixture_envelope(registry):
    env, _ = await registry.call(
        "ifind_fin_indicator", {"thscode": "688256.SH", "report": "2026-2"}, thread_id="t1"
    )
    assert env.error is None
    assert env.auth == "fixture"
    metrics = {m["key"]: m for m in env.data["metrics"]}
    assert metrics["operating_income"]["value"] == 5996000000
    assert metrics["operating_income"]["yoy_pct"] == 108.13
    assert metrics["net_margin"]["prior"] == 36.02
    assert metrics["rd_expense_ratio"]["value"] == 11.72


async def test_audit_log_written(registry, tmp_db):
    await registry.call("fuyao_valuation", {"thscode": "688256.SH"}, thread_id="t_audit")
    logs = await registry.audit.list_for_thread("t_audit")
    assert len(logs) == 1
    row = logs[0]
    assert row["tool"] == "fuyao_valuation"
    assert row["auth"] == "fixture"
    assert row["status"] == "ok"
    assert row["params"]["thscode"] == "688256.SH"
    assert row["latency_ms"] >= 0


async def test_missing_key_without_fixture_fallback(tmp_db, monkeypatch):
    monkeypatch.setenv("ALLOW_FIXTURE_FALLBACK", "false")
    await init_db(tmp_db)
    reg = ToolRegistry(get_settings(), AuditLogger(tmp_db))
    env, _ = await reg.call("ifind_fin_statement", {"thscode": "688256.SH", "report": "2026-2"}, thread_id="t2")
    assert env.data is None
    assert env.auth == "missing_key"
    assert env.error.kind == "missing_key"
    logs = await reg.audit.list_for_thread("t2")
    assert logs[0]["status"] == "error"
    assert logs[0]["auth"] == "missing_key"


async def test_bad_thscode_rejected(registry):
    env, _ = await registry.call("fuyao_quote_snapshot", {"thscode": "not-a-code"}, thread_id="t3")
    assert env.data is None
    assert env.error.kind == "bad_params"


async def test_api_error_with_key_no_fallback(tmp_db, monkeypatch):
    import respx

    monkeypatch.setenv("FUYAO_API_KEY", "test-key")
    monkeypatch.setenv("ALLOW_FIXTURE_FALLBACK", "false")
    await init_db(tmp_db)
    reg = ToolRegistry(get_settings(), AuditLogger(tmp_db))
    with respx.mock:
        respx.get(url__startswith="https://fuyao.aicubes.cn/api/a-share/prices/snapshot").respond(500)
        env, _ = await reg.call("fuyao_quote_snapshot", {"thscode": "688256.SH"}, thread_id="t4")
    assert env.data is None
    assert env.error.kind == "api_error"


async def test_api_error_falls_back_to_fixture(tmp_db, monkeypatch):
    import respx

    monkeypatch.setenv("FUYAO_API_KEY", "test-key")
    monkeypatch.setenv("ALLOW_FIXTURE_FALLBACK", "true")
    await init_db(tmp_db)
    reg = ToolRegistry(get_settings(), AuditLogger(tmp_db))
    with respx.mock:
        respx.get(url__startswith="https://fuyao.aicubes.cn/api/a-share/prices/snapshot").respond(500)
        env, _ = await reg.call("fuyao_quote_snapshot", {"thscode": "688256.SH"}, thread_id="t5")
    assert env.error is None
    assert env.auth == "fixture"
    assert env.data["snapshot"]["thscode"] == "688256.SH"
