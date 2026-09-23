from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI


class LLMUnavailableError(RuntimeError):
    pass


@dataclass
class LLMResponse:
    content: str
    tokens_in: int = 0
    tokens_out: int = 0


@dataclass
class LLMClient:
    """OpenAI 兼容客户端封装；LLM_API_KEY 缺失时首次调用即抛 LLMUnavailableError。"""

    base_url: str
    api_key: str
    model: str
    temperature: float = 0.2
    _chat: ChatOpenAI | None = field(default=None, init=False, repr=False)

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def _get_chat(self) -> ChatOpenAI:
        if not self.api_key:
            raise LLMUnavailableError("LLM_API_KEY 未配置，LLM 能力不可用")
        if self._chat is None:
            self._chat = ChatOpenAI(
                base_url=self.base_url,
                api_key=self.api_key,
                model=self.model,
                temperature=self.temperature,
                timeout=30,
                max_retries=1,
            )
        return self._chat

    def invoke(self, system: str, user: str) -> LLMResponse:
        chat = self._get_chat()
        messages: list[BaseMessage] = [SystemMessage(content=system), HumanMessage(content=user)]
        resp = chat.invoke(messages)
        usage: dict[str, Any] = getattr(resp, "usage_metadata", None) or {}
        return LLMResponse(
            content=str(resp.content),
            tokens_in=int(usage.get("input_tokens", 0) or 0),
            tokens_out=int(usage.get("output_tokens", 0) or 0),
        )
