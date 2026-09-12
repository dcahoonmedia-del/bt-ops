# Stopped for Daniel — Google account-level decisions

Phase 1 cannot continue without choices only you can make. I did not pick a Cloud project, create billing, or authenticate `contactus@`.

## What I found

| Check | Result |
| --- | --- |
| Local `gcloud` / ADC / `GOOGLE_CLOUD_PROJECT` | Absent |
| Dedicated B&T Pub/Sub topic | Not created |
| `contactus@` Gmail API token (`gmail.readonly`) | Absent |
| Cursor Gmail MCP | Connected as **daniel@btpestcontrol.com**, with send/draft/label tools. Unused. Not a `users.watch` substitute. |

## Reply with these decisions

1. **Google Cloud project ID** I may use for this intake proof only. Example: `bt-intake-proof-2026`. I will not scan and pick an existing project.
2. Confirm I may, in **that project only**:
   - enable Gmail API and Pub/Sub API if they are off
   - create topic `bt-intake-proof-contactus`
   - create subscription `bt-intake-proof-contactus-sub`
   - grant `gmail-api-push@system.gserviceaccount.com` Pub/Sub Publisher
   - call Gmail `users.watch` for `contactus@btpestcontrol.com`
3. If that project needs **billing** enabled, you enable it. I will stop again if Google requires it.
4. **OAuth Desktop client** in that project, or tell me to create one after you name the project.
5. **Interactive consent as `contactus@btpestcontrol.com`** (not daniel@) for this scope only:
   `https://www.googleapis.com/auth/gmail.readonly`
   I will print the URL and wait. Do not grant send/modify.

## After watch is PASS — you send the mail

I will not send email or create drafts. Use only `daniel@btpestcontrol.com` → `contactus@btpestcontrol.com`.

Wait until I report `gmail_watch_registration = PASS`, then send:

| Test | Subject must include | Notes |
| --- | --- | --- |
| New message | `BT-INTAKE-PROOF-NEW-E9A8-7F3C` | New thread |
| Old-thread reply | `BT-INTAKE-PROOF-REPLY-E9A8-7F3C` | Reply on existing internal thread `1a09242c087af92c` / subject `BT-PILOT-0911-TEST02` |
| Recovery | `BT-INTAKE-PROOF-RECOVERY-E9A8-7F3C` | Send only after I say the receiver is stopped |

Do not use customer threads. Do not send customer mail into this proof.
