"""Configuration loaded from environment variables (never from the repo)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(path: Path = Path(".env")) -> None:
    """Minimal .env loader so local runs work without extra dependencies."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Config:
    anthropic_api_key: str | None
    claude_model: str
    ig_user_id: str
    ig_access_token: str
    ig_graph_version: str
    ig_graph_host: str
    telegram_bot_token: str
    telegram_chat_id: str
    data_dir: Path
    report_language: str
    timezone: str
    account_brief: str

    @classmethod
    def from_env(cls, require: tuple[str, ...] = ()) -> "Config":
        _load_dotenv()
        env = os.environ.get
        cfg = cls(
            anthropic_api_key=env("ANTHROPIC_API_KEY") or None,
            claude_model=env("CLAUDE_MODEL") or "claude-opus-5-5",
            ig_user_id=env("IG_USER_ID", ""),
            ig_access_token=env("IG_ACCESS_TOKEN", ""),
            ig_graph_version=env("IG_GRAPH_VERSION") or "v24.0",
            ig_graph_host=env("IG_GRAPH_HOST") or "graph.facebook.com",
            telegram_bot_token=env("TELEGRAM_BOT_TOKEN", ""),
            telegram_chat_id=env("TELEGRAM_CHAT_ID", ""),
            data_dir=Path(env("DATA_DIR") or "data"),
            report_language=env("REPORT_LANGUAGE") or "fa",
            timezone=env("TIMEZONE") or "Asia/Tehran",
            account_brief=env("ACCOUNT_BRIEF", ""),
        )
        missing = [name for name in require if not getattr(cfg, name.lower(), None)]
        if missing:
            raise ConfigError("Missing required settings: " + ", ".join(n.upper() for n in missing))
        return cfg
