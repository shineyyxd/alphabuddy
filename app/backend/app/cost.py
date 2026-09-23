from __future__ import annotations

import json
import time
from typing import Any

from .models import CostInfo


class CostTracker:
    """进程内成本累计器。Langfuse key 缺失时的兜底（默认路径），key 存在时另行上报。"""

    def __init__(self, token_budget: int) -> None:
        self.token_budget = token_budget
        self.tokens_in = 0
        self.tokens_out = 0
        self.llm_calls = 0
        self.tool_calls = 0
        self._start = time.monotonic()

    def record_llm(self, tokens_in: int, tokens_out: int) -> None:
        self.tokens_in += max(tokens_in, 0)
        self.tokens_out += max(tokens_out, 0)
        self.llm_calls += 1

    def record_tool(self) -> None:
        self.tool_calls += 1

    @property
    def budget_remaining(self) -> int:
        return max(self.token_budget - self.tokens_in - self.tokens_out, 0)

    @property
    def over_budget(self) -> bool:
        return self.tokens_in + self.tokens_out >= self.token_budget

    def snapshot(self) -> CostInfo:
        return CostInfo(
            tokens_in=self.tokens_in,
            tokens_out=self.tokens_out,
            llm_calls=self.llm_calls,
            tool_calls=self.tool_calls,
            elapsed_ms=int((time.monotonic() - self._start) * 1000),
            budget_remaining=self.budget_remaining,
        )


_langfuse_client: Any = None


def report_to_langfuse(name: str, metadata: dict[str, Any]) -> None:
    """可选上报；langfuse 未安装或未配置时静默跳过。"""
    global _langfuse_client
    try:
        if _langfuse_client is None:
            from langfuse import Langfuse  # type: ignore

            _langfuse_client = Langfuse()
        _langfuse_client.event(name=name, metadata=json.loads(json.dumps(metadata, default=str)))
    except Exception:
        return
