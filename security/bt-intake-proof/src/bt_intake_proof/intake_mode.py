"""Live intake mode. Isolated test harness stays on until Daniel authorizes more.

Shadow or production capture of all contactus@ mail is a separate authorization.
Setting an environment variable is not enough.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .gates import ROOT

MODE_ISOLATED_TEST = "isolated_test"
MODE_SHADOW_ALL = "shadow_all"
MODE_PRODUCTION = "production"
LIVE_RECEIVER_MODE = MODE_ISOLATED_TEST

AUTHORIZED_SHADOW_PATH = ROOT / "config" / "shadow_intake.authorized.json"


class IntakeModeError(Exception):
    """Refuses a live-mode change that Daniel has not authorized."""


def requested_mode() -> str:
    raw = os.environ.get("BT_INTAKE_MODE", "").strip().lower()
    return raw or MODE_ISOLATED_TEST


def shadow_authorization() -> dict[str, Any] | None:
    if not AUTHORIZED_SHADOW_PATH.exists():
        return None
    import json

    try:
        data = json.loads(AUTHORIZED_SHADOW_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    if data.get("authorize_shadow_intake") is True and data.get("authorized_by") == "daniel@btpestcontrol.com":
        return data
    return None


def live_receiver_mode() -> str:
    """The running receiver always stays on the isolated test harness tonight."""
    return LIVE_RECEIVER_MODE


def require_isolated_live_receiver() -> str:
    requested = requested_mode()
    if requested != MODE_ISOLATED_TEST:
        raise IntakeModeError(
            f"refusing live mode {requested!r}. Marker filters stay on until Daniel "
            "authorizes shadow intake of all real contactus@ mail in a dedicated file. "
            "Do not process real customer mail."
        )
    if shadow_authorization():
        raise IntakeModeError(
            "shadow authorization file is present but live receiver activation is not wired. "
            "Do not process real customer mail from this proof host."
        )
    return LIVE_RECEIVER_MODE


def describe_mode() -> dict[str, Any]:
    return {
        "live_receiver_mode": live_receiver_mode(),
        "requested_mode": requested_mode(),
        "shadow_authorized": bool(shadow_authorization()),
        "real_customer_processing": False,
        "subject_marker_filters": "enabled_for_isolated_testing_only",
        "production_capture": "documented_and_tested_not_live",
    }
