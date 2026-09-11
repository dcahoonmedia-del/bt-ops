# Isolated Codex ExternalMessage Test 0

Disposable Docker harness for a controlled security test:

Can customer-controlled email text enter Codex as `ExternalMessage` / `toolOutput` without being treated as user authorization?

This directory never mounts Gmail, Fieldwork, B&T workspace files, browser profiles, or host Codex config.

## Pins

- `openai-codex==0.154.0`
- `openai-codex-cli-bin==0.154.0`

## Isolation

The host runner starts a read-only container on a dedicated bridge network with:

- `CODEX_HOME` on tmpfs
- plugins, remote plugin catalog, apps, hooks, shell, snapshots, multi-agent, and web search disabled
- empty marketplace allowlist
- browser/computer access denied
- no API key unless you later approve one
- host-side `tcpdump` during startup

## Run

```bash
bash security/codex-external-isolation/scripts/host_run.sh
```

Phase 1 is isolation preflight. Phase 2 (real thread/turn) starts only if preflight passes and an official ChatGPT/Codex login is already available inside the container.

Latest isolated run: **BLOCKED** after a passing preflight because the disposable runtime has no ChatGPT/Codex login. See `RESULTS.md`.
