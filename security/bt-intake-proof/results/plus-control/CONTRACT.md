# Plus-address control transport

Internal Lead Desk controls may use:

`daniel@btpestcontrol.com` → `daniel+lead-desk@btpestcontrol.com`

The contactus@ path remains authorized and unchanged.

Plus-address authorization requires a message retrieved through the
authenticated daniel@ Gmail account with SENT present, exact From/To,
and current control metadata. Inbound Authentication-Results are not
required on this path. Header spoofing and copied control syntax are
not enough.

CLI: `desk-plus-control --message-id <daniel-gmail-id>`

Gmail filters were not changed.

## Offline proof

`PYTHONPATH=src python3 -m unittest discover -s tests` → 255 passed, 1 skipped.

`tests/test_desk_plus_control.py` covers one plus-path `revise_draft`
save, contactus@ still working, and spoof/SENT/recipient/customer-copy
rejections.
