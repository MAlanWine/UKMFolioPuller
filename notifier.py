"""Telegram notification module"""

import time
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


def send_message(bot_token: str, chat_ids, text: str):
    """Send a MarkdownV2 message via Telegram Bot API.

    chat_ids accepts a single chat id (str/int) or a list of chat ids;
    the message is delivered to every target.
    """
    if isinstance(chat_ids, (str, int)):
        targets = [chat_ids]
    else:
        targets = list(chat_ids)

    errors = []
    for cid in targets:
        try:
            resp = requests.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={
                    "chat_id": cid,
                    "text": text,
                    "parse_mode": "MarkdownV2",
                    "disable_web_page_preview": True,
                },
            )
            resp.raise_for_status()
            result = resp.json()
            if not result.get("ok"):
                errors.append(f"{cid}: {result.get('description', 'unknown')}")
        except Exception as e:
            errors.append(f"{cid}: {e}")
    if errors:
        raise RuntimeError("Telegram API error(s): " + "; ".join(errors))


def notify_new_item(bot_token: str, chat_id: str, item: dict, course: dict):
    msg = _build_new_item_message(item, course)
    send_message(bot_token, chat_id, msg)


def notify_changed_item(bot_token: str, chat_id: str, item: dict,
                        course: dict, changes: list[str]):
    msg = _build_changed_item_message(item, course, changes)
    send_message(bot_token, chat_id, msg)


def _build_check_item_message(item: dict, course: dict) -> str:
    """Build Telegram message for a single upcoming deadline."""
    title = _escape_md(item["item_title"])
    itype = _escape_md(item["item_type"])
    deadline = _escape_md(_format_deadline(item.get("deadline")))
    course_info = _escape_md(f"{course['course_shortname']} {course['course_name']}")
    now = int(time.time())
    days_left = (item["deadline"] - now) / 86400
    days_str = _escape_md(f"({days_left:.1f} days left)")
    url = item["item_url"]

    return (
        f"*Upcoming Deadline*\n"
        f"\\- Title:      {title}\n"
        f"\\- Type:       {itype}\n"
        f"\\- Deadline:  {deadline} {days_str}\n"
        f"\\- Course:    {course_info}\n"
        f"\\- Link:       [Open]({url})"
    )


def notify_check_item(bot_token: str, chat_id: str, item: dict, course: dict):
    msg = _build_check_item_message(item, course)
    send_message(bot_token, chat_id, msg)


def notify_no_upcoming(bot_token: str, chat_id: str):
    msg = _escape_md("No assignments/quizzes due within the next 7 days.")
    send_message(bot_token, chat_id, msg)
