"""Claude-powered analysis: daily summary, post ideas, and comment reply suggestions."""
from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

import anthropic

from .instagram import AccountSnapshot

SYSTEM_PROMPT = """You are a social media strategist managing an Instagram account for its owner.
You receive today's account metrics, yesterday's metrics (if available), and recent posts with
their insights and latest comments. Write for the owner, in the requested language, in a warm,
direct tone. Be specific: refer to actual posts and numbers. Do not invent numbers that are not
in the data. Post ideas must fit the account's niche as shown by its recent captions and the
owner's brief. Captions must be ready to paste. Suggested comment replies must be polite and short,
and only for comments that deserve a reply (questions, compliments, complaints); skip spam."""

ANALYSIS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {"type": "string", "description": "3-5 sentence overview of the day"},
        "highlights": {"type": "array", "items": {"type": "string"}},
        "concerns": {"type": "array", "items": {"type": "string"}},
        "post_ideas": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "format": {"type": "string", "enum": ["image", "carousel", "reel", "story"]},
                    "why": {"type": "string"},
                    "caption": {"type": "string"},
                    "hashtags": {"type": "array", "items": {"type": "string"}},
                    "visual_brief": {
                        "type": "string",
                        "description": "What the photo/video should show, for the owner or a designer",
                    },
                    "best_time": {"type": "string", "description": "Suggested local posting time"},
                },
                "required": ["title", "format", "why", "caption", "hashtags", "visual_brief", "best_time"],
                "additionalProperties": False,
            },
        },
        "comment_replies": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "comment_id": {"type": "string"},
                    "username": {"type": "string"},
                    "comment": {"type": "string"},
                    "suggested_reply": {"type": "string"},
                },
                "required": ["comment_id", "username", "comment", "suggested_reply"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["summary", "highlights", "concerns", "post_ideas", "comment_replies"],
    "additionalProperties": False,
}

LANGUAGE_NAMES = {"fa": "Persian (Farsi)", "en": "English"}


class Strategist:
    def __init__(self, model: str = "claude-opus-5-5", client: anthropic.Anthropic | None = None) -> None:
        self.model = model
        self.client = client or anthropic.Anthropic()

    def analyze(
        self,
        today: AccountSnapshot,
        previous: dict[str, Any] | None,
        language: str = "fa",
        brief: str = "",
        n_ideas: int = 3,
    ) -> dict[str, Any]:
        payload = {
            "today": asdict(today),
            "previous_day": previous,
            "owner_brief": brief or "(none provided)",
        }
        user = (
            f"Language for all output: {LANGUAGE_NAMES.get(language, language)}.\n"
            f"Give exactly {n_ideas} post ideas.\n\n"
            f"<account_data>\n{json.dumps(payload, ensure_ascii=False, indent=1)}\n</account_data>"
        )
        response = self.client.beta.messages.create(
            model=self.model,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user}],
            thinking={"type": "adaptive"},
            output_config={
                "effort": "medium",
                "format": {"type": "json_schema", "schema": ANALYSIS_SCHEMA},
            },
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        if response.stop_reason == "refusal":
            raise RuntimeError("Claude declined to produce the analysis")
        if response.stop_reason == "max_tokens":
            raise RuntimeError("Claude's analysis was cut off (max_tokens)")
        text = next(b.text for b in response.content if b.type == "text")
        return json.loads(text)
