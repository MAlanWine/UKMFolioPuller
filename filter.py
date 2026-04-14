"""Title filter module — whitelist/blacklist rules for item titles."""

import re

MODE_DEFAULT = "Default"
MODE_BLACKLIST = "BlackList"
MODE_WHITELIST = "WhiteList"
MODE_DISABLED = "Disabled"
VALID_MODES = {MODE_DEFAULT, MODE_BLACKLIST, MODE_WHITELIST, MODE_DISABLED}


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
