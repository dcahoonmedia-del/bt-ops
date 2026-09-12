"""Provider-backed origin authentication for desk control mail.

Threat model (fail closed)
==========================

Identity is not proven by:

- the From: header (attacker-controlled)
- PACKET_HASH / nonce (binding to a draft, not a mailbox)
- a copied or quoted DESK-CTRL block in a reply
- Authentication-Results written by the sender or by any hop we did not
  observe via the receiving mailbox's Gmail API

This proof mailbox is contactus@, fetched with the existing read-only
Gmail API token. Gmail prepends its own Authentication-Results on ingest
(`authserv-id=mx.google.com`). We therefore:

1. Require the message to have been fetched via `contactus_gmail_api`
   with a non-empty Gmail message id. CLI files and reconstructed bodies
   fail closed unless that provider evidence is attached.
2. Read only the first/topmost Authentication-Results header. If that
   header is absent or its authserv-id is not mx.google.com, reject.
   We do not walk later AR headers; an attacker can append or inject
   those in the raw RFC822.
3. Require that first Google AR to show `dkim=pass` for @btpestcontrol.com
   or `spf=pass` for smtp.mailfrom=daniel@btpestcontrol.com.
4. Require the normalized From: to equal daniel@btpestcontrol.com as a
   consistency check *after* the provider result. From alone never
   authorizes.
5. Parse control fields only from unquoted text. Lines that look like
   `>` quotes cannot authorize.

Out of scope / residual risk:

- Compromise of daniel@ itself (authorized mailbox).
- Compromise of the contactus Gmail API token (can mint false fetches).
- Gmail-side AR bugs. We do not have a second provider (daniel@ Sent
  cross-check) on the live VM with current access; that would be a
  narrow additional control, not a reason to weaken this gate.
- We do not trust attacker-supplied Authentication-Results in isolation.

Replay is blocked by nonce consume, not by origin auth.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping

from .constants import ALLOWED_SENDER
from .eligibility import normalize_email

FETCHED_VIA_GMAIL = "contactus_gmail_api"
AUTHSERV_GMAIL = "mx.google.com"

_DKIM_PASS = re.compile(r"\bdkim=pass\b", re.I)
_SPF_PASS = re.compile(r"\bspf=pass\b", re.I)
_DKIM_I = re.compile(r"header\.i=([^\s;]+)", re.I)
_MAILFROM = re.compile(r"smtp\.mailfrom=([^\s;]+)", re.I)
_QUOTED = re.compile(r"^\s*>")


def unquoted_control_text(body: str | None) -> str:
    """Drop quoted reply lines so copied CTRL syntax cannot authorize."""
    lines = []
    for line in str(body or "").replace("\r\n", "\n").split("\n"):
        if _QUOTED.match(line):
            continue
        lines.append(line)
    return "\n".join(lines)


def _as_header_pairs(headers: Any) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    if not headers:
        return pairs
    if isinstance(headers, Mapping):
        for key, value in headers.items():
            if isinstance(value, (list, tuple)):
                for item in value:
                    pairs.append((str(key), str(item)))
            else:
                pairs.append((str(key), str(value)))
        return pairs
    if isinstance(headers, Iterable):
        for item in headers:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                pairs.append((str(item[0]), str(item[1])))
    return pairs


def first_authentication_results(headers: Any) -> str | None:
    for name, value in _as_header_pairs(headers):
        if name.lower() == "authentication-results":
            return value
    return None


def _authserv_id(value: str) -> str:
    return value.split(";", 1)[0].strip().split()[0].lower() if value.strip() else ""


def _dkim_identity_ok(value: str) -> bool:
    if not _DKIM_PASS.search(value):
        return False
    identity = (_DKIM_I.search(value) or [None, ""])[1].strip().lower()
    if identity == ALLOWED_SENDER or identity == f"<{ALLOWED_SENDER}>":
        return True
    return identity.endswith("@btpestcontrol.com") or identity == "@btpestcontrol.com"


def _spf_mailfrom_ok(value: str) -> bool:
    if not _SPF_PASS.search(value):
        return False
    mailfrom = (_MAILFROM.search(value) or [None, ""])[1].strip().lower()
    return normalize_email(mailfrom) == ALLOWED_SENDER


def authenticate_control_origin(
    headers: Any,
    from_addr: str | None,
    provider_evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Fail closed unless Gmail-fetched evidence authenticates Daniel."""
    evidence = dict(provider_evidence or {})
    fetched_via = str(evidence.get("fetched_via") or "")
    gmail_message_id = str(evidence.get("gmail_message_id") or "").strip()
    header_source = headers if headers is not None else evidence.get("headers")
    from_n = normalize_email(from_addr)
    base = {
        "accepted": False,
        "fetched_via": fetched_via or None,
        "gmail_message_id": gmail_message_id or None,
        "from": from_n,
        "authserv": None,
        "dkim_ok": False,
        "spf_ok": False,
        "trusted_from_header_only": False,
        "trusted_packet_hash_as_identity": False,
    }
    if fetched_via != FETCHED_VIA_GMAIL or not gmail_message_id:
        return {**base, "reason": "origin_evidence_missing"}
    ar = first_authentication_results(header_source)
    if not ar:
        return {**base, "reason": "authentication_results_missing"}
    authserv = _authserv_id(ar)
    base["authserv"] = authserv
    if authserv != AUTHSERV_GMAIL:
        return {**base, "reason": "authentication_results_not_gmail"}
    dkim_ok = _dkim_identity_ok(ar)
    spf_ok = _spf_mailfrom_ok(ar)
    base["dkim_ok"] = dkim_ok
    base["spf_ok"] = spf_ok
    if not dkim_ok and not spf_ok:
        return {**base, "reason": "provider_auth_failed"}
    if from_n != ALLOWED_SENDER:
        return {**base, "reason": "from_not_daniel"}
    return {**base, "accepted": True, "reason": "gmail_ar_pass"}


def daniel_origin_evidence(
    gmail_message_id: str,
    *,
    headers: list[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    """Fixture / test helper. Not a production bypass."""
    return {
        "fetched_via": FETCHED_VIA_GMAIL,
        "gmail_message_id": gmail_message_id,
        "headers": headers
        or [
            (
                "Authentication-Results",
                "mx.google.com; "
                "dkim=pass header.i=@btpestcontrol.com header.s=google; "
                "spf=pass smtp.mailfrom=daniel@btpestcontrol.com; "
                "dmarc=pass header.from=btpestcontrol.com",
            ),
            ("From", f"Daniel Cahoon <{ALLOWED_SENDER}>"),
        ],
    }
