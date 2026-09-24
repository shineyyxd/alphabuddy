import json

import pytest
from fastapi.testclient import TestClient


def _parse_sse(lines):
    events = []
    current = None
    for line in lines:
        if line.startswith("event: "):
            current = line[7:].strip()
        elif line.startswith("data: ") and current:
            events.append((current, json.loads(line[6:])))
            current = None
    return events


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "api.db"))
    monkeypatch.setenv("ALLOW_FIXTURE_FALLBACK", "true")
    from app.main import app

    with TestClient(app) as c:
        yield c


def test_full_api_flow(client):
    r = client.post("/api/threads", json={
        "goal": "验证寒武纪盈利改善来自主营业务", "skill": "thesis_check",
    })
    assert r.status_code == 200
    tid = r.json()["thread_id"]

    # 第一次 /run：跑到审批 interrupt 停住
    with client.stream("POST", f"/api/threads/{tid}/run", json={"resume_token": None}) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        events = _parse_sse(resp.iter_lines())
    types = [t for t, _ in events]
    assert "run_started" in types
    assert "plan" in types
    assert "interrupt" in types
    assert "artifact_done" not in types

    # 刷新恢复：state 快照可用
    state = client.get(f"/api/threads/{tid}/state").json()
    assert state["status"] == "awaiting_approval"
    assert state["skill"] == "thesis_check"

    # 审批后继续
    r = client.post(f"/api/threads/{tid}/approve", json={"action": "approve"})
    assert r.json() == {"ok": True}
    with client.stream("POST", f"/api/threads/{tid}/run", json={"resume_token": None}) as resp:
        events2 = _parse_sse(resp.iter_lines())
    types2 = [t for t, _ in events2]
    for t in ("step_start", "tool_call_start", "tool_call_result",
              "step_done", "artifact_delta", "artifact_done", "memory_write", "cost", "done"):
        assert t in types2, t
    done = next(d for t, d in events2 if t == "done")
    assert done["status"] == "done"
    artifact = next(d for t, d in events2 if t == "artifact_done")
    assert "证据清单" in artifact["markdown"]
    assert "待核实事项" in artifact["markdown"]
    assert "59.96" in artifact["markdown"]

    # 状态与审计
    state = client.get(f"/api/threads/{tid}/state").json()
    assert state["status"] == "done"
    assert state["artifacts"]
    assert state["cost"]["tool_calls"] == 4
    audit = client.get(f"/api/threads/{tid}/audit").json()["audit"]
    assert len(audit) == 4
    assert all(row["auth"] == "fixture" for row in audit)

    threads = client.get("/api/threads").json()["threads"]
    assert any(t["thread_id"] == tid and t["status"] == "done" for t in threads)


def test_guard_blocked_thread(client):
    r = client.post("/api/threads", json={"goal": "寒武纪下周会涨吗", "skill": None})
    tid = r.json()["thread_id"]
    with client.stream("POST", f"/api/threads/{tid}/run", json={"resume_token": None}) as resp:
        events = _parse_sse(resp.iter_lines())
    types = [t for t, _ in events]
    assert "warning" in types
    warning = next(d for t, d in events if t == "warning")
    assert warning["kind"] == "guard"
    assert "plan" not in types  # 未进入研究计划
    state = client.get(f"/api/threads/{tid}/state").json()
    assert state["status"] == "failed"


def test_capabilities(client):
    caps = client.get("/api/capabilities").json()["tools"]
    names = {t["name"] for t in caps}
    assert names == {
        "fuyao_quote_snapshot", "fuyao_valuation", "ifind_fin_indicator",
        "ifind_fin_statement", "ifind_announcement",
    }
    assert all(t["returns"] == ["data", "source", "as_of", "unit", "caliber"] for t in caps)


def test_unknown_thread_404(client):
    assert client.get("/api/threads/nope/state").status_code == 404
    assert client.post("/api/threads/nope/approve", json={"action": "approve"}).status_code == 404
