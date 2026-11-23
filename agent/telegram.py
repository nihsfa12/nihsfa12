"""Minimal Telegram Bot API client."""
from __future__ import annotations

from typing import Any

import httpx

MAX_MESSAGE = 4000  # Telegram limit is 4096 characters


class TelegramError(RuntimeError):
    pass


class TelegramClient:
    def __init__(self, token: str, http: httpx.Client | None = None) -> None:
        self._base = f"https://api.telegram.org/bot{token}"
        self._http = http or httpx.Client(timeout=60)

    def _call(self, method: str, files: dict[str, Any] | None = None, **data: Any) -> Any:
        resp = self._http.post(f"{self._base}/{method}", data=data, files=files)
        body = resp.json()
        if not body.get("ok"):
            raise TelegramError(f"{method}: {body.get('description', resp.status_code)}")
        return body["result"]

    def send_message(self, chat_id: str, text: str, parse_mode: str = "HTML") -> list[int]:
        ids = []
        for chunk in split_message(text):
            msg = self._call(
                "sendMessage",
                chat_id=chat_id,
                text=chunk,
                parse_mode=parse_mode,
                disable_web_page_preview="true",
            )
            ids.append(msg["message_id"])
        return ids

    def send_document(self, chat_id: str, filename: str, content: bytes, caption: str = "") -> int:
        msg = self._call(
            "sendDocument",
            files={"document": (filename, content)},
            chat_id=chat_id,
            caption=caption[:1000],
        )
        return msg["message_id"]

    def pin(self, chat_id: str, message_id: int) -> None:
        self._call("pinChatMessage", chat_id=chat_id, message_id=message_id, disable_notification="true")

    def get_updates(self, offset: int | None, timeout: int = 50) -> list[dict[str, Any]]:
        data: dict[str, Any] = {"timeout": timeout}
        if offset is not None:
            data["offset"] = offset
        return self._call("getUpdates", **data)


def split_message(text: str, limit: int = MAX_MESSAGE) -> list[str]:
    """Split on line boundaries so HTML tags opened on a line are closed on it."""
    chunks, current = [], ""
    for line in text.split("\n"):
        while len(line) > limit:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(line[:limit])
            line = line[limit:]
        if len(current) + len(line) + 1 > limit:
            chunks.append(current)
            current = line
        else:
            current = f"{current}\n{line}" if current else line
    if current:
        chunks.append(current)
    return chunks
