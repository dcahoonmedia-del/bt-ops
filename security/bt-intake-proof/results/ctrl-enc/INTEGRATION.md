# CTRL-ENC scorecard

| Item | Result | Notes |
| --- | --- | --- |
| Local codec / wrap / tamper tests | **PASS** (unit) | See `tests.test_desk_control_codec` |
| Old long `NOTE=` wrap (live failure mode) | **FAIL closed** (unit) | Does not authorize folded simple NOTE |
| 63-character hash | **FAIL closed** (unit) | `packet_hash_invalid` unchanged |
| Live CASEMGR walkthrough | **PASS** (Codex-observed) | Recorded in `results/casemgr-draft/CODEX_OBSERVED_WALKTHROUGH.md` |
| Phone / Mac-off | **BLOCKED** | Desktop-mediated only |
| This VM live mail / deploy | **BLOCKED** | No send; no SSH |
| Completed case mutation | **not done** | `BTC-contactus-1a096d60643b3b1a` left alone |
| Action 1 / 2 | **untouched** | Do not verify-recipient or recover `--execute` |
| Customer / proof send | **BLOCKED** | None authorized |
| New OAuth / scopes | **not requested** | Existing packet path only |
| Immutable release | **yes** | SHA256 `e04fe1b4…` source `f811fc1` artifact `5140331` |

Do not fabricate a model PASS from these unit tests.
