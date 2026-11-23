"""Turn a snapshot + Claude analysis into a Telegram message and a Markdown archive file."""
from __future__ import annotations

from html import escape
from typing import Any

from .instagram import AccountSnapshot

METRIC_LABELS_FA = {
    "followers_count": "دنبال‌کننده",
    "reach": "دسترسی (Reach)",
    "profile_views": "بازدید پروفایل",
    "accounts_engaged": "حساب‌های درگیر",
    "total_interactions": "کل تعاملات",
    "website_clicks": "کلیک لینک",
}


def _delta(now: int, before: int | None) -> str:
    if before is None:
        return ""
    diff = now - before
    sign = "+" if diff >= 0 else ""
    return f" ({sign}{diff})"


def metrics(snap: AccountSnapshot, prev: dict[str, Any] | None) -> list[tuple[str, int, str]]:
    rows = [("followers_count", snap.followers_count, _delta(snap.followers_count, prev and prev.get("followers_count")))]
    prev_ins = (prev or {}).get("insights", {})
    for key, value in snap.insights.items():
        rows.append((key, value, _delta(value, prev_ins.get(key))))
    return [(METRIC_LABELS_FA.get(k, k), v, d) for k, v, d in rows]


def top_posts(snap: AccountSnapshot, n: int = 3) -> list:
    def score(p):
        return p.insights.get("total_interactions") or (p.like_count + p.comments_count)

    return sorted(snap.posts, key=score, reverse=True)[:n]


def telegram_html(day: str, snap: AccountSnapshot, prev: dict[str, Any] | None, analysis: dict[str, Any], draft_ids: list[int]) -> str:
    e = escape
    lines = [f"<b>📊 گزارش روزانه اینستاگرام @{e(snap.username)}</b>", f"📅 {e(day)}", ""]
    lines.append("<b>آمار</b>")
    for label, value, delta in metrics(snap, prev):
        lines.append(f"• {e(label)}: <b>{value:,}</b>{e(delta)}")
    lines += ["", "<b>خلاصه</b>", e(analysis["summary"])]
    if analysis["highlights"]:
        lines += ["", "<b>✅ نکات مثبت</b>"] + [f"• {e(h)}" for h in analysis["highlights"]]
    if analysis["concerns"]:
        lines += ["", "<b>⚠️ نیاز به توجه</b>"] + [f"• {e(c)}" for c in analysis["concerns"]]
    tops = top_posts(snap)
    if tops:
        lines += ["", "<b>🏆 پست‌های برتر</b>"]
        for p in tops:
            title = e((p.caption or "بدون کپشن").split("\n")[0][:60])
            lines.append(f"• <a href=\"{e(p.permalink)}\">{title}</a> ❤️{p.like_count} 💬{p.comments_count}")
    if analysis["post_ideas"]:
        lines += ["", "<b>💡 پیشنهاد پست</b>"]
        for idea, did in zip(analysis["post_ideas"], draft_ids):
            lines.append(f"<b>#{did} {e(idea['title'])}</b> ({e(idea['format'])}، {e(idea['best_time'])})")
            lines.append(f"<i>{e(idea['why'])}</i>")
        lines.append("متن کامل در فایل گزارش است. برای انتشار: <code>/publish شماره لینک‌عکس</code>")
    if analysis["comment_replies"]:
        lines += ["", f"<b>💬 {len(analysis['comment_replies'])} کامنت منتظر پاسخ</b> (پیشنهاد پاسخ در فایل)"]
    return "\n".join(lines)


def markdown(day: str, snap: AccountSnapshot, prev: dict[str, Any] | None, analysis: dict[str, Any], draft_ids: list[int]) -> str:
    out = [f"# گزارش روزانه اینستاگرام @{snap.username} — {day}", "", "## آمار", ""]
    out += [f"- {label}: **{value:,}**{delta}" for label, value, delta in metrics(snap, prev)]
    out += ["", "## خلاصه", "", analysis["summary"], ""]
    if analysis["highlights"]:
        out += ["## نکات مثبت", ""] + [f"- {h}" for h in analysis["highlights"]] + [""]
    if analysis["concerns"]:
        out += ["## نیاز به توجه", ""] + [f"- {c}" for c in analysis["concerns"]] + [""]
    out += ["## پست‌های اخیر", "", "| پست | نوع | لایک | کامنت | Reach | ذخیره |", "|---|---|---|---|---|---|"]
    for p in snap.posts:
        title = (p.caption or "بدون کپشن").split("\n")[0][:40].replace("|", "/")
        out.append(
            f"| [{title}]({p.permalink}) | {p.media_type} | {p.like_count} | {p.comments_count}"
            f" | {p.insights.get('reach', '-')} | {p.insights.get('saved', '-')} |"
        )
    out.append("")
    if analysis["post_ideas"]:
        out += ["## پیشنهاد پست (پیش‌نویس)", ""]
        for idea, did in zip(analysis["post_ideas"], draft_ids):
            out += [
                f"### #{did} {idea['title']}",
                f"- قالب: {idea['format']} — زمان پیشنهادی: {idea['best_time']}",
                f"- چرا: {idea['why']}",
                f"- تصویر/ویدیو: {idea['visual_brief']}",
                "",
                "```",
                idea["caption"],
                "",
                " ".join(idea["hashtags"]),
                "```",
                "",
            ]
    if analysis["comment_replies"]:
        out += ["## پیشنهاد پاسخ به کامنت‌ها", ""]
        for c in analysis["comment_replies"]:
            out += [f"- **@{c['username']}**: {c['comment']}", f"  - پاسخ پیشنهادی: {c['suggested_reply']}", f"  - `/reply {c['comment_id']} متن`"]
    return "\n".join(out) + "\n"
