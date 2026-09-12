#!/usr/bin/env python3
"""Verify an extracted desk-roundtrip release tree. No secrets allowed."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

SKIP_PREFIXES = ("secrets/", "results/live/", ".git/")
SKIP_PARTS = {"__pycache__", ".git"}
SKIP_SUFFIXES = (".pyc",)


def iter_files(root: Path) -> list[Path]:
    files = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if rel == "RELEASE.json" or any(rel.startswith(prefix) for prefix in SKIP_PREFIXES):
            continue
        if any(part in SKIP_PARTS for part in path.parts):
            continue
        if rel.endswith(SKIP_SUFFIXES):
            continue
        files.append(path)
    return files


def tree_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for path in iter_files(root):
        rel = path.relative_to(root).as_posix()
        digest.update(rel.encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=".")
    parser.add_argument("--hash-only", action="store_true")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    actual = tree_sha256(root)
    if args.hash_only:
        print(json.dumps({"ok": True, "tree_sha256": actual, "root": str(root)}))
        return 0
    secrets = root / "secrets"
    if secrets.exists() and any(secrets.glob("*.json")):
        print("FAIL: release tree contains secrets", file=sys.stderr)
        return 2
    release = json.loads((root / "RELEASE.json").read_text(encoding="utf-8"))
    expected = release.get("tree_sha256")
    if expected and actual != expected:
        print(json.dumps({"ok": False, "expected": expected, "actual": actual}))
        return 2
    print(json.dumps({"ok": True, "tree_sha256": actual, "root": str(root)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
