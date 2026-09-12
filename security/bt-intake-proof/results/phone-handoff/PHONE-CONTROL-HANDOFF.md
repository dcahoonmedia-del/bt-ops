# Phone control handoff (CTRL-ENC v1)

Self-contained contract for a phone agent that can read Daniel Gmail and send
mail, but does not have the VM, local files, or this repository.

Derived from **exactly** deployed source `c41404e75bbc768d034814a5ec3bca90ad927b6e`
(release SHA256 `2ec5186023ca9a7dacc9dfc51b67e2aaae4de563630b33ae39b223514c2e38e2`).
Do not invent fields. Do not recompute `PACKET_HASH`. Do not send until Daniel
approves one specific next step.

This file is **preparation**. It is not live-send approval. It is not phone /
Mac-off proof.

Completed case `BTC-contactus-1a096d60643b3b1a` is Brenda-owned. Do not touch
or replay it. Actions 1 and 2 stay consumed. Customer sends stay OFF.

Offline checker: `offline_ctrl_enc.py` + `offline_vector.json` (synthetic only).

---

## 1. Envelope

| Item | Exact value |
| --- | --- |
| From | `daniel@btpestcontrol.com` |
| To | `contactus@btpestcontrol.com` |
| Cc / Bcc | empty |
| Subject | `BT-INTAKE-PROOF-DESK-CTRL-E9A8` |
| Body marker (first line) | `BT-INTAKE-PROOF-DESK-CTRL-E9A8` |

Quoted `>` lines are stripped before parse and cannot authorize.

### Permitted intents (bridge)

Only these authorize:

- `revise_draft`
- `hold`
- `office_owned` (requires `owner` `brenda` or `ally`)
- `no_response_needed`
- `approve_and_send_current` (still the exact isolated desk-roundtrip send only; **no blanket send**)

Not bridge-authorized (backend rejects): `approve_draft_only`, `request_information`, `conditional_instruction`, `ambiguous_needs_confirmation`.

---

## 2. When to use simple KEY=value vs CTRL-ENC=v1

**Simple** (one `KEY=value` line each) only if the note has no CR/LF **and** every generated line is ≤ 76 characters, including `PACKET_HASH=<64 hex>` (that line is 76).

Hold / Brenda / Ally / empty NOTE usually stay simple.

**v1** if the note has a newline, or any simple line would exceed 76 (long NOTE, long case id, long nonce). Multiline revision **must** use v1. Do not put a long draft on a raw `NOTE=` line.

---

## 3. v1 JSON schema

One JSON object. Exact keys, no extras, no missing, no duplicates.

| Key | Type | Required | Source |
| --- | --- | --- | --- |
| `intent` | string | yes | chosen action |
| `owner` | string | yes | `""` unless `office_owned` |
| `note` | string | yes | exact revision body, or `""` |
| `case_id` | string | yes | CASE packet `CASE_ID=` |
| `draft_version` | JSON number (int) or `null` | yes | CASE packet `DRAFT_VERSION=` as integer |
| `nonce` | string | yes | CASE packet `NONCE=` |
| `packet_hash` | string, 64 lowercase hex | yes | CASE packet `PACKET_HASH=` **copied** |

`draft_version` must be a JSON integer, not `"3"`, not `true`.
`note` must be a JSON string, not an object.
Duplicate keys fail closed (`duplicate_json_field`). Last-key-wins is forbidden.
Do not coerce objects or numbers to strings.

`owner` for `office_owned` is `brenda` or `ally` (lowercase). Otherwise `""`.

---

## 4. Exact UTF-8 serialization

```
raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
ENC_LEN = len(raw)          # byte length
ENC_SHA256 = sha256(raw)    # 64 lowercase hex
ENC_B64 = standard base64(raw), wrapped at 64 characters
```

`sort_keys=True` order: `case_id`, `draft_version`, `intent`, `nonce`, `note`, `owner`, `packet_hash`.

`ensure_ascii=False` so `Café` and `—` stay UTF-8.

Wire body:

