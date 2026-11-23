import json
from pathlib import Path
from types import SimpleNamespace

import httpx

from agent.bot import Bot
from agent.config import Config
from agent.daily import run_daily
from agent.ideas import Strategist
from agent.instagram import InstagramClient
from agent.storage import Store
from agent.telegram import TelegramClient, split_message

ANALYSIS = {
    "summary": "روز خوبی بود <و رشد داشتیم>",
    "highlights": ["ریل دیروز عالی بود"],
    "concerns": [],
    "post_ideas": [
        {"title": "پشت صحنه", "format": "image", "why": "مخاطب دوست دارد", "caption": "سلام!",
         "hashtags": ["#a", "#b"], "visual_brief": "عکس میز کار", "best_time": "20:00"},
    ],
    "comment_replies": [
        {"comment_id": "c1", "username": "ali", "comment": "قیمت؟", "suggested_reply": "دایرکت بدید"},
    ],
}


def graph_handler(calls):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        path = request.url.path
        if request.method == "POST" and path.endswith("/media"):
            return httpx.Response(200, json={"id": "container1"})
        if path.endswith("/media_publish"):
            return httpx.Response(200, json={"id": "media99"})
        if path.endswith("/replies"):
            return httpx.Response(200, json={"id": "r1"})
        if path.endswith("/insights") and "/123/" in path:
            metric = request.url.params["metric"]
            if metric == "website_clicks":
                return httpx.Response(400, json={"error": {"message": "unsupported"}})
            return httpx.Response(200, json={"data": [{"name": metric, "total_value": {"value": 50}}]})
        if path.endswith("/insights"):
            metric = request.url.params["metric"]
            if metric == "views":
                return httpx.Response(400, json={"error": {"message": "unsupported"}})
            return httpx.Response(200, json={"data": [{"name": metric, "values": [{"value": 7}]}]})
        if path.endswith("/comments"):
            return httpx.Response(200, json={"data": [{"id": "c1", "text": "قیمت؟", "username": "ali"}]})
        if path.endswith("/123/media"):
            return httpx.Response(200, json={"data": [
                {"id": "m1", "caption": "اولین پست", "media_type": "IMAGE", "permalink": "https://instagram.com/p/1",
                 "timestamp": "2026-11-22T10:00:00+0000", "like_count": 10, "comments_count": 1},
            ]})
        if path.endswith("/123"):
            return httpx.Response(200, json={"username": "shop", "followers_count": 1000, "follows_count": 5, "media_count": 1})
        return httpx.Response(404, json={"error": {"message": "nope"}})
    return handler


def make_ig(calls):
    return InstagramClient("123", "SECRET", http=httpx.Client(transport=httpx.MockTransport(graph_handler(calls))))


class FakeTelegram(TelegramClient):
    def __init__(self):
        self.messages, self.documents = [], []

    def send_message(self, chat_id, text, parse_mode="HTML"):
        self.messages.append(text)
        return [1]

    def send_document(self, chat_id, filename, content, caption=""):
        self.documents.append((filename, content.decode()))
        return 2


def cfg(tmp_path: Path) -> Config:
    return Config(None, "claude-opus-5-5", "123", "SECRET", "v24.0", "graph.facebook.com", "T", "42",
                  tmp_path, "fa", "Asia/Tehran", "")


def test_snapshot_skips_unsupported_metrics():
    snap = make_ig([]).snapshot(0, 1)
    assert snap.username == "shop" and snap.followers_count == 1000
    assert "website_clicks" not in snap.insights and snap.insights["reach"] == 50
    assert "views" not in snap.posts[0].insights and snap.posts[0].insights["saved"] == 7
    assert snap.posts[0].recent_comments[0]["id"] == "c1"


def test_errors_do_not_leak_token():
    ig = make_ig([])
    try:
        ig._request("GET", "unknown")
    except Exception as exc:
        assert "SECRET" not in str(exc)


def test_strategist_sends_structured_request():
    captured = {}

    def create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=json.dumps(ANALYSIS))])

    fake = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)))
    out = Strategist(client=fake).analyze(make_ig([]).snapshot(0, 1), None)
    assert out["post_ideas"][0]["title"] == "پشت صحنه"
    assert captured["model"] == "claude-opus-5-5"
    assert captured["output_config"]["format"]["type"] == "json_schema"
    assert "Persian" in captured["messages"][0]["content"]


def test_daily_end_to_end(tmp_path):
    strategist = SimpleNamespace(analyze=lambda *a, **k: ANALYSIS)
    tg = FakeTelegram()
    md = run_daily(cfg(tmp_path), ig=make_ig([]), strategist=strategist, tg=tg)
    assert "@shop" in tg.messages[0]
    assert "&lt;و رشد داشتیم&gt;" in tg.messages[0]  # HTML escaped
    assert tg.documents[0][0].startswith("instagram-report-")
    assert "/reply c1" in md
    assert list((tmp_path / "reports").glob("*.md"))
    assert Store(tmp_path).list_drafts()[0]["title"] == "پشت صحنه"


def test_publish_requires_confirm(tmp_path):
    calls = []
    store = Store(tmp_path)
    did = store.add_draft(ANALYSIS["post_ideas"][0])
    tg = FakeTelegram()
    bot = Bot(cfg(tmp_path), tg, make_ig(calls), store, run_report=lambda: None)

    def send(text, chat="42"):
        bot.handle({"message": {"chat": {"id": chat}, "text": text}})

    send(f"/confirm {did}")
    assert "اول /publish" in tg.messages[-1]
    send(f"/publish {did} https://example.com/a.jpg")
    assert not any(c.method == "POST" for c in calls)
    send(f"/confirm {did}", chat="999")  # stranger is ignored
    assert not any(c.method == "POST" for c in calls)
    send(f"/confirm {did}")
    assert "منتشر شد" in tg.messages[-1]
    assert store.get_draft(did)["status"] == "published"


def test_split_message():
    text = "\n".join(["x" * 100] * 100)
    chunks = split_message(text, limit=1000)
    assert all(len(c) <= 1000 for c in chunks)
    assert "\n".join(chunks) == text


def test_scheduled_report_runs_once_per_day(tmp_path):
    from datetime import datetime
    ran = []
    bot = Bot(cfg(tmp_path), FakeTelegram(), make_ig([]), Store(tmp_path), run_report=lambda: ran.append(1))
    assert not bot.maybe_run_scheduled("09:00", datetime(2026, 11, 24, 8, 59))
    assert bot.maybe_run_scheduled("09:00", datetime(2026, 11, 24, 9, 0))
    assert not bot.maybe_run_scheduled("09:00", datetime(2026, 11, 24, 15, 0))
    assert bot.maybe_run_scheduled("09:00", datetime(2026, 11, 25, 9, 5))
    assert len(ran) == 2
