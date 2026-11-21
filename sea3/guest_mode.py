"""Free trial: 1 month, then a one-time reset for 2 more months with a rest day after every 10 days."""

import json
import os
from datetime import datetime, timedelta

GUEST_FILE = "guest_session.json"
TRIAL_DAYS = 30
EXTRA_DAYS = 60
REST_EVERY = 10  # in the extra months: 10 trial days, then 1 rest day


def load_guest_session():
    if os.path.exists(GUEST_FILE):
        try:
            with open(GUEST_FILE, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return None
    return None


def save_guest_session(session):
    with open(GUEST_FILE, "w", encoding="utf-8") as f:
        json.dump(session, f, indent=2)


def start_guest_trial():
    """Start the 1-month clock the first time someone presses 'Start Free Trial'."""
    if not load_guest_session():
        now = datetime.now()
        save_guest_session({
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(days=TRIAL_DAYS)).isoformat(),
            "usage_count": 0,
            "extended": False,
        })


def record_guest_usage():
    session = load_guest_session()
    if session:
        session["usage_count"] = session.get("usage_count", 0) + 1
        save_guest_session(session)


def trial_status(now=None):
    """state is 'not_started', 'active', 'rest_day' or 'ended'; can_reset says whether the 2-month reset is still available."""
    now = now or datetime.now()
    session = load_guest_session()
    if not session:
        return {"state": "not_started", "days_left": TRIAL_DAYS, "usage_count": 0, "can_reset": False, "extended": False}

    expires = datetime.fromisoformat(session["expires_at"])
    extended = session.get("extended", False)
    info = {"usage_count": session.get("usage_count", 0), "extended": extended, "can_reset": False}

    if now >= expires:
        return {**info, "state": "ended", "days_left": 0, "can_reset": not extended}

    info["days_left"] = max(1, (expires - now).days)
    if extended:
        day = (now - datetime.fromisoformat(session["extension_start"])).days
        if day % (REST_EVERY + 1) == REST_EVERY:
            return {**info, "state": "rest_day"}
    return {**info, "state": "active"}


def reset_trial(now=None):
    """Give 2 more months, once, after the first month has ended. Returns True if it worked."""
    now = now or datetime.now()
    status = trial_status(now)
    if not status["can_reset"]:
        return False
    session = load_guest_session()
    session.update(
        extended=True,
        extension_start=now.isoformat(),
        expires_at=(now + timedelta(days=EXTRA_DAYS)).isoformat(),
    )
    session.pop("locked_out", None)
    save_guest_session(session)
    return True


def get_guest_info():
    status = trial_status()
    return {"days_left": status["days_left"], "usage_count": status["usage_count"]}
