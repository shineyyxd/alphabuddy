from __future__ import annotations

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS threads (
    thread_id TEXT PRIMARY KEY,
    visitor_id TEXT,
    goal TEXT NOT NULL,
    skill TEXT,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tool_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id TEXT NOT NULL,
    visitor_id TEXT,
    ts TEXT NOT NULL,
    tool TEXT NOT NULL,
    params TEXT NOT NULL,
    latency_ms INTEGER NOT NULL,
    auth TEXT NOT NULL,
    status TEXT NOT NULL,
    error TEXT
);
CREATE INDEX IF NOT EXISTS idx_tool_audit_thread ON tool_audit(thread_id);
"""


async def _ensure_column(db: aiosqlite.Connection, table: str, column: str, ddl: str) -> None:
    cur = await db.execute(f"PRAGMA table_info({table})")
    cols = {row[1] for row in await cur.fetchall()}
    if column not in cols:
        await db.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")


async def init_db(path: str) -> None:
    async with aiosqlite.connect(path) as db:
        await db.executescript(SCHEMA)
        # 老库自动迁移：visitor_id 缺失则补列（历史行保持 NULL，等待 /api/threads/claim 认领）
        await _ensure_column(db, "threads", "visitor_id", "visitor_id TEXT")
        await _ensure_column(db, "tool_audit", "visitor_id", "visitor_id TEXT")
        await db.commit()
