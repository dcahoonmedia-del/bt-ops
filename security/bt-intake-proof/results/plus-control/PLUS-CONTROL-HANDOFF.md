# Cloud Work handoff — private plus-address revision

Self-contained contract for Cloud Work. Keep machine details out of
Daniel’s spoken conversation. Use the existing CTRL-ENC v1 control
body. Do not invent a workaround. Do not send customer mail. Sending
the control is not proof of a save.

This file is **preparation**. Live host activation is a later
project-lead step. Deployment stays held after the project-lead
correction. Do not process or replay Gmail id `1a0979e37a0b0a94`.

---

## 1. Private transport

| Item | Exact value |
| --- | --- |
| From | `daniel@btpestcontrol.com` |
| To | `daniel+lead-desk@btpestcontrol.com` |
| Cc / Bcc | empty |
| Subject | `BT-INTAKE-PROOF-DESK-CTRL-E9A8` |
| Body marker | `BT-INTAKE-PROOF-DESK-CTRL-E9A8` |
| Intent this path allows | `revise_draft` only |

Hold, office ownership, and send stay on the contactus@ path.

Quoted `>` copies do not authorize. Copy `CASE_ID`, `DRAFT_VERSION`,
`NONCE`, and `PACKET_HASH` from the newest binding. Do not recompute
the hash.

Multiline revision **must** use `CTRL-ENC=v1`. Do not put a long draft
on a raw `NOTE=` line.

---

## 2. How to retrieve the one authoritative result

After you send the plus-address control, wait for **one** new mail:

| Item | Exact value |
| --- | --- |
| Mailbox | `daniel+lead-desk-results@btpestcontrol.com` |
| Subject prefix | `BT-INTAKE-PROOF-PLUS-RESULT-E9A8` |
| Marker in body | `BT-INTAKE-PROOF-PLUS-RESULT-E9A8` |

That mail is the save outcome **and** the newest binding. There is no
separate save-confirmation email and no CASE email on this path. Do
not look in contactus@ for this result.

Correlate by `CONTROL_ID=` (the Gmail id of the control you sent) and
the new `PACKET_HASH=` / `NONCE=` / `DRAFT_VERSION=` in the machine
binding block.

---

## 3. Natural-language revision flow

1. Daniel asks to change the draft.
2. You interpret `revise_draft` and put the exact new wording in the
   CTRL-ENC note.
3. You send one plus-address control from daniel@ to
   `daniel+lead-desk@`.
4. You wait for the plus-result mail.
5. You tell Daniel only the human sentence from that result.

Usual success sentence:

> Draft updated to vN. Nothing sent.

Do not read case ids, hashes, nonces, or draft numbers unless he asks
for backend detail.

---

## 4. Honest pending / blocked / verified

| State | What you tell Daniel | What you do not say |
| --- | --- | --- |
| **Pending** | I sent the revision request. I have not seen the save result yet. | “It’s saved.” “The send means it worked.” |
| **Blocked** | Nothing was saved. The private result channel or the packet was not ready. What wording do you want instead? | That a missing backend token is his fault, or any machine path. |
| **Verified** | Draft updated to vN. Nothing sent. | Machine fields, unless he asks. |

If `STATUS=failed` or `SAVE=no`, nothing was saved. Ask what he wants
instead.

If no result arrives, stay **pending**. Do not send a second control
with the same nonce. Do not send a customer message. Do not fall back
to contactus@ unless he asks to use the office path.

---

## 5. Rules you must not break

- You interpret. The backend authorizes.
- No direct customer composer sends.
- No control or result through contactus@ on this path.
- Do not assume sending the control proves a save.
- Use CTRL-ENC v1 for multiline notes.
- Do not replay old approvals.
