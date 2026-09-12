"""Provider-backed origin authentication for desk control mail.

Threat model (fail closed)
==========================

Identity is not proven by:

- the From: header (attacker-controlled)
- PACKET_HASH / nonce (binding to a draft, not a mailbox)
- a copied or quoted DESK-CTRL block in a reply
- Authentication-Results written by the sender or by any hop we did not
  observe via the receiving mailbox's Gmail API
- a domain-level DKIM pass for @btpestcontrol.com (proves the Workspace
  domain signed, not that the mailbox was daniel@)
- an arbitrary string `mx.google.com` in a header we did not fetch

Mailbox-bound provider result (what this module can claim)
----------------------------------------------------------

A Gmail-fetched first `Authentication-Results` header may authorize only
when a *method-specific* result is bound to daniel@ itself:

- `spf=pass` on the same spec as `smtp.mailfrom=daniel@btpestcontrol.com`
- `dkim=pass` on the same spec as `header.i=daniel@btpestcontrol.com`

`dkim=pass header.i=@btpestcontrol.com` is recorded as domain evidence
only. It does not authorize. contactus@, brenda@, ally@, and daniel@
share that organizational DKIM identity.

This is not full human-identity proof. It does not survive compromise of
daniel@ or of the contactus Gmail API token.

Trusted Gmail-inserted header boundary
--------------------------------------

We do not walk later Authentication-Results headers. We take only the
first header whose name is Authentication-Results (not
ARC-Authentication-Results). Gmail's ingest inserts its own AR with
authserv-id `mx.google.com` ahead of the original RFC822. Runtime
evidence of that order on a Gmail-ingested inbound is in
`results/DESK_ORIGIN_EVIDENCE.md` (daniel@ inbox copy of the Phase E
send, provider id `1a094071c6be5dab`). That is Gmail's inbound path,
not a contactus-fetched control mail. The live contactus fetch that
would confirm the same prepend on the control mailbox is the existing
readonly Gmail API used by `hydrate_receipt`; this agent cannot read
that mailbox.

authserv-id must be exactly `mx.google.com` (no lookalike suffix).

Missing capability for a stronger origin claim
----------------------------------------------

A Message-ID match against daniel@ Sent would prove the control was
submitted from that mailbox independently of AR parsing. That path is
not available on this agent (no daniel read token on the VM; Cursor
Gmail MCP is not the host). Until that exists, authorization stays at
mailbox-bound SPF/DKIM method results, not "full identity PASS".
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping

from .constants import ALLOWED_SENDER
from .eligibility import normalize_email

FETCHED_VIA_GMAIL = "contactus_gmail_api"
AUTHSERV_GMAIL = "mx.google.com"
IDENTITY_LEVEL_MAILBOX = "mailbox_bound_provider_result"
IDENTITY_LEVEL_DOMAIN = "domain_only_not_mailbox"
IDENTITY_LEVEL_NONE = "none"

_QUOTED = re.compile(r"^\s*>")
_COMMENT = re.compile(r"\([^)]*\)")
_SPEC = re.compile(r"(?i)^\s*([a-z0-9-]+)\s*=\s*([a-z0-9-]+)\s*(.*)$")
_PROP = re.compile(r"(?i)([a-z0-9.]+)=([^\s;]+)")


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
    if not value.strip():
        return ""
    token = value.split(";", 1)[0].strip().split()[0].lower()
    return token.rstrip(".")


def parse_ar_method_results(value: str) -> list[dict[str, Any]]:
    """Parse each method=result and bind following properties to that result only."""
    rest = value.split(";", 1)[1] if ";" in value else ""
    found: list[dict[str, Any]] = []
    for raw in rest.split(";"):
        spec = _COMMENT.sub(" ", raw).strip()
        if not spec:
            continue
        match = _SPEC.match(spec)
        if not match:
            continue
        method, result, prop_blob = match.group(1).lower(), match.group(2).lower(), match.group(3)
        props: dict[str, str] = {}
        for item in _PROP.finditer(prop_blob):
            props[item.group(1).lower()] = item.group(2).strip().strip("<>")
        found.append({"method": method, "result": result, "props": props, "raw": spec})
    return found


def _mailbox_match(raw: str | None) -> bool:
    return normalize_email(raw) == ALLOWED_SENDER


def _domain_only_identity(raw: str | None) -> bool:
    ident = str(raw or "").strip().lower().strip("<>")
    return ident in {"@btpestcontrol.com", "btpestcontrol.com"}


def evaluate_method_results(methods: list[dict[str, Any]]) -> dict[str, Any]:
    dkim_mailbox = False
    dkim_domain = False
    spf_mailbox = False
    dkim_pass_identities: list[str] = []
    spf_pass_mailfrom: list[str] = []
    for item in methods:
        if item["method"] == "dkim":
            ident = item["props"].get("header.i") or item["props"].get("header.i")
            if item["result"] == "pass":
                dkim_pass_identities.append(str(ident or ""))
                if _mailbox_match(ident):
                    dkim_mailbox = True
                elif _domain_only_identity(ident):
                    dkim_domain = True
        elif item["method"] == "spf":
            mailfrom = item["props"].get("smtp.mailfrom")
            if item["result"] == "pass":
                spf_pass_mailfrom.append(str(mailfrom or ""))
                if _mailbox_match(mailfrom):
                    spf_mailbox = True
    mailbox_ok = dkim_mailbox or spf_mailbox
    if mailbox_ok:
        level = IDENTITY_LEVEL_MAILBOX
    elif dkim_domain:
        level = IDENTITY_LEVEL_DOMAIN
    else:
        level = IDENTITY_LEVEL_NONE
    return {
        "dkim_mailbox_ok": dkim_mailbox,
        "dkim_domain_ok": dkim_domain,
        "spf_mailbox_ok": spf_mailbox,
        "dkim_ok": dkim_mailbox,
        "spf_ok": spf_mailbox,
        "dkim_pass_identities": dkim_pass_identities,
        "spf_pass_mailfrom": spf_pass_mailfrom,
        "identity_level": level,
        "mailbox_ok": mailbox_ok,
    }


def authenticate_control_origin(
    headers: Any,
    from_addr: str | None,
    provider_evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Fail closed unless Gmail-fetched method results bind to daniel@."""
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
        "dkim_mailbox_ok": False,
        "dkim_domain_ok": False,
        "spf_mailbox_ok": False,
        "identity_level": IDENTITY_LEVEL_NONE,
        "trusted_from_header_only": False,
        "trusted_packet_hash_as_identity": False,
        "trusted_domain_dkim_as_mailbox": False,
        "full_identity_pass": False,
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
    judged = evaluate_method_results(parse_ar_method_results(ar))
    base.update(
        {
            "dkim_ok": judged["dkim_ok"],
            "spf_ok": judged["spf_ok"],
            "dkim_mailbox_ok": judged["dkim_mailbox_ok"],
            "dkim_domain_ok": judged["dkim_domain_ok"],
            "spf_mailbox_ok": judged["spf_mailbox_ok"],
            "identity_level": judged["identity_level"],
            "dkim_pass_identities": judged["dkim_pass_identities"],
            "spf_pass_mailfrom": judged["spf_pass_mailfrom"],
        }
    )
    if judged["identity_level"] == IDENTITY_LEVEL_DOMAIN and not judged["mailbox_ok"]:
        return {**base, "reason": "domain_dkim_not_mailbox_identity"}
    if not judged["mailbox_ok"]:
        return {**base, "reason": "provider_auth_failed"}
    if from_n != ALLOWED_SENDER:
        return {**base, "reason": "from_not_daniel"}
    return {
        **base,
        "accepted": True,
        "reason": "mailbox_bound_provider_result",
        "full_identity_pass": False,
    }


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
                "dkim=pass header.i=daniel@btpestcontrol.com header.s=google; "
                "spf=pass smtp.mailfrom=daniel@btpestcontrol.com; "
                "dmarc=pass header.from=btpestcontrol.com",
            ),
            ("From", f"Daniel Cahoon <{ALLOWED_SENDER}>"),
        ],
    }
