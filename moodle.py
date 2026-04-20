"""Moodle AJAX API call module"""

import html as html_mod
import re

import requests


_FORUM_LINK_RE = re.compile(r'/mod/forum/view\.php\?id=(\d+)')
_DISCUSS_LINK_RE = re.compile(r'/mod/forum/discuss\.php\?d=(\d+)')
_TAG_RE = re.compile(r'<[^>]+>')


def _strip_tags(s: str) -> str:
    return html_mod.unescape(_TAG_RE.sub('', s or '')).strip()


def _clean_subject(s: str) -> str:
    return html_mod.unescape((s or '').strip())


def _ajax_call(session: requests.Session, sesskey: str, base_url: str,
               method: str, args: dict) -> dict:
    """Call the Moodle AJAX service endpoint."""
    resp = session.post(
        f"{base_url}/lib/ajax/service.php",
        params={"sesskey": sesskey, "info": method},
        json=[{"index": 0, "methodname": method, "args": args}],
    )
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, list) and data and data[0].get("error"):
        exc = data[0]["exception"]
        raise RuntimeError(f"Moodle API error [{exc['errorcode']}]: {exc['message']}")
    return data[0]["data"]


def get_enrolled_courses(session: requests.Session, sesskey: str,
                         base_url: str) -> list[dict]:
    """Fetch enrolled courses, return normalized course dicts."""
    data = _ajax_call(session, sesskey, base_url,
                      "core_course_get_enrolled_courses_by_timeline_classification",
                      {"classification": "all", "limit": 0, "offset": 0, "sort": "fullname"})
    courses = []
    for c in data["courses"]:
        courses.append({
            "course_id": c["id"],
            "course_name": c["fullname"],
            "course_shortname": c.get("shortname", ""),
            "course_category": c.get("coursecategory", ""),
        })
    return courses


# Moodle surfaces multiple calendar events per activity (one per eventtype:
# `due`, `close`, `expectcompletionon`, `gradingdue`, ...). For a student's
# deadline view we want at most one event per activity, preferring the real
# deadline over the soft completion marker — otherwise the same assignment
# shows up twice under its identical activityname.
_EVENTTYPE_PRIORITY = {
    "due": 0,
    "close": 0,
    "gradingdue": 5,
    "expectcompletionon": 10,
}


def _event_rank(event: dict) -> int:
    return _EVENTTYPE_PRIORITY.get(event.get("eventtype", ""), 3)


def get_action_events(session: requests.Session, sesskey: str,
                      base_url: str, course_ids: list[int]) -> list[dict]:
    """Fetch action events (assignment/quiz deadlines) for all courses.

    Deduplicates per-activity events so each (modulename, instance) yields
    at most one item — the event with the most authoritative eventtype.
    """
    data = _ajax_call(session, sesskey, base_url,
                      "core_calendar_get_action_events_by_courses",
                      {"courseids": course_ids, "timesortfrom": 0})

    chosen: dict[tuple, dict] = {}
    loose: list[dict] = []
    for group in data["groupedbycourse"]:
        for event in group["events"]:
            instance = event.get("instance")
            if instance is None:
                loose.append(event)
                continue
            key = (event.get("modulename"), instance)
            prev = chosen.get(key)
            if prev is None or _event_rank(event) < _event_rank(prev):
                chosen[key] = event

    items = []
    for event in list(chosen.values()) + loose:
        items.append({
            "item_id": event["id"],
            "item_type": event.get("modulename", "unknown"),
            "item_title": event.get("activityname", event.get("name", "")),
            "deadline": event.get("timestart"),
            "item_url": event.get("url", ""),
            "belongs_to": event["course"]["id"],
        })
    return items


def get_forum_discussions(session: requests.Session, sesskey: str,
                          base_url: str, course_ids: list[int]) -> list[dict]:
    """Fetch all visible forum discussions across the given courses.

    Strategy (forum list AJAX endpoints are disabled on ukmfolio, so
    discovery is HTML-scraped and only post content uses AJAX):
      1. GET /course/view.php?id=<cid> -> extract forum cmids
      2. GET /mod/forum/view.php?id=<cmid> -> extract discussion ids
      3. AJAX mod_forum_get_discussion_posts for each discussion -> root post

    Returns item dicts shaped like action events plus item_body:
      item_id:    discussion id
      item_type:  "forum"
      item_title: root post subject (the discussion's visible title)
      deadline:   root post timecreated (unix ts; past, used only as a
                  stable change-detection field, never as a due date)
      item_url:   https://.../mod/forum/discuss.php?d=<id>
      belongs_to: course_id of the first course whose page surfaced the forum
      item_body:  plain-text root post message (stored but NOT compared)
    """
    items = []
    seen_forum_cmids: set[int] = set()

    for course_id in course_ids:
        try:
            r = session.get(f"{base_url}/course/view.php",
                            params={"id": course_id}, timeout=30)
            r.raise_for_status()
        except Exception as e:
            print(f"[WARN] forum scrape failed for course {course_id}: {e}")
            continue

        forum_cmids = sorted({int(m) for m in _FORUM_LINK_RE.findall(r.text)})

        for cmid in forum_cmids:
            # Site-wide forums (e.g. Site announcements) appear on every
            # course page; attribute to the first course we saw them on.
            if cmid in seen_forum_cmids:
                continue
            seen_forum_cmids.add(cmid)

            try:
                fr = session.get(f"{base_url}/mod/forum/view.php",
                                 params={"id": cmid}, timeout=30)
                fr.raise_for_status()
            except Exception as e:
                print(f"[WARN] forum cmid={cmid} fetch failed: {e}")
                continue

            discussion_ids = sorted(
                {int(m) for m in _DISCUSS_LINK_RE.findall(fr.text)})

            for did in discussion_ids:
                try:
                    data = _ajax_call(session, sesskey, base_url,
                                      "mod_forum_get_discussion_posts",
                                      {"discussionid": did})
                except Exception as e:
                    print(f"[WARN] discussion {did} fetch failed: {e}")
                    continue

                posts = data.get("posts") or []
                if not posts:
                    continue
                # Root post = lowest id within the discussion. Robust across
                # Moodle versions that may or may not include parentid/hasparent.
                root = min(posts, key=lambda p: p.get("id") or 0)

                items.append({
                    "item_id":    did,
                    "item_type":  "forum",
                    "item_title": _clean_subject(root.get("subject"))
                                  or f"(discussion {did})",
                    "deadline":   root.get("timecreated"),
                    "item_url":   f"{base_url}/mod/forum/discuss.php?d={did}",
                    "belongs_to": course_id,
                    "item_body":  _strip_tags(root.get("message") or ""),
                })

    return items
