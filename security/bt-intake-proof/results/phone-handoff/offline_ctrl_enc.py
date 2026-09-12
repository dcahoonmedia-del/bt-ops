#!/usr/bin/env python3
"""Portable CTRL-ENC v1 encoder/decoder. Standard library only.

Matches deployed source c41404e75bbc768d034814a5ec3bca90ad927b6e
(release 2ec5186023ca9a7dacc9dfc51b67e2aaae4de563630b33ae39b223514c2e38e2).
Does not send mail. Does not import bt_intake_proof.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

MARKER = "BT-INTAKE-PROOF-DESK-CTRL-E9A8"
CTRL_ENC_VERSION = "v1"
WIRE_LINE = 64
SIMPLE_LINE = 76
SIMPLE_KEYS = ("INTENT", "OWNER", "NOTE", "CASE_ID", "DRAFT_VERSION", "NONCE", "PACKET_HASH")
PAYLOAD_KEYS = ("intent", "owner", "note", "case_id", "draft_version", "nonce", "packet_hash")
PAYLOAD_STRING_KEYS = ("intent", "owner", "note", "case_id", "nonce", "packet_hash")
_KEY_LINE = re.compile(r"^([A-Z][A-Z0-9_-]*)=(.*)$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_QUOTED = re.compile(r"^\s*>")


class DuplicateJsonField(ValueError):
    pass


def unquoted(body: str | None) -> str:
    lines = []
    for line in str(body or "").replace("\r\n", "\n").split("\n"):
        if _QUOTED.match(line):
            continue
        lines.append(line)
    return "\n".join(lines)


def wrap_wire(text: str, width: int = WIRE_LINE) -> list[str]:
    return [text[i : i + width] for i in range(0, len(text), width)] or [""]


def reject_duplicate_pairs(pairs: list[tuple[Any, Any]]) -> dict[Any, Any]:
    seen: dict[Any, Any] = {}
    for key, value in pairs:
        if key in seen:
            raise DuplicateJsonField(str(key))
        seen[key] = value
    return seen


def control_payload(*, intent: str, binding: dict[str, Any], owner: str = "", note: str = "") -> dict[str, Any]:
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


def dumps_payload(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def simple_lines(*, intent: str, binding: dict[str, Any], owner: str = "", note: str = "") -> list[str]:
    return [
        MARKER,
        f"INTENT={intent}",
        f"OWNER={owner or ''}",
        f"NOTE={note}",
        f"CASE_ID={binding.get('case_id') or ''}",
        f"DRAFT_VERSION={binding.get('draft_version') or ''}",
        f"NONCE={binding.get('nonce') or ''}",
        f"PACKET_HASH={binding.get('packet_hash') or ''}",
    ]


def encode(*, intent: str, binding: dict[str, Any], owner: str = "", note: str = "") -> str:
    text = "" if note is None else str(note)
    lines = simple_lines(intent=intent, binding=binding, owner=owner, note=text)
    if "\n" not in text and "\r" not in text and all(len(line) <= SIMPLE_LINE for line in lines):
        return "\n".join(lines) + "\n"
    payload = control_payload(intent=intent, binding=binding, owner=owner, note=text)
    raw = dumps_payload(payload)
    digest = hashlib.sha256(raw).hexdigest()
    b64 = base64.b64encode(raw).decode("ascii")
    out = [
        MARKER,
        f"CTRL-ENC={CTRL_ENC_VERSION}",
        f"ENC_LEN={len(raw)}",
        "ENC_SHA256",
        digest,
        "ENC_B64",
        *wrap_wire(b64),
        "ENC_B64_END",
    ]
    if any(len(line) > WIRE_LINE for line in out):
        raise ValueError("v1 wire line exceeds 64")
    return "\n".join(out) + "\n"


def _fail(reason: str) -> dict[str, Any]:
    return {"ok": False, "reason": reason}


def decode(subject: str | None, body: str | None) -> dict[str, Any]:
    blob = f"{subject or ''}\n{unquoted(body)}"
    if MARKER not in blob:
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
            if token in {"ENC_B64", "ENC_B64_END", "ENC_SHA256", MARKER} or _KEY_LINE.match(line.strip() or ""):
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
            if token == "ENC_B64_END":
                in_b64 = False
                b64_closed = True
                continue
            if token in {"ENC_B64", "ENC_SHA256", "ENC_B64_END", MARKER}:
                return _fail("note_b64_truncated")
            b64_parts.append(re.sub(r"\s+", "", line))
            continue
        stripped = line.strip()
        if not stripped or stripped == MARKER or stripped.startswith("---"):
            continue
        if stripped == "ENC_SHA256":
            if "ENC_SHA256" in tokens:
                return _fail("duplicate_control_field")
            tokens.append("ENC_SHA256")
            sha_next = True
            continue
        if stripped == "ENC_B64":
            if b64_closed or "ENC_B64" in tokens:
                return _fail("duplicate_control_field")
            tokens.append("ENC_B64")
            in_b64 = True
            continue
        if stripped == "ENC_B64_END":
            return _fail("note_b64_end_without_start")
        match = _KEY_LINE.match(stripped)
        if not match:
            return _fail("note_folded_or_truncated")
        key, value = match.group(1), match.group(2)
        if key not in SIMPLE_KEYS + ("CTRL-ENC", "ENC_LEN"):
            return _fail("unknown_control_field")
        if key in fields:
            return _fail("duplicate_control_field")
        fields[key] = value
    if in_b64 or sha_next:
        return _fail("note_b64_truncated")
    enc = fields.get("CTRL-ENC")
    has_v1 = bool(enc or "ENC_LEN" in fields or "ENC_SHA256" in tokens or "ENC_B64" in tokens)
    if enc is None:
        if has_v1:
            return _fail("conflicting_note_encoding")
        note = fields.get("NOTE", "")
        if "\n" in note or "\r" in note or len(f"NOTE={note}") > SIMPLE_LINE:
            return _fail("note_folded_or_truncated")
        return {"ok": True, "encoding": "simple", "fields": fields, "note": note}
    if enc != CTRL_ENC_VERSION:
        return _fail("unknown_ctrl_enc")
    if any(key in fields for key in SIMPLE_KEYS):
        return _fail("conflicting_note_encoding")
    if "ENC_LEN" not in fields or "ENC_SHA256" not in tokens or "ENC_B64" not in tokens or not b64_closed:
        return _fail("note_b64_truncated")
    try:
        expected_len = int(fields["ENC_LEN"])
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
        text = raw.decode("utf-8")
        payload = json.loads(text, object_pairs_hook=reject_duplicate_pairs)
    except DuplicateJsonField:
        return _fail("duplicate_json_field")
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _fail("note_not_utf8")
    if not isinstance(payload, dict):
        return _fail("control_payload_type")
    if set(payload) != set(PAYLOAD_KEYS):
        return _fail("control_payload_invalid")
    for key in PAYLOAD_STRING_KEYS:
        if not isinstance(payload[key], str):
            return _fail("control_payload_type")
    version = payload["draft_version"]
    if version is not None and (isinstance(version, bool) or not isinstance(version, int)):
        return _fail("control_payload_type")
    out_fields = {
        "INTENT": payload["intent"],
        "OWNER": payload["owner"],
        "NOTE": payload["note"],
        "CASE_ID": payload["case_id"],
        "DRAFT_VERSION": "" if version is None else str(version),
        "NONCE": payload["nonce"],
        "PACKET_HASH": payload["packet_hash"],
    }
    return {
        "ok": True,
        "encoding": CTRL_ENC_VERSION,
        "fields": out_fields,
        "note": out_fields["NOTE"],
        "payload": payload,
        "enc_len": expected_len,
        "enc_sha256": sha_hex,
        "raw_json": text,
    }


def check_vector(path: Path) -> dict[str, Any]:
    vector = json.loads(path.read_text(encoding="utf-8"))
    body = encode(
        intent=vector["intent"],
        binding=vector["binding"],
        owner=vector.get("owner") or "",
        note=vector["note"],
    )
    decoded = decode(vector["subject"], body)
    return {
        "ok": body == vector["body"] and decoded.get("ok") and decoded.get("note") == vector["note"],
        "body_matches": body == vector["body"],
        "decode_ok": bool(decoded.get("ok")),
        "note_matches": decoded.get("note") == vector["note"],
        "enc_len": decoded.get("enc_len"),
        "enc_sha256": decoded.get("enc_sha256"),
        "reason": decoded.get("reason"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Portable CTRL-ENC v1 checker. Does not send.")
    parser.add_argument("--vector", default=str(Path(__file__).with_name("offline_vector.json")))
    args = parser.parse_args(argv)
    result = check_vector(Path(args.vector))
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    sys.exit(main())