```
BT-INTAKE-PROOF-DESK-CTRL-E9A8
CTRL-ENC=v1
ENC_LEN=<decimal>
ENC_SHA256
<64 hex, may wrap; parser joins hex fragments>
ENC_B64
<base64 chunks, each ≤ 64 chars>
ENC_B64_END
```

Every v1 line is ≤ 64 characters. Do not emit simple `INTENT=` / `NOTE=` lines next to v1 (conflicting encoding).

### Parser behavior (fail closed)

- Drop quoted `>` lines.
- Join whitespace in base64 and in the SHA hex.
- Require closed `ENC_B64` / `ENC_B64_END`.
- `ENC_LEN` must equal decoded byte length.
- SHA-256 of those bytes must equal `ENC_SHA256`.
- Strict JSON object pairs; duplicate keys fail.
- Payload types must match the table above.
- Unknown `CTRL-ENC` version fails.
- Folded simple `NOTE=` (mail wrap of a long first line) fails `note_folded_or_truncated`.
- 63-character `PACKET_HASH` is later rejected as `packet_hash_invalid`. Do not truncate.

---

## 5. How to read bindings from the delivered CASE packet

Open the newest Daniel inbox mail whose subject starts with:

`BT-INTAKE-PROOF-DESK-CASE-E9A8`

Do not use an older CASE mail after a RESULT that changed the draft.

Human blocks (speak these to Daniel; they are not the binding):

- Case / Owner / Office hold / Draft version / Why it needs attention
- Current draft → Proposed response

Machine block (do **not** read to Daniel):

```
--- Machine binding (ChatGPT only; do not read this to Daniel) ---
BT-INTAKE-PROOF-DESK-BIND-E9A8
CASE_ID=...
DRAFT_VERSION=...
NONCE=...
PACKET_HASH=...
LATEST_INBOUND=...
TO_ADDR=...
BODY_HASH=...
```

Copy `CASE_ID`, `DRAFT_VERSION`, `NONCE`, `PACKET_HASH` into the control JSON.

### Expiry

There is **no** control-binding expiry field on the CASE packet. Freshness is:

- newest CASE packet for that case
- unused nonce + current draft version
- backend also checks inbound id and draft body hash

A used nonce fails `nonce_consumed`. A new draft or inbound fails `stale_draft_version` / `inbound_changed` / `packet_hash_invalid`.

### Do not recompute PACKET_HASH

Backend hash input is JSON of:

`body_hash`, `case_id`, `draft_version`, `latest_inbound_message_id`, `mailbox`, `nonce`, `to_addr`

`mailbox` (`contactus@btpestcontrol.com`) is **inside the hash and is not printed** on the CASE packet. If you recompute from visible fields only, the hash will not match.

**Copy `PACKET_HASH=`.** Do not invent `mailbox` on the wire.

---

## 6. What the CASE packet actually supplies

| Needed to build a control | On delivered CASE packet? |
| --- | --- |
| `case_id` | yes — `CASE_ID=` and `CASE=` |
| `draft_version` | yes — `DRAFT_VERSION=` and Draft version |
| `nonce` | yes — `NONCE=` |
| `packet_hash` (64 hex) | yes — `PACKET_HASH=` |
| current draft body | yes — Proposed response |
| owner / hold | yes — Owner / Office hold |
| `intent` / `owner` / `note` | no — you choose after talking to Daniel |
| CTRL-ENC encode/decode contract | **no** — this handoff |
| control-binding expiry | **no** — not a runtime field |
| `mailbox` for hash recompute | **no** — copy `PACKET_HASH` instead |
| Host `desk-control.json` | **no** — generate-only on the VM, not Gmail |

The encoding contract missing from Gmail is why Prepare Grok Audit Access was **BLOCKED** after it could already read CASE/RESULT. Smallest fix: put this file in the phone conversation. Do not change runtime to invent expiry or mailbox fields in this milestone.

If a later change prints `MAILBOX=` on the binding block, that is optional convenience. It is not required to send a valid control today.

---

## 7. Exact revision body and DRAFT - NOT SENT

`note` is the **entire** new draft, byte-for-byte.

