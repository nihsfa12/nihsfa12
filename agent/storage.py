"""Local SQLite store for daily snapshots and post drafts."""
from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .instagram import AccountSnapshot

SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    day TEXT PRIMARY KEY,
    taken_at TEXT NOT NULL,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    title TEXT NOT NULL,
    format TEXT NOT NULL,
    caption TEXT NOT NULL,
    hashtags TEXT NOT NULL,
    visual_brief TEXT NOT NULL,
    best_time TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    media_id TEXT
);
"""


class Store:
    def __init__(self, data_dir: Path) -> None:
        data_dir.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(data_dir / "agent.db")
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    # snapshots
    def save_snapshot(self, day: str, snap: AccountSnapshot) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO snapshots(day, taken_at, data) VALUES (?, ?, ?)",
            (day, datetime.now(timezone.utc).isoformat(), json.dumps(asdict(snap), ensure_ascii=False)),
        )
        self.db.commit()

    def previous_snapshot(self, before_day: str) -> dict[str, Any] | None:
        row = self.db.execute(
            "SELECT data FROM snapshots WHERE day < ? ORDER BY day DESC LIMIT 1", (before_day,)
        ).fetchone()
        return json.loads(row["data"]) if row else None

    # drafts
    def add_draft(self, idea: dict[str, Any]) -> int:
        cur = self.db.execute(
            "INSERT INTO drafts(created_at, title, format, caption, hashtags, visual_brief, best_time)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                datetime.now(timezone.utc).isoformat(),
                idea["title"],
                idea["format"],
                idea["caption"],
                " ".join(idea["hashtags"]),
                idea["visual_brief"],
                idea["best_time"],
            ),
        )
        self.db.commit()
        return int(cur.lastrowid)

    def get_draft(self, draft_id: int) -> dict[str, Any] | None:
        row = self.db.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)).fetchone()
        return dict(row) if row else None

    def list_drafts(self, status: str = "draft", limit: int = 10) -> list[dict[str, Any]]:
        rows = self.db.execute(
            "SELECT * FROM drafts WHERE status = ? ORDER BY id DESC LIMIT ?", (status, limit)
        ).fetchall()
        return [dict(r) for r in rows]

    def mark_published(self, draft_id: int, media_id: str) -> None:
        self.db.execute(
            "UPDATE drafts SET status = 'published', media_id = ? WHERE id = ?", (media_id, draft_id)
        )
        self.db.commit()
