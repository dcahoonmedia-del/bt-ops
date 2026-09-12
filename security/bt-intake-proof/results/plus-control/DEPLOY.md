# Plus-control guarded deploy (project lead, real GCE host)

This Cursor cloud VM is **not** the GCE host and does **not** have
`/var/lib/bt-intake-proof/receipts.sqlite`. Do not pretend otherwise.

Package: `results/plus-control-release/`. Service/timer ship **disabled**.
No live mail. No credential minting. No filter/label changes.

| Ref | Value |
| --- | --- |
| Source commit | `3e67a45ecd9abccc4c8d6bf7865166c5089e1fa5` |
| Artifact commit | `11a19a3` (TRANSFER RAW) |
| Tarball SHA256 | `100823dcdcd8fe68f87e9f8eb40ac57ac78b50b466964a970943176fae252510` |
| Tree SHA256 | `7fdab6783b4505e4b75a9901649f92dfef0634f6d83d7a520aa31885d246ddd0` |

## Backup / migration / rollback (narrow)

The existing guarded transaction backs up **code, env, and unit files
only**. It never copies, resets, or rolls back:

- `/var/lib/bt-intake-proof/receipts.sqlite` (cases, approvals, nonces)
- token files under `/opt/bt-intake-proof/secrets/`

New tables (`plus_control_cursors`, `plus_control_seen`,
`plus_result_outbox`) are created on first plus poll via
`CREATE TABLE IF NOT EXISTS`. They do not rewrite cases.

Rollback:

```bash
sudo bash /opt/bt-intake-proof/scripts/rollback_to_predeploy.sh
```

That restores the previous tree/env/units. Cases and credentials stay.

## Host commands after the tarball is on the VM

See `results/plus-control-release/TRANSFER` for curl + sha256 + extract.

```bash
sudo bash /tmp/bt-intake-plus-control-src/bt-intake-proof/scripts/guarded_desk_roundtrip_deploy.sh
systemctl is-enabled bt-intake-receiver.service
systemctl is-enabled bt-plus-control-poll.timer || true
systemctl is-enabled bt-plus-control-poll.service || true
```

Plus units must remain disabled until preflight is READY.

## Preflight (read-only)

```bash
sudo -u btintake bash -lc 'cd /opt/bt-intake-proof && PYTHONPATH=/opt/bt-intake-proof/src python3 -m bt_intake_proof desk-plus-preflight'
```

Expect `daniel@` live profile, Control label present, isolated cursor
key, and an explicit sender blocker if
`/opt/bt-intake-proof/secrets/daniel_plus_result_send_token.json` is
missing. Do not add `gmail.settings` scope. Do not recreate filters.

Optional env reference (do not create the token file here):

`BT_DANIEL_PLUS_RESULT_SEND_TOKEN=/opt/bt-intake-proof/secrets/daniel_plus_result_send_token.json`

## Activation (only after READY and lead review)

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now bt-plus-control-poll.timer
sudo systemctl start bt-plus-control-poll.service
sudo -u btintake bash -lc 'cd /opt/bt-intake-proof && PYTHONPATH=/opt/bt-intake-proof/src python3 -m bt_intake_proof desk-plus-poll --once'
```

Do not enable if preflight lists sender or discovery blockers.
A missing sender must not consume a new decision.

## Verification

```bash
journalctl -u bt-plus-control-poll.service -n 50 --no-pager
sudo -u btintake bash -lc 'cd /opt/bt-intake-proof && PYTHONPATH=/opt/bt-intake-proof/src python3 -m bt_intake_proof desk-plus-preflight'
```

A later Work revision should produce **one**
`BT-INTAKE-PROOF-PLUS-RESULT-E9A8` to
`daniel+lead-desk-results@btpestcontrol.com` and no new contactus@
control/result. Never process `1a0979e37a0b0a94`.
