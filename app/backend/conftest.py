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
