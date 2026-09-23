from __future__ import annotations

import asyncio
import json
import time
from typing import Any


def _jsonable(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if hasattr(obj, "model_dump"):
        return _jsonable(obj.model_dump())
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return str(obj)


class EventBus:
    """线程级事件总线：图节点 emit，REST 回放，SSE 订阅。"""

    def __init__(self, thread_id: str) -> None:
        self.thread_id = thread_id
        self.events: list[dict[str, Any]] = []
        self._condition = asyncio.Condition()

    def emit(self, type_: str, data: dict[str, Any]) -> dict[str, Any]:
        event = {
            "type": type_,
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "data": _jsonable(data),
        }
        self.events.append(event)

        def _notify() -> None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                return
            loop.call_soon_threadsafe(self._schedule_notify)

        _notify()
        return event

    def _schedule_notify(self) -> None:
        async def _n() -> None:
            async with self._condition:
                self._condition.notify_all()

        asyncio.ensure_future(_n())

    async def subscribe(self, start: int = 0):
        """异步生成器：从序号 start 起按序产出事件，直到收到 done/stopped 终止事件。"""
        idx = start
        while True:
            async with self._condition:
                await self._condition.wait_for(lambda: len(self.events) > idx)
            while idx < len(self.events):
                ev = self.events[idx]
                idx += 1
                yield ev
                if ev["type"] in {"done", "stopped", "_end"}:
                    return

    def render_sse(self, event: dict[str, Any]) -> str:
        return f"event: {event['type']}\ndata: {json.dumps(event['data'], ensure_ascii=False)}\n\n"
