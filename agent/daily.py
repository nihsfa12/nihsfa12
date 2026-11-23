"""The daily job: collect Instagram data, analyze with Claude, report to Telegram."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .config import Config
from .ideas import Strategist
from .instagram import InstagramClient
from .report import markdown, telegram_html
from .storage import Store
from .telegram import TelegramClient

log = logging.getLogger(__name__)


def run_daily(cfg: Config, ig: InstagramClient | None = None, strategist: Strategist | None = None, tg: TelegramClient | None = None) -> str:
    tz = ZoneInfo(cfg.timezone)
    now = datetime.now(tz)
    day = now.date().isoformat()
    since = int((now - timedelta(days=1)).timestamp())
    until = int(now.timestamp())

    ig = ig or InstagramClient(cfg.ig_user_id, cfg.ig_access_token, cfg.ig_graph_version, cfg.ig_graph_host)
    strategist = strategist or Strategist(cfg.claude_model)
    tg = tg or TelegramClient(cfg.telegram_bot_token)
    store = Store(cfg.data_dir)

    log.info("collecting Instagram data")
    snap = ig.snapshot(since, until)
    prev = store.previous_snapshot(day)
    store.save_snapshot(day, snap)

    log.info("analyzing with %s", cfg.claude_model)
    analysis = strategist.analyze(snap, prev, cfg.report_language, cfg.account_brief)
    draft_ids = [store.add_draft(idea) for idea in analysis["post_ideas"]]

    md = markdown(day, snap, prev, analysis, draft_ids)
    reports_dir = cfg.data_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / f"{day}.md").write_text(md, encoding="utf-8")

    log.info("sending report to Telegram")
    tg.send_message(cfg.telegram_chat_id, telegram_html(day, snap, prev, analysis, draft_ids))
    # The file in the chat is the permanent, searchable archive of each day's report.
    tg.send_document(cfg.telegram_chat_id, f"instagram-report-{day}.md", md.encode("utf-8"), caption=f"#گزارش_روزانه {day}")
    return md
