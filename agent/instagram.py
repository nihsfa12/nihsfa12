"""Thin client for the official Instagram Graph API."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

log = logging.getLogger(__name__)

MEDIA_FIELDS = (
    "id,caption,media_type,media_product_type,permalink,timestamp,like_count,comments_count"
)
# Metrics change between Graph API versions; unsupported ones are skipped, not fatal.
MEDIA_METRICS = ("reach", "views", "saved", "shares", "total_interactions")
ACCOUNT_METRICS = ("reach", "profile_views", "accounts_engaged", "total_interactions", "website_clicks")


class InstagramError(RuntimeError):
    pass


@dataclass
class Post:
    id: str
    caption: str
    media_type: str
    permalink: str
    timestamp: str
    like_count: int = 0
    comments_count: int = 0
    insights: dict[str, int] = field(default_factory=dict)
    recent_comments: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class AccountSnapshot:
    username: str
    followers_count: int
    follows_count: int
    media_count: int
    insights: dict[str, int]
    posts: list[Post]


class InstagramClient:
    def __init__(
        self,
        user_id: str,
        access_token: str,
        version: str = "v24.0",
        host: str = "graph.facebook.com",
        http: httpx.Client | None = None,
    ) -> None:
        self.user_id = user_id
        self._token = access_token
        self._base = f"https://{host}/{version}"
        self._http = http or httpx.Client(timeout=30)

    # --- low level -------------------------------------------------------
    def _request(self, method: str, path: str, **params: Any) -> dict[str, Any]:
        params["access_token"] = self._token
        if method == "GET":
            resp = self._http.get(f"{self._base}/{path}", params=params)
        else:
            resp = self._http.post(f"{self._base}/{path}", data=params)
        try:
            body = resp.json()
        except ValueError:
            body = {}
        if resp.status_code >= 400 or "error" in body:
            err = body.get("error", {})
            # Never include the token in error messages.
            raise InstagramError(f"{path}: {err.get('message', resp.status_code)}")
        return body

    # --- reading ---------------------------------------------------------
    def profile(self) -> dict[str, Any]:
        return self._request(
            "GET", self.user_id, fields="username,followers_count,follows_count,media_count"
        )

    def recent_media(self, limit: int = 12) -> list[dict[str, Any]]:
        return self._request("GET", f"{self.user_id}/media", fields=MEDIA_FIELDS, limit=limit).get(
            "data", []
        )

    def media_insights(self, media_id: str) -> dict[str, int]:
        out: dict[str, int] = {}
        for metric in MEDIA_METRICS:  # one by one: a bad metric fails the whole call otherwise
            try:
                body = self._request("GET", f"{media_id}/insights", metric=metric)
            except InstagramError as exc:
                log.debug("skip media metric %s: %s", metric, exc)
                continue
            for item in body.get("data", []):
                values = item.get("values") or [{}]
                out[item["name"]] = int(values[0].get("value", 0) or 0)
        return out

    def account_insights(self, since: int, until: int) -> dict[str, int]:
        out: dict[str, int] = {}
        for metric in ACCOUNT_METRICS:
            try:
                body = self._request(
                    "GET",
                    f"{self.user_id}/insights",
                    metric=metric,
                    period="day",
                    metric_type="total_value",
                    since=since,
                    until=until,
                )
            except InstagramError as exc:
                log.debug("skip account metric %s: %s", metric, exc)
                continue
            for item in body.get("data", []):
                total = (item.get("total_value") or {}).get("value", 0)
                out[item["name"]] = int(total or 0)
        return out

    def comments(self, media_id: str, limit: int = 10) -> list[dict[str, Any]]:
        return self._request(
            "GET", f"{media_id}/comments", fields="id,text,username,timestamp", limit=limit
        ).get("data", [])

    def snapshot(self, since: int, until: int, media_limit: int = 12) -> AccountSnapshot:
        prof = self.profile()
        posts = []
        for m in self.recent_media(media_limit):
            post = Post(
                id=m["id"],
                caption=m.get("caption", ""),
                media_type=m.get("media_product_type") or m.get("media_type", ""),
                permalink=m.get("permalink", ""),
                timestamp=m.get("timestamp", ""),
                like_count=int(m.get("like_count", 0) or 0),
                comments_count=int(m.get("comments_count", 0) or 0),
            )
            post.insights = self.media_insights(post.id)
            if post.comments_count:
                try:
                    post.recent_comments = self.comments(post.id, limit=5)
                except InstagramError as exc:
                    log.debug("skip comments for %s: %s", post.id, exc)
            posts.append(post)
        return AccountSnapshot(
            username=prof.get("username", ""),
            followers_count=int(prof.get("followers_count", 0) or 0),
            follows_count=int(prof.get("follows_count", 0) or 0),
            media_count=int(prof.get("media_count", 0) or 0),
            insights=self.account_insights(since, until),
            posts=posts,
        )

    # --- writing (only ever called after explicit approval) --------------
    def publish_image(self, image_url: str, caption: str) -> str:
        """Publish a single image post. Returns the new media id."""
        container = self._request("POST", f"{self.user_id}/media", image_url=image_url, caption=caption)
        published = self._request("POST", f"{self.user_id}/media_publish", creation_id=container["id"])
        return published["id"]

    def reply_to_comment(self, comment_id: str, message: str) -> str:
        return self._request("POST", f"{comment_id}/replies", message=message)["id"]
