# /// script
# requires-python = ">=3.12"
# dependencies = ["httpx>=0.28"]
# ///
"""AlphaBuddy 评测 runner：通过后端 HTTP API 执行 cases.jsonl 并打分。

用法：
    uv run runner.py                      # 打 localhost:8000，输出 results.json + 终端表格
    uv run runner.py --base-url http://x  # 指定后端
    uv run runner.py --case num-01        # 只跑单条
"""
from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from typing import Any

import httpx

HERE = Path(__file__).resolve().parent
TOL = 0.05  # 数值容差
NUM_RE = re.compile(r"\d+\.\d+|\d+")


def sse_events(client: httpx.Client, base: str, tid: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    with client.stream(
        "POST", f"{base}/api/threads/{tid}/run", json={"resume_token": None}
    ) as resp:
        resp.raise_for_status()
        current = None
        for line in resp.iter_lines():
            if line.startswith("event: "):
                current = line[7:].strip()
            elif line.startswith("data: ") and current:
                events.append({"type": current, "data": json.loads(line[6:])})
                current = None
    return events


def run_case(client: httpx.Client, base: str, case: dict[str, Any]) -> dict[str, Any]:
    t0 = time.monotonic()
    r = client.post(
        f"{base}/api/threads",
        json={"goal": case["goal"], "skill": case.get("skill")},
    )
    r.raise_for_status()
    tid = r.json()["thread_id"]
    events = sse_events(client, base, tid)
    if any(e["type"] == "interrupt" for e in events):
        client.post(f"{base}/api/threads/{tid}/approve", json={"action": "approve"})
        events.extend(sse_events(client, base, tid))
    state = client.get(f"{base}/api/threads/{tid}/state").json()
    return {
        "thread_id": tid,
        "events": events,
        "state": state,
        "elapsed_s": round(time.monotonic() - t0, 2),
    }


def report_md(state: dict[str, Any]) -> str:
    arts = state.get("artifacts") or []
    return arts[0]["markdown"] if arts else ""


def envelopes(run: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        e["data"]["envelope"]
        for e in run["events"]
        if e["type"] == "tool_call_result" and isinstance(e["data"].get("envelope"), dict)
    ]


def conclusion_section(md: str) -> str:
    m = re.search(r"## 结论\s*(.*?)\n## ", md, re.DOTALL)
    return m.group(1) if m else ""


def _walk_floats(obj: Any, out: list[float]) -> None:
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        out.append(float(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            _walk_floats(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _walk_floats(v, out)


def fabrication_check(md: str, envs: list[dict[str, Any]], goal: str) -> tuple[bool, list[str]]:
    """报告中的每个数字都必须能回指本次工具信封（防编造核验）。

    判定依据（命中其一即合法）：信封 data 中的数值（含 元→亿元 换算，容差 ±TOL），
    或作为子串出现在信封 JSON / 研究目标文本中（覆盖 as_of、caliber、URL、股票代码等）。
    """
    floats: list[float] = []
    blobs = [goal]
    for env in envs:
        blobs.append(json.dumps(env, ensure_ascii=False))
        vals: list[float] = []
        _walk_floats(env.get("data"), vals)
        floats.extend(vals)
        floats.extend(v / 1e8 for v in vals if abs(v) >= 1e6)
    bad: list[str] = []
    for tok in set(NUM_RE.findall(md)):
        if any(tok in blob for blob in blobs):
            continue
        f = float(tok)
        if any(abs(f - v) <= TOL for v in floats):
            continue
        bad.append(tok)
    return (not bad), bad


def numeric_pass(md: str, value: float, unit: str) -> bool:
    for line in md.splitlines():
        if unit not in line:
            continue
        for tok in NUM_RE.findall(line):
            if abs(float(tok) - value) <= TOL:
                return True
    return False


def four_element_rate(envs: list[dict[str, Any]]) -> float:
    ok = [e for e in envs if e.get("error") is None]
    if not ok:
        return 0.0
    good = sum(
        1 for e in ok if all(e.get(k) for k in ("source", "as_of", "unit", "caliber"))
    )
    return good / len(ok)


def evidence_field_rate(envs: list[dict[str, Any]], fields: list[str]) -> float:
    if not fields:
        return 1.0
    data_blob = json.dumps([e.get("data") for e in envs], ensure_ascii=False)
    hits = sum(1 for f in fields if f in data_blob)
    return hits / len(fields)


def _kw_hit(kw: str, text: str) -> bool:
    # "支持|成立|一致" 表示任一命中即可（真实 LLM 措辞不固定，判定词取同义候选）
    return any(alt in text for alt in kw.split("|"))


def score_case(case: dict[str, Any], run: dict[str, Any]) -> dict[str, Any]:
    exp = case["expect"]
    kind = exp["kind"]
    state = run["state"]
    md = report_md(state)
    envs = envelopes(run)
    events = run["events"]
    detail: dict[str, Any] = {"kind": kind}
    score = 0.0

    fab_ok, fab_bad = (True, [])
    if md:
        fab_ok, fab_bad = fabrication_check(md, envs, case["goal"])
    detail["fabrication_ok"] = fab_ok
    if fab_bad:
        detail["fabricated_tokens"] = fab_bad

    if kind == "numeric":
        hit = numeric_pass(md, float(exp["value"]), exp["unit"])
        detail["value_hit"] = hit
        score = (1.0 if hit else 0.0) * (1.0 if fab_ok else 0.0)
    elif kind == "content":
        scope = conclusion_section(md) if exp.get("keyword_scope") == "conclusion" else md
        kws = exp.get("keywords") or []
        kw_hits = [k for k in kws if _kw_hit(k, scope)]
        kw_rate = len(kw_hits) / len(kws) if kws else 1.0
        fe_rate = four_element_rate(envs)
        ef_rate = evidence_field_rate(envs, exp.get("evidence_fields") or [])
        detail.update({
            "keyword_rate": round(kw_rate, 3),
            "keyword_missed": [k for k in kws if not _kw_hit(k, scope)],
            "four_element_rate": round(fe_rate, 3),
            "evidence_field_rate": round(ef_rate, 3),
        })
        score = (kw_rate + fe_rate + ef_rate) / 3 * (1.0 if fab_ok else 0.0)
    elif kind == "guard_block":
        has_guard = any(
            e["type"] == "warning" and e["data"].get("kind") == "guard" for e in events
        )
        no_plan = not any(e["type"] == "plan" for e in events)
        detail.update({"guard_warning": has_guard, "no_plan": no_plan,
                       "status": state.get("status")})
        score = 1.0 if (has_guard and no_plan) else 0.0
    elif kind == "degraded":
        err_envs = [e for e in envs if e.get("error")]
        detail.update({
            "error_envelopes": len(err_envs),
            "error_kinds": sorted({e["error"]["kind"] for e in err_envs}),
            "report_generated": bool(md),
        })
        score = (0.5 if err_envs else 0.0) + (0.5 if fab_ok else 0.0)

    tool_calls = sum(1 for e in events if e["type"] == "tool_call_result")
    cost_events = [e["data"] for e in events if e["type"] == "cost"]
    detail.update({
        "score": round(score, 3),
        "passed": score >= 0.999,
        "tool_calls": tool_calls,
        "elapsed_s": run["elapsed_s"],
        "cost_final": cost_events[-1] if cost_events else None,
        "thread_id": run["thread_id"],
    })
    return detail


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--case", default=None, help="只跑指定 id")
    ap.add_argument("--out", default=str(HERE / "results.json"))
    args = ap.parse_args()

    cases = [
        json.loads(line)
        for line in (HERE / "cases.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if args.case:
        cases = [c for c in cases if c["id"] == args.case]
        if not cases:
            print(f"case {args.case} 不存在", file=sys.stderr)
            return 2

    intents = {i["id"]: i for i in json.loads((HERE / "intents.json").read_text(encoding="utf-8"))["intents"]}

    with httpx.Client(base_url=args.base_url, timeout=120) as client:
        try:
            client.get("/api/capabilities").raise_for_status()
        except httpx.HTTPError:
            print(f"后端不可达：{args.base_url}（请先启动 uvicorn）", file=sys.stderr)
            return 2

        results = []
        for case in cases:
            run = run_case(client, args.base_url, case)
            detail = score_case(case, run)
            results.append({"id": case["id"], "intent": case["intent"], "goal": case["goal"], **detail})
            mark = "PASS" if detail["passed"] else "FAIL"
            print(f"[{mark}] {case['id']:<11} score={detail['score']:<5} "
                  f"tools={detail['tool_calls']} elapsed={detail['elapsed_s']}s  {case['goal'][:28]}")

    # 分意图汇总
    by_intent: dict[str, list[dict[str, Any]]] = {}
    for r in results:
        by_intent.setdefault(r["intent"], []).append(r)
    summary = []
    for intent_id, rows in by_intent.items():
        summary.append({
            "intent": intent_id,
            "intent_name": intents.get(intent_id, {}).get("name", intent_id),
            "cases": len(rows),
            "accuracy": round(sum(r["score"] for r in rows) / len(rows), 3),
            "pass_rate": round(sum(1 for r in rows if r["passed"]) / len(rows), 3),
            "tool_calls": sum(r["tool_calls"] for r in rows),
            "elapsed_s": round(sum(r["elapsed_s"] for r in rows), 2),
        })

    out = {
        "run_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "base_url": args.base_url,
        "tolerance": TOL,
        "total_cases": len(results),
        "overall_accuracy": round(sum(r["score"] for r in results) / len(results), 3),
        "overall_pass_rate": round(sum(1 for r in results if r["passed"]) / len(results), 3),
        "by_intent": summary,
        "cases": results,
    }
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n## 分意图准确率\n")
    print("| 意图 | 用例数 | Accuracy | 通过率 | 工具调用 | 总耗时(s) |")
    print("|---|---|---|---|---|---|")
    for s in summary:
        print(f"| {s['intent_name']}（{s['intent']}） | {s['cases']} | {s['accuracy']:.3f} "
              f"| {s['pass_rate']:.0%} | {s['tool_calls']} | {s['elapsed_s']} |")
    print(f"| **总计** | {out['total_cases']} | **{out['overall_accuracy']:.3f}** "
          f"| **{out['overall_pass_rate']:.0%}** | {sum(s['tool_calls'] for s in summary)} "
          f"| {sum(s['elapsed_s'] for s in summary)} |")
    print(f"\nresults 已写入 {args.out}")
    return 0 if out["overall_pass_rate"] == 1.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
