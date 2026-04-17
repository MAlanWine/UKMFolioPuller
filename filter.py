"""Title filter module — whitelist/blacklist rules for item titles."""

import re

MODE_DEFAULT = "Default"
MODE_BLACKLIST = "BlackList"
MODE_WHITELIST = "WhiteList"
MODE_DISABLED = "Disabled"
VALID_MODES = {MODE_DEFAULT, MODE_BLACKLIST, MODE_WHITELIST, MODE_DISABLED}


# config `listen_filed` maps user-facing labels to internal `item_type` values
_LISTEN_LABEL_TO_TYPE = {
    "Quiz":       "quiz",
    "Assignment": "assign",
    "Form":       "forum",
}
VALID_LISTEN_LABELS = tuple(_LISTEN_LABEL_TO_TYPE.keys())


def parse_listen_field(raw) -> set[str] | None:
    """Parse config['listen_filed'] into the set of internal item_types to monitor.

    Returns None (monitor every supported type) when the field is absent,
    malformed, empty, or contains no valid labels. Returns a set of internal
    type strings (subset of {'quiz', 'assign', 'forum'}) otherwise.

    All deviations (wrong shape, unknown labels, all-invalid) emit [WARN] prints
    so misconfigurations are never silent.
    """
    if raw is None:
        return None
    if not isinstance(raw, list):
        print(f"[WARN] 'listen_filed' must be a list of strings; got "
              f"{type(raw).__name__}. Falling back to default (listen to all).")
        return None
    if len(raw) == 0:
        print("[WARN] 'listen_filed' is an empty array. "
              "Falling back to default (listen to all).")
        return None

    accepted: set[str] = set()
    for entry in raw:
        if isinstance(entry, str) and entry in _LISTEN_LABEL_TO_TYPE:
            accepted.add(_LISTEN_LABEL_TO_TYPE[entry])
        else:
            print(f"[WARN] 'listen_filed' entry {entry!r} is not one of "
                  f"{list(VALID_LISTEN_LABELS)}; ignoring.")

    if not accepted:
        print(f"[WARN] 'listen_filed' contains no valid entries "
              f"(valid labels: {list(VALID_LISTEN_LABELS)}). "
              f"Falling back to default (listen to all).")
        return None
    return accepted


def filter_by_type(items: list[dict], listen_types: set[str] | None) -> list[dict]:
    """Keep only items whose item_type is in listen_types. None means keep all."""
    if listen_types is None:
        return items
    kept = [i for i in items if i.get("item_type") in listen_types]
    dropped = len(items) - len(kept)
    if dropped > 0:
        print(f"[*] Type filter: dropped {dropped} of {len(items)} items "
              f"(listening to {sorted(listen_types)}).")
    return kept


def _compile_patterns(patterns: list[str] | None) -> list[re.Pattern]:
    compiled = []
    for p in patterns or []:
        try:
            compiled.append(re.compile(p))
        except re.error as e:
            print(f"[WARN] Invalid filter regex '{p}': {e}")
    return compiled


def _match_any(regexes: list[re.Pattern], text: str) -> bool:
    return any(r.search(text) for r in regexes)


def apply_filter(items: list[dict], filter_config: dict | None) -> list[dict]:
    """
    Filter items by title according to filter_config.

    filter_config schema:
        {
            "mode": "Default" | "BlackList" | "WhiteList" | "Disabled",
            "whitelist": [regex, ...],
            "blacklist": [regex, ...]
        }

    Modes:
    - Default:   pass if matches whitelist; drop if matches blacklist; otherwise pass.
    - BlackList: drop if matches blacklist; otherwise pass.
    - WhiteList: pass only if matches whitelist; otherwise drop.
    - Disabled:  pass all items.
    """
    if not filter_config:
        return items
    mode = filter_config.get("mode", MODE_DEFAULT)
    if mode not in VALID_MODES:
        print(f"[WARN] Unknown filter mode '{mode}', falling back to Default.")
        mode = MODE_DEFAULT
    if mode == MODE_DISABLED:
        return items

    whitelist = _compile_patterns(filter_config.get("whitelist"))
    blacklist = _compile_patterns(filter_config.get("blacklist"))

    result = []
    for item in items:
        title = item.get("item_title", "") or ""
        if mode == MODE_WHITELIST:
            if _match_any(whitelist, title):
                result.append(item)
        elif mode == MODE_BLACKLIST:
            if not _match_any(blacklist, title):
                result.append(item)
        else:  # Default
            if _match_any(whitelist, title):
                result.append(item)
            elif _match_any(blacklist, title):
                continue
            else:
                result.append(item)

    dropped = len(items) - len(result)
    if dropped > 0:
        print(f"[*] Filter ({mode}): dropped {dropped} of {len(items)} items.")
    return result
