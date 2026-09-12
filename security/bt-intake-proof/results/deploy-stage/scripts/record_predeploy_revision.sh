#!/usr/bin/env bash
# Read-only preflight on the live VM. Records the actual deployed tree.
# Does not assume PR #14 or any other SHA. Does not install or restart.
set -euo pipefail

PREFIX="${BT_INTAKE_PREFIX:-/opt/bt-intake-proof}"
STATE="${BT_INTAKE_STATE:-/var/lib/bt-intake-proof}"
DEST="${STATE}/predeploy-revision.json"
SNAP="${STATE}/predeploy-tree"

if [[ ! -d "$PREFIX" ]]; then
  echo "missing install prefix: $PREFIX" >&2
  exit 1
fi

mkdir -p "$STATE"
if [[ -d "${PREFIX}/.git" ]]; then
  revision="$(git -C "$PREFIX" rev-parse HEAD)"
  revision_source="git"
else
  revision="$(PREFIX="$PREFIX" python3 - <<'PY'
import hashlib, os
from pathlib import Path
root = Path(os.environ["PREFIX"])
digest = hashlib.sha256()
for path in sorted(item for item in root.rglob("*") if item.is_file()):
    rel = path.relative_to(root).as_posix()
    if rel.startswith("secrets/") or "/.git/" in rel:
        continue
    digest.update(rel.encode())
    digest.update(b"\0")
    digest.update(path.read_bytes())
print(digest.hexdigest())
PY
)"
  revision_source="content_sha256"
fi

python3 - "$DEST" "$PREFIX" "$revision" "$revision_source" <<'PY'
import json, os, sys, time
dest, prefix, revision, source = sys.argv[1:]
payload = {
    "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "prefix": prefix,
    "revision": revision,
    "revision_source": source,
    "unit": "bt-intake-receiver",
    "note": "Actual pre-deploy revision. Do not assume PR #14 / 378ffcf.",
}
os.makedirs(os.path.dirname(dest), exist_ok=True)
with open(dest, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, indent=2)
    handle.write("\n")
print(json.dumps(payload, indent=2))
PY

if command -v rsync >/dev/null 2>&1; then
  mkdir -p "$SNAP"
  rsync -a --delete --exclude secrets --exclude results/live --exclude .git "$PREFIX/" "$SNAP/"
  echo "snapshot=$SNAP"
fi
echo "recorded=$DEST revision=$revision source=$revision_source"
