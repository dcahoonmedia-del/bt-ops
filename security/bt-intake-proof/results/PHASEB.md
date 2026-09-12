# Phase B — cloud-hosted intake proof

VM `bt-intake-cloud` is on-spec (e2-small, us-east1-c, receiver SA, 20 GB). No JSON key. OS Login is unset.

Receiver `bt-intake-receiver` is **enabled + active**. Latest start `2026-09-12T03:26:58Z` after adding `btintake` to the docker group (install used `id docker` instead of `getent group docker`).

- Identity: `gce_metadata`, receiver SA matches, `json_key_created=false`, no impersonation
- Watch cursor `6008066` preserved across restart (no rewind)
- Service PID has docker group `1001`
- Isolation image `bt-ops-codex-isolation:0.154.0` and volume `codex-iso-chatgpt-home` present
- Receipts: 0 before CLOUD markers

`contactus` SSH works. Instance metadata SSH key is still in the wrong Edit-page columns (`btadmin` login fails). Mac-off CLOUD-NEW send is next.
