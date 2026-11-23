"""CLI: python -m agent {daily|bot|check}"""
from __future__ import annotations

import argparse
import logging
import sys

from .config import Config, ConfigError

REQUIRED = ("ig_user_id", "ig_access_token", "telegram_bot_token", "telegram_chat_id")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agent")
    parser.add_argument("command", choices=["daily", "bot", "check"])
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--daily-at", metavar="HH:MM", help="bot only: also send the daily report at this local time")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # its URLs contain tokens

    try:
        cfg = Config.from_env(require=REQUIRED)
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 2

    from .daily import run_daily
    from .instagram import InstagramClient
    from .telegram import TelegramClient

    if args.command == "check":
        ig = InstagramClient(cfg.ig_user_id, cfg.ig_access_token, cfg.ig_graph_version, cfg.ig_graph_host)
        prof = ig.profile()
        print(f"Instagram OK: @{prof.get('username')} ({prof.get('followers_count')} followers)")
        TelegramClient(cfg.telegram_bot_token).send_message(cfg.telegram_chat_id, "✅ اتصال ایجنت به تلگرام برقرار است.")
        print("Telegram OK")
        return 0
    if args.command == "daily":
        run_daily(cfg)
        return 0

    from .bot import Bot
    from .storage import Store

    tg = TelegramClient(cfg.telegram_bot_token)
    ig = InstagramClient(cfg.ig_user_id, cfg.ig_access_token, cfg.ig_graph_version, cfg.ig_graph_host)
    Bot(cfg, tg, ig, Store(cfg.data_dir), run_report=lambda: run_daily(cfg, ig=ig, tg=tg)).run_forever(args.daily_at)
    return 0


if __name__ == "__main__":
    sys.exit(main())
