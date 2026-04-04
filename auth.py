"""
UKMFolio SAML SSO login module

Login flow (SAML 2.0):
1. GET ukmfolio.ukm.my/login/index.php -> 302 -> sso.ukm.my/saml2/idp/SSOService.php?SAMLRequest=...
2. GET SSOService.php -> 302 -> sso.ukm.my/module.php/core/loginuserpass.php?AuthState=...
3. GET loginuserpass.php -> 200 -> login form (extract AuthState hidden field)
4. POST loginuserpass.php -> 200 -> auto-submit form (contains SAMLResponse)
5. POST ukmfolio.ukm.my/auth/saml2/sp/saml2-acs.php/... -> 302 -> login complete
6. Extract sesskey from page for subsequent AJAX calls
"""

import json
import re
from pathlib import Path
from html.parser import HTMLParser

import requests


CONFIG_PATH = Path(__file__).parent / "config.json"


class FormParser(HTMLParser):
    """Parse HTML forms, extract action and all hidden inputs."""

    def __init__(self):
        super().__init__()
        self.forms = []
        self._current_form = None

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == "form":
            self._current_form = {
                "action": attrs_dict.get("action", ""),
                "method": attrs_dict.get("method", "get").upper(),
                "fields": {},
            }
        elif tag == "input" and self._current_form is not None:
            name = attrs_dict.get("name")
            value = attrs_dict.get("value", "")
            if name:
                self._current_form["fields"][name] = value

    def handle_endtag(self, tag):
        if tag == "form" and self._current_form is not None:
            self.forms.append(self._current_form)
            self._current_form = None


def _parse_forms(html: str) -> list[dict]:
    parser = FormParser()
    parser.feed(html)
    return parser.forms


def load_config() -> dict:
    """Load credentials from config.json."""
    with open(CONFIG_PATH, "r") as f:
        config = json.load(f)
    if not config.get("username") or not config.get("password"):
        raise ValueError("Please fill in username and password in config.json")
    return config


def login(config: dict | None = None) -> tuple[requests.Session, str]:
    """
    Perform the full SAML login flow.

    Returns:
        (session, sesskey) - authenticated requests.Session and Moodle sesskey
    """
    if config is None:
        config = load_config()

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    })

    base_url = config["base_url"]

    # Step 1: Visit Moodle login page, get redirect to IdP
    resp = session.get(f"{base_url}/login/index.php", allow_redirects=False)
    if resp.status_code != 302:
        raise RuntimeError(f"Step 1 failed: expected 302, got {resp.status_code}")
    idp_url = resp.headers["Location"]

    # Step 2: Visit IdP SSO endpoint, get redirect to login form
    resp = session.get(idp_url, allow_redirects=False)
    if resp.status_code != 302:
        raise RuntimeError(f"Step 2 failed: expected 302, got {resp.status_code}")
    login_form_url = resp.headers["Location"]
    # Handle relative URL
    if login_form_url.startswith("/"):
        login_form_url = config["sso_url"] + login_form_url

    # Step 3: Load login form, extract AuthState
    resp = session.get(login_form_url)
    resp.raise_for_status()

    forms = _parse_forms(resp.text)
    auth_state = None
    for form in forms:
        if "AuthState" in form["fields"]:
            auth_state = form["fields"]["AuthState"]
            break
    if auth_state is None:
        raise RuntimeError("Step 3 failed: could not extract AuthState from login page")

    # Step 4: Submit credentials
    post_data = {
        "username": config["username"],
        "password": config["password"],
        "AuthState": auth_state,
    }
    resp = session.post(login_form_url, data=post_data)
    resp.raise_for_status()

    # Check for login failure
    if "Incorrect username or password" in resp.text or "loginerror" in resp.text:
        raise RuntimeError("Login failed: incorrect username or password")

    # Step 5: Parse auto-submit form, extract SAMLResponse and RelayState
    forms = _parse_forms(resp.text)
    saml_form = None
    for form in forms:
        if "SAMLResponse" in form["fields"]:
            saml_form = form
            break
    if saml_form is None:
        raise RuntimeError("Step 5 failed: SAMLResponse form not found")

    acs_url = saml_form["action"]
    saml_data = {
        "SAMLResponse": saml_form["fields"]["SAMLResponse"],
        "RelayState": saml_form["fields"].get("RelayState", ""),
    }

    # Step 6: POST SAMLResponse to Moodle ACS
    resp = session.post(acs_url, data=saml_data)
    resp.raise_for_status()

    # Step 7: Extract sesskey from page
    sesskey = _extract_sesskey(resp.text)
    if sesskey is None:
        # May need to request the homepage again
        resp = session.get(base_url)
        sesskey = _extract_sesskey(resp.text)

    if sesskey is None:
        raise RuntimeError("Login appeared successful but could not extract sesskey")

    return session, sesskey


def _extract_sesskey(html: str) -> str | None:
    """Extract sesskey from Moodle page HTML."""
    # M.cfg.sesskey is usually in a <script> tag
    match = re.search(r'"sesskey"\s*:\s*"([a-zA-Z0-9]+)"', html)
    if match:
        return match.group(1)
    # May also appear in <input name="sesskey">
    match = re.search(r'name="sesskey"\s+value="([a-zA-Z0-9]+)"', html)
    if match:
        return match.group(1)
    return None


if __name__ == "__main__":
    cfg = load_config()
    sess, key = login(cfg)
    print(f"Login successful! sesskey={key}")
    print(f"MoodleSession cookie: {sess.cookies.get('MoodleSession', domain='ukmfolio.ukm.my')}")
