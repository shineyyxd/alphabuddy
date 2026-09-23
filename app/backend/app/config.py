from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return int(raw)


@dataclass(frozen=True)
class Settings:
    llm_base_url: str
    llm_api_key: str
    llm_model: str
    fuyao_base_url: str
    fuyao_api_key: str
    ifind_mcp_url: str
    ifind_auth_token: str
    allow_fixture_fallback: bool
    max_steps: int
    token_budget: int
    tool_timeout_seconds: float
    langfuse_public_key: str
    langfuse_secret_key: str
    langfuse_host: str
    sqlite_path: Path
    fixture_dir: Path
    compress_threshold_chars: int

    @property
    def langfuse_enabled(self) -> bool:
        return bool(self.langfuse_public_key and self.langfuse_secret_key)


def get_settings() -> Settings:
    sqlite_path = Path(os.environ.get("SQLITE_PATH", "./data/xbuddy.db"))
    if not sqlite_path.is_absolute():
        sqlite_path = _BACKEND_DIR / sqlite_path
    return Settings(
        llm_base_url=os.environ.get("LLM_BASE_URL", "https://api.moonshot.cn/v1"),
        llm_api_key=os.environ.get("LLM_API_KEY", ""),
        llm_model=os.environ.get("LLM_MODEL", "kimi-k2-0905-preview"),
        fuyao_base_url=os.environ.get("FUYAO_BASE_URL", "https://fuyao.aicubes.cn"),
        fuyao_api_key=os.environ.get("FUYAO_API_KEY", ""),
        ifind_mcp_url=os.environ.get(
            "IFIND_MCP_URL",
            "https://api-mcp.51ifind.com:8643/ds-mcp-servers/hexin-ifind-ds-stock-mcp",
        ),
        ifind_auth_token=os.environ.get("IFIND_AUTH_TOKEN", ""),
        allow_fixture_fallback=_bool("ALLOW_FIXTURE_FALLBACK", True),
        max_steps=_int("MAX_STEPS", 30),
        token_budget=_int("TOKEN_BUDGET", 200000),
        tool_timeout_seconds=float(_int("TOOL_TIMEOUT_SECONDS", 10)),
        langfuse_public_key=os.environ.get("LANGFUSE_PUBLIC_KEY", ""),
        langfuse_secret_key=os.environ.get("LANGFUSE_SECRET_KEY", ""),
        langfuse_host=os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com"),
        sqlite_path=sqlite_path,
        fixture_dir=_BACKEND_DIR / "fixtures",
        compress_threshold_chars=_int("COMPRESS_THRESHOLD_CHARS", 24000),
    )
