"""Deterministic control-mail field encoding.

Simple single-line controls stay `KEY=value` for backward compatibility.
Arbitrary or long text uses CTRL-ENC=v1: one JSON payload, UTF-8, SHA-256,
and whitespace-tolerant base64 with a closed boundary. Every v1 wire line
is at most WIRE_LINE characters so MIME wrap cannot split a field.

This does not relax case/version/nonce/hash/recipient/origin checks.
Quoted `>` lines are not fields. Malformed, duplicate, truncated, or
conflicting encodings fail closed.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from typing import Any

from .constants import MARKER_DESK_CTRL
from .desk_origin import unquoted_control_text

CTRL_ENC_VERSION = "v1"
CTRL_ENC_FIELD = "CTRL-ENC"
WIRE_LINE = 64
SIMPLE_LINE = 76
ENC_LEN_FIELD = "ENC_LEN"
ENC_SHA_TOKEN = "ENC_SHA256"
ENC_B64_START = "ENC_B64"
ENC_B64_END = "ENC_B64_END"

SIMPLE_KEYS = ("INTENT", "OWNER", "NOTE", "CASE_ID", "DRAFT_VERSION", "NONCE", "PACKET_HASH")
META_KEYS = (CTRL_ENC_FIELD, ENC_LEN_FIELD)
KNOWN_KEYS = SIMPLE_KEYS + META_KEYS
PAYLOAD_KEYS = ("intent", "owner", "note", "case_id", "draft_version", "nonce", "packet_hash")

_KEY_LINE = re.compile(r"^([A-Z][A-Z0-9_-]*)=(.*)$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def note_fits_simple(note: str | None) -> bool:
    text = "" if note is None else str(note)
    if "\n" in text or "\r" in text:
        return False
    return len(f"NOTE={text}") <= SIMPLE_LINE


def wrap_wire(text: str, width: int = WIRE_LINE) -> list[str]:
    if width < 1:
        raise ValueError("wire width must be positive")
    return [text[index : index + width] for index in range(0, len(text), width)] or [""]


def control_payload(
    *,
    intent: str,
    binding: dict[str, Any],
    owner: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    version = binding.get("draft_version")
    try:
        draft_version = int(version) if version not in (None, "") else None
    except (TypeError, ValueError):
        draft_version = None
    return {
        "intent": str(intent or ""),
        "owner": str(owner or ""),
        "note": "" if note is None else str(note),
        "case_id": str(binding.get("case_id") or ""),
        "draft_version": draft_version,
        "nonce": str(binding.get("nonce") or ""),
        "packet_hash": str(binding.get("packet_hash") or ""),
    }


def encode_payload_v1(payload: dict[str, Any]) -> list[str]:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    b64 = base64.b64encode(raw).decode("ascii")
    lines = [
        f"{CTRL_ENC_FIELD}={CTRL_ENC_VERSION}",
        f"{ENC_LEN_FIELD}={len(raw)}",
        ENC_SHA_TOKEN,
        digest,
        ENC_B64_START,
    ]
    lines.extend(wrap_wire(b64))
    lines.append(ENC_B64_END)
    for line in lines:
        if len(line) > WIRE_LINE:
            raise ValueError(f"v1 wire line exceeds {WIRE_LINE}: {len(line)}")
    return lines


def serialize_control_body(
    *,
    intent: str,
    binding: dict[str, Any],
    owner: str | None = None,
    note: str | None = None,
) -> str:
    """Build the control body. Empty/short single-line NOTE stays simple."""
    text = "" if note is None else str(note)
    if note_fits_simple(text):
        lines = [
            MARKER_DESK_CTRL,
            f"INTENT={intent}",
            f"OWNER={owner or ''}",
            f"NOTE={text}",
            f"CASE_ID={binding.get('case_id') or ''}",
            f"DRAFT_VERSION={binding.get('draft_version') or ''}",
            f"NONCE={binding.get('nonce') or ''}",
            f"PACKET_HASH={binding.get('packet_hash') or ''}",
        ]
        return "\n".join(lines) + "\n"
    payload = control_payload(intent=intent, binding=binding, owner=owner, note=text)
    return "\n".join([MARKER_DESK_CTRL, *encode_payload_v1(payload)]) + "\n"


def _fail(reason: str) -> dict[str, Any]:
    return {"ok": False, "reason": reason}


def decode_control_fields(subject: str | None, body: str | None) -> dict[str, Any]:
    """Parse simple or v1 control fields. Fail closed on ambiguity."""
    blob = f"{subject or ''}\n{unquoted_control_text(body)}"
    if MARKER_DESK_CTRL not in blob:
        return _fail("not_control_mail")
    lines = blob.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    fields: dict[str, str] = {}
    tokens: list[str] = []
    b64_parts: list[str] = []
    in_b64 = False
    b64_closed = False
    sha_next = False
    sha_hex = ""
    for line in lines:
        if sha_next:
            token = re.sub(r"\s+", "", line).lower()
            if not token:
                continue
            if token in {ENC_B64_START, ENC_B64_END, ENC_SHA_TOKEN, MARKER_DESK_CTRL} or _KEY_LINE.match(line.strip() or ""):
                return _fail("note_b64_truncated")
            if any(char not in "0123456789abcdef" for char in token):
                return _fail("note_sha256_invalid")
            sha_hex += token
            if len(sha_hex) == 64:
                sha_next = False
            elif len(sha_hex) > 64:
                return _fail("note_sha256_invalid")
            continue
        if in_b64:
            token = line.strip()
            if token == ENC_B64_END:
                in_b64 = False
                b64_closed = True
                continue
            if token in {ENC_B64_START, ENC_SHA_TOKEN, ENC_B64_END, MARKER_DESK_CTRL}:
                return _fail("note_b64_truncated")
            b64_parts.append(re.sub(r"\s+", "", line))
            continue
        stripped = line.strip()
        if not stripped or stripped == MARKER_DESK_CTRL or stripped.startswith("---"):
            continue
        if stripped == ENC_SHA_TOKEN:
            if ENC_SHA_TOKEN in tokens:
                return _fail("duplicate_control_field")
            tokens.append(ENC_SHA_TOKEN)
            sha_next = True
            continue
        if stripped == ENC_B64_START:
            if b64_closed or ENC_B64_START in tokens:
                return _fail("duplicate_control_field")
            tokens.append(ENC_B64_START)
            in_b64 = True
            continue
        if stripped == ENC_B64_END:
            return _fail("note_b64_end_without_start")
        match = _KEY_LINE.match(stripped)
        if not match:
            return _fail("note_folded_or_truncated")
        key, value = match.group(1), match.group(2)
        if key not in KNOWN_KEYS:
            return _fail("unknown_control_field")
        if key in fields:
            return _fail("duplicate_control_field")
        fields[key] = value
    if in_b64 or sha_next:
        return _fail("note_b64_truncated")

    enc = fields.get(CTRL_ENC_FIELD)
    has_v1 = bool(enc or ENC_LEN_FIELD in fields or ENC_SHA_TOKEN in tokens or ENC_B64_START in tokens)
    if enc is None:
        if has_v1:
            return _fail("conflicting_note_encoding")
        note = fields.get("NOTE", "")
        if not note_fits_simple(note):
            return _fail("note_folded_or_truncated")
        return {"ok": True, "encoding": "simple", "fields": fields, "note": note}

    if enc != CTRL_ENC_VERSION:
        return _fail("unknown_ctrl_enc")
    simple_present = [key for key in SIMPLE_KEYS if key in fields]
    if simple_present:
        return _fail("conflicting_note_encoding")
    if ENC_LEN_FIELD not in fields or ENC_SHA_TOKEN not in tokens or ENC_B64_START not in tokens or not b64_closed:
        return _fail("note_b64_truncated")
    try:
        expected_len = int(fields[ENC_LEN_FIELD])
    except ValueError:
        return _fail("note_len_invalid")
    if expected_len < 0:
        return _fail("note_len_invalid")
    if not _HEX64.match(sha_hex):
        return _fail("note_sha256_invalid")
    packed = "".join(b64_parts)
    if not packed and expected_len != 0:
        return _fail("note_b64_truncated")
    try:
        raw = base64.b64decode(packed, validate=True)
    except (ValueError, binascii.Error):
        return _fail("note_b64_invalid")
    if len(raw) != expected_len:
        return _fail("note_len_mismatch")
    if hashlib.sha256(raw).hexdigest() != sha_hex:
        return _fail("note_sha256_mismatch")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _fail("note_not_utf8")
    if not isinstance(payload, dict):
        return _fail("note_not_utf8")
    extra = set(payload) - set(PAYLOAD_KEYS)
    missing = set(PAYLOAD_KEYS) - set(payload)
    if extra or missing:
        return _fail("control_payload_invalid")
    fields = {
        "INTENT": str(payload.get("intent") or ""),
        "OWNER": str(payload.get("owner") or ""),
        "NOTE": "" if payload.get("note") is None else str(payload.get("note")),
        "CASE_ID": str(payload.get("case_id") or ""),
        "DRAFT_VERSION": "" if payload.get("draft_version") in (None, "") else str(payload.get("draft_version")),
        "NONCE": str(payload.get("nonce") or ""),
        "PACKET_HASH": str(payload.get("packet_hash") or ""),
    }
    return {"ok": True, "encoding": CTRL_ENC_VERSION, "fields": fields, "note": fields["NOTE"], "payload": payload}
