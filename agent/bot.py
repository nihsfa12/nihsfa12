"""Telegram bot: on-demand reports and approve-before-publish actions.

Only the configured TELEGRAM_CHAT_ID may use it. Nothing is ever posted to
Instagram without an explicit /confirm from that chat.
"""
from __future__ import annotations

import logging
from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo
from typing import Any, Callable

from .config import Config
from .instagram import InstagramClient, InstagramError
from .storage import Store
from .telegram import TelegramClient

log = logging.getLogger(__name__)

HELP = """<b>دستورات</b>
/report — ساخت و ارسال گزارش همین الان
/drafts — فهرست پیش‌نویس‌های پست
/draft N — متن کامل پیش‌نویس شماره N
/publish N لینک‌عکس — پیش‌نمایش انتشار پیش‌نویس N با عکس (لینک عمومی https)
/confirm N — انتشار نهایی پیش‌نویس N در اینستاگرام
/reply شناسه‌کامنت متن — پاسخ به یک کامنت
/cancel — لغو انتشار در انتظار"""


class Bot:
    def __init__(self, cfg: Config, tg: TelegramClient, ig: InstagramClient, store: Store, run_report: Callable[[], Any]) -> None:
        self.cfg, self.tg, self.ig, self.store = cfg, tg, ig, store
        self.run_report = run_report
        self.pending: dict[int, str] = {}  # draft id -> image url awaiting /confirm
        self._last_scheduled: str | None = None

    def say(self, text: str) -> None:
        self.tg.send_message(self.cfg.telegram_chat_id, text)

    def handle(self, update: dict[str, Any]) -> None:
        msg = update.get("message") or {}
        if str(msg.get("chat", {}).get("id")) != str(self.cfg.telegram_chat_id):
            return  # ignore everyone except the owner
        text = (msg.get("text") or "").strip()
        if not text.startswith("/"):
            return
        cmd, _, rest = text.partition(" ")
        cmd = cmd.split("@")[0].lower()
        try:
            self.dispatch(cmd, rest.strip())
        except (InstagramError, ValueError) as exc:
            self.say(f"❌ {escape(str(exc))}")

    def dispatch(self, cmd: str, args: str) -> None:
        if cmd in ("/start", "/help"):
            self.say(HELP)
        elif cmd == "/report":
            self.say("⏳ در حال ساخت گزارش…")
            self.run_report()
        elif cmd == "/drafts":
            drafts = self.store.list_drafts()
            if not drafts:
                self.say("پیش‌نویسی وجود ندارد.")
            else:
                self.say("\n".join(f"#{d['id']} {escape(d['title'])} ({escape(d['format'])})" for d in drafts))
        elif cmd == "/draft":
            d = self._draft(args)
            self.say(
                f"<b>#{d['id']} {escape(d['title'])}</b>\n🖼 {escape(d['visual_brief'])}\n⏰ {escape(d['best_time'])}\n\n"
                f"<pre>{escape(d['caption'])}\n\n{escape(d['hashtags'])}</pre>"
            )
        elif cmd == "/publish":
            num, _, url = args.partition(" ")
            d = self._draft(num)
            url = url.strip()
            if not url.startswith("https://"):
                raise ValueError("لینک عکس باید یک آدرس عمومی https باشد")
            if d["format"] != "image":
                self.say("ℹ️ این MVP فعلاً فقط پست تک‌عکس منتشر می‌کند؛ این پیش‌نویس به‌صورت عکس منتشر می‌شود.")
            self.pending[d["id"]] = url
            self.say(
                f"پیش‌نمایش انتشار #{d['id']}:\n{escape(url)}\n\n<pre>{escape(d['caption'])}\n\n{escape(d['hashtags'])}</pre>\n"
                f"برای انتشار بفرستید: <code>/confirm {d['id']}</code>"
            )
        elif cmd == "/confirm":
            d = self._draft(args)
            url = self.pending.pop(d["id"], None)
            if not url:
                raise ValueError("اول /publish را برای این پیش‌نویس بفرستید")
            media_id = self.ig.publish_image(url, f"{d['caption']}\n\n{d['hashtags']}")
            self.store.mark_published(d["id"], media_id)
            self.say(f"✅ پیش‌نویس #{d['id']} منتشر شد.")
        elif cmd == "/cancel":
            self.pending.clear()
            self.say("لغو شد.")
        elif cmd == "/reply":
            comment_id, _, message = args.partition(" ")
            if not comment_id or not message.strip():
                raise ValueError("فرمت: /reply شناسه‌کامنت متن")
            self.ig.reply_to_comment(comment_id, message.strip())
            self.say("✅ پاسخ ارسال شد.")
        else:
            self.say(HELP)

    def _draft(self, num: str) -> dict[str, Any]:
        if not num.strip().lstrip("#").isdigit():
            raise ValueError("شماره پیش‌نویس را وارد کنید")
        d = self.store.get_draft(int(num.strip().lstrip("#")))
        if not d:
            raise ValueError("پیش‌نویس پیدا نشد")
        return d

    def maybe_run_scheduled(self, daily_at: str | None, now: datetime | None = None) -> bool:
        """Run the daily report once per day at or after daily_at (HH:MM, local time)."""
        if not daily_at:
            return False
        now = now or datetime.now(ZoneInfo(self.cfg.timezone))
        today = now.date().isoformat()
        if now.strftime("%H:%M") < daily_at or self._last_scheduled == today:
            return False
        self._last_scheduled = today
        try:
            self.run_report()
        except Exception:
            log.exception("scheduled report failed")
            self.say("❌ گزارش زمان‌بندی‌شده با خطا مواجه شد؛ جزئیات در لاگ.")
        return True

    def run_forever(self, daily_at: str | None = None) -> None:
        offset = None
        log.info("bot polling started (daily report at %s)", daily_at or "off")
        while True:
            self.maybe_run_scheduled(daily_at)
            try:
                updates = self.tg.get_updates(offset)
            except Exception as exc:  # network hiccups shouldn't kill the bot
                log.warning("getUpdates failed: %s", exc)
                continue
            for upd in updates:
                offset = upd["update_id"] + 1
                try:
                    self.handle(upd)
                except Exception:
                    log.exception("failed to handle update")
                    self.say("❌ خطای داخلی؛ جزئیات در لاگ.")
