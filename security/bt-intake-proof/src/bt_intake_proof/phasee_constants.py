"""Phase E send-test constants. Internal B&T mail only."""

PHASEE_CASE_MARKER = "BT-INTAKE-PROOF-CASEMGR-PHASEE-E9A8"
PHASEE_SEND_MARKER = "BT-PHASE-E-SEND-E9A8-C4F1"
PHASEE_FROM = "contactus@btpestcontrol.com"
PHASEE_TO = "daniel@btpestcontrol.com"
PHASEE_SUBJECT = "BT-PHASE-E-SEND-E9A8-C4F1 internal send test"
PHASEE_BODY = """BT-PHASE-E-SEND-E9A8-C4F1

This is an internal B&T Phase E send test only.
It is not customer mail and does not book, price, or promise service.

B&T office"""
PHASEE_TIMING = "immediate_supervised"

STATUS_APPROVED = "approved"
STATUS_QUEUED = "queued"
STATUS_ATTEMPTED = "attempted_verification_pending"
STATUS_UNKNOWN = "unknown"
STATUS_SENT_VERIFIED = "sent_verified"
STATUS_RECEIPT_VERIFIED = "recipient_receipt_verified"
STATUS_FAILED = "failed"
STATUS_REJECTED = "rejected"
