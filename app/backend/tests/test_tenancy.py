import json

import pytest
from fastapi.testclient import TestClient

GOAL = "验证寒武纪盈利改善来自主营业务"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "tenancy.db"))
    monkeypatch.setenv("ALLOW_FIXTURE_FALLBACK", "true")
    from app.main import app

    with TestClient(app) as c:
        yield c


def _h(v: str) -> dict[str, str]:
    return {"X-Visitor-Id": v}


def _sse_events(resp) -> list[tuple[str, dict]]:
    events, current = [], None
    for line in resp.iter_lines():
        if line.startswith("event: "):
            current = line[7:].strip()
        elif line.startswith("data: ") and current:
            events.append((current, json.loads(line[6:])))
            current = None
    return events


def _run_full(c: TestClient, tid: str, headers: dict[str, str]) -> list[tuple[str, dict]]:
    with c.stream("POST", f"/api/threads/{tid}/run", json={"resume_token": None}, headers=headers) as r:
        events = _sse_events(r)
    if any(t == "interrupt" for t, _ in events):
        c.post(f"/api/threads/{tid}/approve", json={"action": "approve"}, headers=headers)
        with c.stream("POST", f"/api/threads/{tid}/run", json={"resume_token": None}, headers=headers) as r:
            events += _sse_events(r)
    return events


def test_threads_isolated_between_visitors(client):
    tid_a = client.post("/api/threads", json={"goal": GOAL, "skill": "thesis_check"}, headers=_h("va")).json()["thread_id"]
    tid_b = client.post("/api/threads", json={"goal": "点评寒武纪 2026 中报业绩", "skill": None}, headers=_h("vb")).json()["thread_id"]

    list_a = client.get("/api/threads", headers=_h("va")).json()["threads"]
    list_b = client.get("/api/threads", headers=_h("vb")).json()["threads"]
    assert [t["thread_id"] for t in list_a] == [tid_a]
    assert [t["thread_id"] for t in list_b] == [tid_b]

    # 跨访客访问一律 404
    for method, url, kwargs in (
        ("GET", f"/api/threads/{tid_a}/state", {}),
        ("POST", f"/api/threads/{tid_a}/approve", {"json": {"action": "approve"}}),
        ("POST", f"/api/threads/{tid_a}/run", {"json": {"resume_token": None}}),
        ("GET", f"/api/threads/{tid_a}/audit", {}),
    ):
        resp = client.request(method, url, headers=_h("vb"), **kwargs)
        assert resp.status_code == 404, (method, url, resp.status_code)

    # anon（不带 header）也看不到 va/vb 的线程
    assert client.get("/api/threads").json()["threads"] == []
    assert client.get(f"/api/threads/{tid_a}/state").status_code == 404


def test_claim_legacy_threads(client):
    # 构造历史遗留线程（visitor_id IS NULL）：直接写库
    import aiosqlite
    import asyncio

    from app.main import app as _app
    db_path = _app.state.app.db_path

    async def _insert():
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "INSERT INTO threads(thread_id, visitor_id, goal, skill, status, created_at, updated_at)"
                " VALUES ('legacy1', NULL, '旧线程', 'thesis_check', 'done', '2026-09-01', '2026-09-01')"
            )
            await db.commit()

    asyncio.run(_insert())

    # 未认领前任何人不可见
    assert client.get("/api/threads", headers=_h("va")).json()["threads"] == []
    assert client.get("/api/threads/legacy1/state", headers=_h("va")).status_code == 404

    r = client.post("/api/threads/claim", headers=_h("va"))
    assert r.json() == {"ok": True, "claimed": 1}
    threads = client.get("/api/threads", headers=_h("va")).json()["threads"]
    assert [t["thread_id"] for t in threads] == ["legacy1"]
    assert client.get("/api/threads/legacy1/state", headers=_h("va")).status_code == 200
    # 已被 va 认领，vb 仍 404；重复 claim 数量为 0
    assert client.get("/api/threads/legacy1/state", headers=_h("vb")).status_code == 404
    assert client.post("/api/threads/claim", headers=_h("vb")).json()["claimed"] == 0


def test_memory_isolated_between_visitors(client):
    # 访客 A 跑完命题验证（写记忆）
    tid_a = client.post("/api/threads", json={"goal": GOAL, "skill": "thesis_check"}, headers=_h("va")).json()["thread_id"]
    events_a = _run_full(client, tid_a, _h("va"))
    assert any(t == "memory_write" for t, _ in events_a)

    # 访客 B 追问"上次研究的…"：不应命中 A 的记忆
    tid_b = client.post("/api/threads", json={"goal": "上次研究的寒武纪结论是否仍成立", "skill": "thesis_check"}, headers=_h("vb")).json()["thread_id"]
    events_b = _run_full(client, tid_b, _h("vb"))
    md_b = next(d["markdown"] for t, d in events_b if t == "artifact_done")
    assert "关联历史记忆" not in md_b

    # 访客 A 自己追问：应命中自己的记忆
    tid_a2 = client.post("/api/threads", json={"goal": "上次研究的寒武纪结论是否仍成立", "skill": "thesis_check"}, headers=_h("va")).json()["thread_id"]
    events_a2 = _run_full(client, tid_a2, _h("va"))
    md_a2 = next(d["markdown"] for t, d in events_a2 if t == "artifact_done")
    assert "关联历史记忆" in md_a2


def test_audit_records_visitor(client):
    tid = client.post("/api/threads", json={"goal": GOAL, "skill": "thesis_check"}, headers=_h("va")).json()["thread_id"]
    _run_full(client, tid, _h("va"))
    import aiosqlite
    import asyncio

    from app.main import app as _app

    async def _q():
        async with aiosqlite.connect(_app.state.app.db_path) as db:
            cur = await db.execute(
                "SELECT DISTINCT visitor_id FROM tool_audit WHERE thread_id=?", (tid,)
            )
            return [r[0] for r in await cur.fetchall()]

    assert asyncio.run(_q()) == ["va"]


def test_ifind_timeout_widened():
    from app.config import get_settings
    from app.tools.base import AuditLogger, FixtureStore
    from app.tools.fuyao import FuyaoClient
    from app.tools.ifind import IFinDMCPClient

    s = get_settings()
    fx = FixtureStore(s.fixture_dir)
    assert IFinDMCPClient(s, fx).timeout_seconds == 20
    assert FuyaoClient(s, fx).timeout_seconds == 10
