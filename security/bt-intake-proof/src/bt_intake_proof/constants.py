"""Fixed intake-proof constants. No Cloud project is chosen here."""

from __future__ import annotations

MAILBOX = "contactus@btpestcontrol.com"
ALLOWED_SENDER = "daniel@btpestcontrol.com"
MARKER_PREFIX = "BT-INTAKE-PROOF-"
MARKER_RE = r"BT-INTAKE-PROOF-[A-Z0-9-]+"

GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
FORBIDDEN_GMAIL_SCOPES = (
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.insert",
    "https://www.googleapis.com/auth/gmail.addons.current.action.compose",
    "https://mail.google.com/",
)

GMAIL_PUSH_SERVICE_ACCOUNT = "gmail-api-push@system.gserviceaccount.com"
DEFAULT_TOPIC_ID = "bt-intake-proof-contactus"
DEFAULT_SUBSCRIPTION_ID = "bt-intake-proof-contactus-sub"
RECEIVER_SA_ID = "bt-intake-proof-receiver"
CLOUD_OWNER_HINT = "daniel@btpestcontrol.com"
CLOUD_PLATFORM_SCOPE = "https://www.googleapis.com/auth/cloud-platform"

# Pre-existing internal daniel→contactus thread (SENT from daniel@ on 2026-09-11).
# Use only this internal test thread for the old-thread reply. Never customer threads.
DESIGNATED_REPLY_THREAD_ID = "1a09242c087af92c"
DESIGNATED_REPLY_SUBJECT = "BT-PILOT-0911-TEST02"

DETECTION_EVENT_DRIVEN = "event_driven"
DETECTION_RECOVERY = "recovery"

CLASS_NEW = "new_message"
CLASS_REPLY = "reply"
CLASS_INELIGIBLE = "ineligible"
CLASS_DESK_CONTROL = "desk_control"

MARKER_DESK_CTRL = "BT-INTAKE-PROOF-DESK-CTRL-E9A8"
MARKER_DESK_BIND = "BT-INTAKE-PROOF-DESK-BIND-E9A8"
MARKER_DESK_RESULT = "BT-INTAKE-PROOF-DESK-RESULT-E9A8"

DISPATCH_PENDING = "pending"
DISPATCH_DELIVERED = "delivered"
DISPATCH_SKIPPED = "skipped"
DISPATCH_FAILED = "failed"

CODEX_TOOL_NAME = "lead_email_ingest"
CODEX_NAMESPACE = "external_untrusted"
