# Plus-control guarded deploy (project lead, real GCE host)

This Cursor cloud VM is **not** the GCE host and does **not** have
`/var/lib/bt-intake-proof/receipts.sqlite`. Do not pretend otherwise.

Package: `results/plus-control-release/`. Service/timer ship **disabled**.
No live mail. No credential minting. No filter/label changes.

| Ref | Value |
| --- | --- |
| Source commit | regenerated after the project-lead correction; see `RELEASE.json` |
| Artifact commit | same as TRANSFER `SOURCE_COMMIT` after rebuild |
| Tarball SHA256 | see `results/plus-control-release/MANIFEST.json` |
| Tree SHA256 | see `results/plus-control-release/RELEASE.json` |

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
systemctl is-enabled bt-plus-control-poll.timer
systemctl is-enabled bt-plus-control-poll.service
```

The guarded path copies plus units when they exist in the release and
runs `systemctl disable` on both (never `enable`). Expect
`disabled` / `static` here. Plus units must remain disabled until
preflight is READY and the project lead activates them.

Expect `READY` only when the live Daniel profile matches, Control and
Results labels resolve by name, and the sender passes live tokeninfo.
A missing Results label or a failed label list is BLOCKED.

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