- Keep paragraph breaks, trailing spaces, and a trailing newline if they are in the approved text.
- Start with `DRAFT - NOT SENT` then a blank line, then the customer-facing wording.
- Backend `revise_draft` saves that string exactly (`preserve_exact`). It still marks `labeled_not_sent`.
- Do not strip trailing whitespace to “clean up” the mail.
- Empty / whitespace-only NOTE leaves the previous draft unchanged.

Speak the wording to Daniel. Do not speak nonce, hash, case id, or draft number unless he asks.

---

## 8. Canonical Sent matching

Authorization is not From: and not PACKET_HASH alone.

Backend requires:

1. Mailbox-bound Authentication-Results on contactus ingest (prerequisite)
2. Exactly one daniel@ Sent message with the same RFC Message-ID, recipient `contactus@btpestcontrol.com` only, and the **same canonical parsed payload**
3. Timing within 15 minutes

Canonical payload fields: `intent`, `owner`, `note`, `case_id`, `draft_version`, `nonce`, `packet_hash`, `marker`.

v1 exists so MIME wrap of the encoded mail still decodes to the same `note` as Daniel Sent. Do not “fix” wrap by joining a raw `NOTE=` line.

Quoted copies of a control do not authorize.

---

## 9. Stale / duplicate / ownership / hold

Backend `blocked_by_backend` reasons include:

| Reason | Meaning |
| --- | --- |
| `nonce_invalid` / `packet_hash_invalid` | binding does not match the current draft |
| `stale_draft_version` | CASE packet is old |
| `nonce_consumed` | that version was already used |
| `inbound_changed` / `draft_body_changed` | new inbound or draft |
| `hold` | hold blocks `approve_and_send_current` |
| `office_owned` | Brenda/Ally ownership blocks competing send |
| `office_owner_required` | `office_owned` without Brenda or Ally |
| `not_desk_send_draft` | send is not the isolated desk-roundtrip body |
| `unsupported_bridge_intent` | not one of the five bridge intents |

RESULT mail subject starts with `BT-INTAKE-PROOF-DESK-RESULT-E9A8`.

Read:

- Human sentence (tell Daniel that)
- `STATUS=ok` or `STATUS=failed`
- `INTENT=`
- `CASE=`
- `DRAFT=` (new version after a successful revise)
- `REASON=`
- `EXECUTE_SEND` / `SEND_QUEUED` must stay `no` for a revision test

Then re-read the newest CASE packet. Draft version must increase. Proposed response must equal the approved `note`. Send action count must stay 0 for a normal CASEMGR draft.

---

## 10. Synthetic offline vector (not live, not the Brenda case)

Bindings below are fixtures. Do not send this mail.

Note (Python repr):

```
'DRAFT - NOT SENT\n\nCafé — please share the service address and a callback number.  \n'
```

That is: label, blank line, `Café` + em dash, two spaces before the final newline.

JSON payload (UTF-8, sorted keys). Newlines inside `note` are the two-character escape `\n`:

```
{"case_id":"BTC-contactus-phone-handoff-fixture-e9a8","draft_version":3,"intent":"revise_draft","nonce":"nonce-phone-handoff-e9a8","note":"DRAFT - NOT SENT\n\nCafé — please share the service address and a callback number.  \n","owner":"","packet_hash":"c337c20ef7d505c4fb11a0e1e2cc26e8e22af0983e632b79d70cde7b1ac53dad"}
```

| Check | Value |
| --- | --- |
| UTF-8 byte length `ENC_LEN` | `322` |
| SHA-256 `ENC_SHA256` | `1aeebd99c769a50ffe51e1b676232c153aa16b19732a879385bbd8ae1e4205d1` |
| UTF-8 hex (unambiguous) | see `offline_vector.json` field `raw_utf8_hex` |

Encoded mail (production serializer and `offline_ctrl_enc.py` both emit this):

