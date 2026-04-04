"""Moodle AJAX API call module"""

import requests


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


def get_action_events(session: requests.Session, sesskey: str,
                      base_url: str, course_ids: list[int]) -> list[dict]:
    """Fetch action events (assignment/quiz deadlines) for all courses."""
    data = _ajax_call(session, sesskey, base_url,
                      "core_calendar_get_action_events_by_courses",
                      {"courseids": course_ids, "timesortfrom": 0})
    items = []
    for group in data["groupedbycourse"]:
        for event in group["events"]:
            items.append({
                "item_id": event["id"],
                "item_type": event.get("modulename", "unknown"),
                "item_title": event.get("activityname", event.get("name", "")),
                "deadline": event.get("timestart"),
                "item_url": event.get("url", ""),
                "belongs_to": event["course"]["id"],
            })
    return items
