"""UKMFolio Checker - main entry point"""

import argparse
import sys
import time
from datetime import datetime, timezone

from auth import load_config, login
from db import init_db, upsert_courses, get_all_items, get_course_info, \
    insert_items, update_item, delete_items
from moodle import get_enrolled_courses, get_action_events
from notifier import notify_new_item, notify_changed_item


def check_config(config: dict, need_telegram: bool = True):
    """Validate config completeness."""
    required = ["username", "password", "base_url", "sso_url"]
    if need_telegram:
        required += ["telegram_bot_token", "telegram_target_user_uuid"]
    missing = [k for k in required if not config.get(k)]
    if missing:
        print(f"[ERROR] Missing fields in config.json: {', '.join(missing)}")
        sys.exit(1)


def detect_changes(api_items: list[dict], db_items: dict[int, dict]):
    """
    Compare API items against database items.

    Returns:
        (new_items, changed_items, deleted_ids)
        changed_items is a list of (item_dict, changes_list)
    """
    api_ids = {item["item_id"] for item in api_items}
    db_ids = set(db_items.keys())

    new_items = [item for item in api_items if item["item_id"] not in db_ids]

    changed_items = []
    for item in api_items:
        if item["item_id"] in db_ids:
            old = db_items[item["item_id"]]
            changes = []
            if old["item_title"] != item["item_title"]:
                changes.append(f"Title: '{old['item_title']}' -> '{item['item_title']}'")
            if old["deadline"] != item["deadline"]:
                changes.append(f"Deadline changed")
            if changes:
                changed_items.append((item, changes))

    deleted_ids = list(db_ids - api_ids)

    return new_items, changed_items, deleted_ids


def cmd_check(config: dict):
    """List assignments/quizzes due within the next 7 days to stdout."""
    check_config(config, need_telegram=False)
    base_url = config["base_url"]

    session, sesskey = login(config)
    courses = get_enrolled_courses(session, sesskey, base_url)
    if not courses:
        print("No enrolled courses.")
        return

    course_map = {c["course_id"]: c for c in courses}
    course_ids = list(course_map.keys())
    api_items = get_action_events(session, sesskey, base_url, course_ids)

    now = int(time.time())
    one_week = now + 7 * 24 * 3600
    upcoming = [i for i in api_items if i.get("deadline") and now <= i["deadline"] <= one_week]
    upcoming.sort(key=lambda i: i["deadline"])

    if not upcoming:
        print("No assignments/quizzes due within the next 7 days.")
        return

    print(f"{'Deadline':^20s} | {'Type':^6s} | {'Course':^12s} | Title")
    print("-" * 80)
    for item in upcoming:
        dl = datetime.fromtimestamp(item["deadline"], tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
        days_left = (item["deadline"] - now) / 86400
        course = course_map.get(item["belongs_to"], {})
        shortname = course.get("course_shortname", "?")
        tag = f"({days_left:.1f}d left)"
        print(f"{dl} {tag:>11s} | {item['item_type']:^6s} | {shortname:^12s} | {item['item_title']}")


def main():
    parser = argparse.ArgumentParser(description="UKMFolio Assignment Checker")
    parser.add_argument("command", nargs="?", default=None,
                        help="Subcommand: 'check' to list upcoming deadlines")
    parser.add_argument("--initct", action="store_true",
                        help="Init Content: first run, populate DB without sending notifications")
    args = parser.parse_args()

    if args.command == "check":
        config = load_config()
        cmd_check(config)
        return

    # 1. Load config
    print("[*] Loading config...")
    config = load_config()
    check_config(config, need_telegram=not args.initct)

    bot_token = config["telegram_bot_token"]
    chat_id = config["telegram_target_user_uuid"]
    base_url = config["base_url"]

    # 2. Initialize database
    print("[*] Initializing database...")
    init_db()

    # 3. Login
    print("[*] Logging in via SAML SSO...")
    try:
        session, sesskey = login(config)
    except RuntimeError as e:
        print(f"[ERROR] Login failed: {e}")
        sys.exit(1)
    print("[*] Login successful.")

    # 4. Fetch enrolled courses
    print("[*] Fetching enrolled courses...")
    courses = get_enrolled_courses(session, sesskey, base_url)
    if not courses:
        print("[WARN] No enrolled courses found.")
        sys.exit(0)
    upsert_courses(courses)
    course_ids = [c["course_id"] for c in courses]
    print(f"[*] Found {len(courses)} courses.")

    # 5. Fetch action events
    print("[*] Fetching action events (assignments/quizzes)...")
    api_items = get_action_events(session, sesskey, base_url, course_ids)
    print(f"[*] Found {len(api_items)} action events.")

    # 6. Detect changes
    db_items = get_all_items()
    new_items, changed_items, deleted_ids = detect_changes(api_items, db_items)

    print(f"[*] Changes: {len(new_items)} new, {len(changed_items)} changed, "
          f"{len(deleted_ids)} removed.")

    # 7. Handle new items
    if new_items:
        insert_items(new_items)
        if not args.initct:
            for item in new_items:
                course = get_course_info(item["belongs_to"])
                if course:
                    try:
                        notify_new_item(bot_token, chat_id, item, course)
                    except Exception as e:
                        print(f"[WARN] Failed to send notification: {e}")

    # 8. Handle changed items
    if changed_items:
        for item, changes in changed_items:
            update_item(item)
            if not args.initct:
                course = get_course_info(item["belongs_to"])
                if course:
                    try:
                        notify_changed_item(bot_token, chat_id, item, course, changes)
                    except Exception as e:
                        print(f"[WARN] Failed to send notification: {e}")

    # 9. Handle deleted items
    if deleted_ids:
        delete_items(deleted_ids)

    print("[*] Done.")


if __name__ == "__main__":
    main()
