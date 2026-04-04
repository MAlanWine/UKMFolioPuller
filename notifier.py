"""Telegram notification module"""

from datetime import datetime, timezone

import requests


def _format_deadline(ts: int | None) -> str:
    if ts is None or ts == 0:
        return "No deadline"
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M UTC")


def _escape_md(text: str) -> str:
    """Escape Telegram MarkdownV2 special characters."""
    special = r"_*[]()~`>#+-=|{}.!"
    for ch in special:
        text = text.replace(ch, f"\\{ch}")
    return text


def _build_new_item_message(item: dict, course: dict) -> str:
    title = _escape_md(item["item_title"])
    itype = _escape_md(item["item_type"])
    deadline = _escape_md(_format_deadline(item.get("deadline")))
    course_info = _escape_md(f"{course['course_shortname']} {course['course_name']}")
    url = item["item_url"]

    return (
        f"*New Assignment/Quiz*\n"
        f"\\- Title:      {title}\n"
        f"\\- Type:       {itype}\n"
        f"\\- Deadline:  {deadline}\n"
        f"\\- Course:    {course_info}\n"
        f"\\- Link:       [Open]({url})"
    )


def _build_changed_item_message(item: dict, course: dict, changes: list[str]) -> str:
    title = _escape_md(item["item_title"])
    itype = _escape_md(item["item_type"])
    deadline = _escape_md(_format_deadline(item.get("deadline")))
    course_info = _escape_md(f"{course['course_shortname']} {course['course_name']}")
    changes_str = _escape_md(", ".join(changes))
    url = item["item_url"]

    return (
        f"*Content Changed*\n"
        f"\\- Title:      {title}\n"
        f"\\- Type:       {itype}\n"
        f"\\- Deadline:  {deadline}\n"
        f"\\- Course:    {course_info}\n"
        f"\\- Link:       [Open]({url})\n"
        f"\\- Changes:  {changes_str}"
    )


def send_message(bot_token: str, chat_id: str, text: str):
    """Send a MarkdownV2 message via Telegram Bot API."""
    resp = requests.post(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "MarkdownV2",
            "disable_web_page_preview": True,
        },
    )
    resp.raise_for_status()
    result = resp.json()
    if not result.get("ok"):
        raise RuntimeError(f"Telegram API error: {result.get('description', 'unknown')}")


def notify_new_item(bot_token: str, chat_id: str, item: dict, course: dict):
    msg = _build_new_item_message(item, course)
    send_message(bot_token, chat_id, msg)


def notify_changed_item(bot_token: str, chat_id: str, item: dict,
                        course: dict, changes: list[str]):
    msg = _build_changed_item_message(item, course, changes)
    send_message(bot_token, chat_id, msg)
