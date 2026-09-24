import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))

# 测试环境：绝不使用真实 Key，固定 fixture 回放模式与临时数据库
os.environ.pop("LLM_API_KEY", None)
os.environ.pop("FUYAO_API_KEY", None)
os.environ.pop("IFIND_AUTH_TOKEN", None)
os.environ["ALLOW_FIXTURE_FALLBACK"] = "true"


@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    path = tmp_path / "test.db"
    monkeypatch.setenv("SQLITE_PATH", str(path))
    return str(path)


@pytest.fixture()
async def graph_env(tmp_db):
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    from langgraph.store.memory import InMemoryStore

    from app.config import get_settings
    from app.db import init_db
    from app.graph import Runtime, build_graph, set_runtime
    from app.llm import LLMClient
    from app.tools.base import AuditLogger
    from app.tools.registry import ToolRegistry

    settings = get_settings()
    await init_db(tmp_db)
    registry = ToolRegistry(settings, AuditLogger(tmp_db))
    llm = LLMClient(settings.llm_base_url, "", settings.llm_model)
    store = InMemoryStore()
    rt = Runtime(
        settings=settings, registry=registry, llm=llm, store=store,
        buses={}, costs={}, pending_approvals={},
    )
    set_runtime(rt)
    async with AsyncSqliteSaver.from_conn_string(tmp_db) as cp:
        yield build_graph(cp, store), rt