```
Subject: BT-INTAKE-PROOF-DESK-CTRL-E9A8

BT-INTAKE-PROOF-DESK-CTRL-E9A8
CTRL-ENC=v1
ENC_LEN=322
ENC_SHA256
1aeebd99c769a50ffe51e1b676232c153aa16b19732a879385bbd8ae1e4205d1
ENC_B64
eyJjYXNlX2lkIjoiQlRDLWNvbnRhY3R1cy1waG9uZS1oYW5kb2ZmLWZpeHR1cmUt
ZTlhOCIsImRyYWZ0X3ZlcnNpb24iOjMsImludGVudCI6InJldmlzZV9kcmFmdCIs
Im5vbmNlIjoibm9uY2UtcGhvbmUtaGFuZG9mZi1lOWE4Iiwibm90ZSI6IkRSQUZU
IC0gTk9UIFNFTlRcblxuQ2Fmw6kg4oCUIHBsZWFzZSBzaGFyZSB0aGUgc2Vydmlj
ZSBhZGRyZXNzIGFuZCBhIGNhbGxiYWNrIG51bWJlci4gIFxuIiwib3duZXIiOiIi
LCJwYWNrZXRfaGFzaCI6ImMzMzdjMjBlZjdkNTA1YzRmYjExYTBlMWUyY2MyNmU4
ZTIyYWYwOTgzZTYzMmI3OWQ3MGNkZTdiMWFjNTNkYWQifQ==
ENC_B64_END
```

Expected decode: `note` equals the repr above; `draft_version` 3; `packet_hash` `c337c20e…353dad`.

Portable checker (stdlib only):

```
python3 offline_ctrl_enc.py --vector offline_vector.json
```

Must print `"ok": true`. Production parser tests in `tests/test_phone_handoff.py` check the same bytes.

---

## 11. Portable encoder (copy into phone Python)

See `offline_ctrl_enc.py`. Minimum encode:

```python
import base64, hashlib, json

def encode_v1(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    b64 = base64.b64encode(raw).decode("ascii")
    chunks = [b64[i:i+64] for i in range(0, len(b64), 64)]
    return "\n".join([
        "BT-INTAKE-PROOF-DESK-CTRL-E9A8",
        "CTRL-ENC=v1",
        f"ENC_LEN={len(raw)}",
        "ENC_SHA256",
        digest,
        "ENC_B64",
        *chunks,
        "ENC_B64_END",
        "",
    ])
```

Copy `PACKET_HASH` from the CASE packet. Do not hash the revision text and call that `packet_hash`.

---

## 12. Operational sequence — NEW internal case only

Do **not** use `BTC-contactus-1a096d60643b3b1a`.

### A. Preparation (this file) — no send

1. Phone agent has this handoff in context.
2. Offline vector / `offline_ctrl_enc.py` checks `ok`.
3. Daniel has **not** approved a live control yet.

### B. Later live test — one contextual approval, then one control

Stop before each send and say what will be sent in plain language.

1. New isolated inquiry: daniel@ → contactus@, unique `BT-INTAKE-PROOF-CASEMGR-…` marker. Not Phase E. Not desk-roundtrip send.
2. Wait for a new CASE packet.
3. Read current draft and the machine binding.
4. Show Daniel the **exact** longer proposed revision (the words, not the hash).
5. Obtain approval for **that text only**. That is not approval to send to a customer and not approval of `approve_and_send_current`.
6. Build one v1 control with the copied binding and that exact `note`.
7. Send only that control: daniel@ → contactus@, subject `BT-INTAKE-PROOF-DESK-CTRL-E9A8`.
8. Read RESULT: `STATUS=ok`, `INTENT=revise_draft`, `DRAFT` is the new version, `EXECUTE_SEND=no`.
9. Re-read CASE: draft version incremented, proposed response matches, no customer send.

If RESULT fails, do not retry from a stale packet. Read the newest CASE packet first.

---

## 13. Remaining live-test limitations

| Item | Status |
| --- | --- |
| Encoding contract now written for phone | this file |
| Offline vector vs production parser | unit / offline |
| Encoded live mail on a new case | **not proven** |
| Phone / Mac-off | **not proven** |
| Customer send | **OFF** |
| Broad capture | **OFF** |
| Fieldwork / scheduling writes | **OFF** |
| New credentials / MCP / infrastructure | **not requested** |
