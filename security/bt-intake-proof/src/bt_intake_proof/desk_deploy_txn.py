"""Quiesced desk-roundtrip deploy transaction.

Backs up code, env, and unit only. Never copies, resets, or rolls back SQLite
or token files. Does not print env values or secrets.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import shutil
import stat
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .desk_deploy_env import load_env_file, merge_desk_roundtrip_env, render_env

UNIT_NAME = "bt-intake-receiver.service"
BACKUP_SUBDIR = "predeploy-backups"
POINTER_NAME = "current-predeploy.json"
SKIP_DIR_NAMES = {".git", "__pycache__"}


class DeployError(RuntimeError):
    def __init__(self, reason: str, *, mutated: bool = False) -> None:
        super().__init__(reason)
        self.reason = reason
        self.mutated = mutated


@dataclass
class DeployPaths:
    source: Path
    prefix: Path
    state: Path
    etc: Path
    systemd_dir: Path
    unit_name: str = UNIT_NAME
    systemctl: list[str] | None = None
    require_root: bool = True
    health: Callable[[], None] | None = None
    after_unit_hook: Callable[[], None] | None = None


def _now_stamp() -> str:
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())


def _rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def skip_rel(rel: str) -> bool:
    if rel == "secrets" or rel.startswith("secrets/"):
        return True
    if rel == "results/live" or rel.startswith("results/live/"):
        return True
    parts = rel.split("/")
    if any(part in SKIP_DIR_NAMES for part in parts):
        return True
    return rel.endswith(".pyc")


def report(event: str, **fields: Any) -> dict[str, Any]:
    blocked = {"env", "body", "token", "secret", "access_token", "refresh_token", "client_secret"}
    payload = {"event": event}
    for key, value in fields.items():
        if key in blocked:
            continue
        payload[key] = value
    print(json.dumps(payload, default=str), flush=True)
    return payload


def file_meta(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    st = path.stat()
    payload = {
        "present": True,
        "mode": oct(stat.S_IMODE(st.st_mode)),
        "uid": st.st_uid,
        "gid": st.st_gid,
        "size": st.st_size,
    }
    if path.is_file():
        payload["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        payload["ino"] = st.st_ino
        payload["dev"] = st.st_dev
    return payload


def sqlite_identity(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    wal = path.with_name(path.name + "-wal")
    shm = path.with_name(path.name + "-shm")
    return {
        "main": file_meta(path),
        "wal": file_meta(wal) if wal.exists() else {"present": False},
        "shm": file_meta(shm) if shm.exists() else {"present": False},
    }


def token_meta(prefix: Path) -> dict[str, Any]:
    secrets_dir = prefix / "secrets"
    return {
        "contactus_readonly": file_meta(secrets_dir / "contactus_gmail_readonly_token.json"),
        "contactus_send": file_meta(secrets_dir / "contactus_gmail_send_token.json"),
        "oauth_client": file_meta(secrets_dir / "gmail_oauth_client.json"),
        "daniel": file_meta(secrets_dir / "daniel_gmail_readonly_token.json"),
    }


def copy_code_tree(src: Path, dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for path in sorted(src.rglob("*")):
        rel = _rel(path, src)
        if skip_rel(rel):
            continue
        dest = dst / rel
        if path.is_dir():
            dest.mkdir(parents=True, exist_ok=True)
        elif path.is_file():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)


def remove_stale_code(src: Path, dst: Path) -> None:
    if not dst.exists():
        return
    for path in sorted(dst.rglob("*"), reverse=True):
        rel = _rel(path, dst)
        if skip_rel(rel):
            continue
        counterpart = src / rel
        if path.is_file() and not counterpart.is_file():
            path.unlink()
        elif path.is_dir() and not counterpart.exists() and not any(path.iterdir()):
            path.rmdir()


def restore_file(src: Path | None, dest: Path, *, present: bool, meta: dict[str, Any] | None) -> None:
    if not present:
        if dest.exists() or dest.is_symlink():
            dest.unlink()
        return
    assert src is not None
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    if meta:
        os.chmod(dest, int(meta["mode"], 8))
        try:
            os.chown(dest, int(meta["uid"]), int(meta["gid"]))
        except PermissionError:
            pass


def run_systemctl(paths: DeployPaths, *args: str) -> subprocess.CompletedProcess[str]:
    cmd = list(paths.systemctl or ["systemctl"]) + list(args)
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def service_state(paths: DeployPaths) -> str:
    listed = run_systemctl(paths, "list-unit-files", paths.unit_name)
    if listed.returncode != 0 and "not-found" in (listed.stderr or "").lower():
        return "missing"
    active = run_systemctl(paths, "is-active", paths.unit_name)
    raw = (active.stdout or "").strip() or (active.stderr or "").strip()
    if raw in {"active", "activating", "reloading"}:
        return "active"
    if raw in {"failed"}:
        return "failed"
    if raw in {"inactive", "dead"}:
        return "inactive"
    if "not-found" in raw or "could not be found" in raw:
        return "missing"
    return raw or "inactive"


def quiesce(paths: DeployPaths) -> str:
    before = service_state(paths)
    if before in {"active", "activating", "reloading", "failed"}:
        stopped = run_systemctl(paths, "stop", paths.unit_name)
        if stopped.returncode != 0 and before != "failed":
            raise DeployError(f"failed to stop {paths.unit_name}", mutated=False)
    after = service_state(paths)
    if after == "active":
        raise DeployError("receiver still active after stop", mutated=False)
    return before


def restore_service_state(paths: DeployPaths, prior: str) -> str:
    run_systemctl(paths, "daemon-reload")
    if prior == "active":
        started = run_systemctl(paths, "start", paths.unit_name)
        if started.returncode != 0:
            raise DeployError("failed to restore active service state", mutated=True)
    elif prior in {"inactive", "failed", "missing"}:
        run_systemctl(paths, "stop", paths.unit_name)
    return service_state(paths)


def unique_backup_dir(state: Path) -> Path:
    root = state / BACKUP_SUBDIR
    root.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(root, 0o700)
    except PermissionError:
        pass
    for _ in range(8):
        dest = root / f"{_now_stamp()}-{secrets.token_hex(4)}"
        try:
            dest.mkdir(mode=0o700)
            return dest
        except FileExistsError:
            continue
    raise DeployError("could not allocate a unique backup directory")


def backup_host(paths: DeployPaths, *, service_before: str) -> dict[str, Any]:
    dest = unique_backup_dir(paths.state)
    code_src = paths.prefix if paths.prefix.exists() else None
    if code_src:
        copy_code_tree(code_src, dest / "tree")
    env_path = paths.etc / "env"
    env_present = env_path.exists()
    env_meta = file_meta(env_path) if env_present else {"present": False}
    if env_present:
        shutil.copy2(env_path, dest / "env")
        os.chmod(dest / "env", 0o600)
    unit_path = paths.systemd_dir / paths.unit_name
    unit_present = unit_path.exists()
    unit_meta = file_meta(unit_path) if unit_present else {"present": False}
    if unit_present:
        shutil.copy2(unit_path, dest / "unit")
    sqlite = paths.state / "receipts.sqlite"
    manifest = {
        "backup_id": dest.name,
        "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "prefix": str(paths.prefix),
        "state": str(paths.state),
        "etc": str(paths.etc),
        "unit_name": paths.unit_name,
        "code_present": bool(code_src),
        "env_present": env_present,
        "env_meta": env_meta,
        "unit_present": unit_present,
        "unit_meta": unit_meta,
        "service_state": service_before,
        "sqlite": sqlite_identity(sqlite),
        "tokens": token_meta(paths.prefix),
        "sqlite_restored": False,
        "tokens_restored": False,
        "note": "Code/env/unit only. Do not revert receipts or approvals.",
    }
    (dest / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    os.chmod(dest / "manifest.json", 0o600)
    pointer = {
        "backup_id": dest.name,
        "dir": str(dest),
        "recorded_at": manifest["recorded_at"],
    }
    pointer_path = paths.state / POINTER_NAME
    pointer_path.write_text(json.dumps(pointer, indent=2) + "\n", encoding="utf-8")
    os.chmod(pointer_path, 0o600)
    return manifest


def load_manifest(state: Path, backup_id: str | None = None) -> tuple[Path, dict[str, Any]]:
    if backup_id:
        dest = state / BACKUP_SUBDIR / backup_id
    else:
        pointer = state / POINTER_NAME
        if not pointer.exists():
            raise DeployError("missing current-predeploy pointer")
        data = json.loads(pointer.read_text(encoding="utf-8"))
        dest = Path(data["dir"])
    manifest_path = dest / "manifest.json"
    if not dest.is_dir() or not manifest_path.exists():
        raise DeployError("backup directory or manifest missing")
    return dest, json.loads(manifest_path.read_text(encoding="utf-8"))


def restore_backup(paths: DeployPaths, manifest: dict[str, Any], dest: Path) -> dict[str, Any]:
    if manifest.get("code_present"):
        tree = dest / "tree"
        copy_code_tree(tree, paths.prefix)
        remove_stale_code(tree, paths.prefix)
    restore_file(
        dest / "env" if manifest.get("env_present") else None,
        paths.etc / "env",
        present=bool(manifest.get("env_present")),
        meta=manifest.get("env_meta") if manifest.get("env_present") else None,
    )
    restore_file(
        dest / "unit" if manifest.get("unit_present") else None,
        paths.systemd_dir / paths.unit_name,
        present=bool(manifest.get("unit_present")),
        meta=manifest.get("unit_meta") if manifest.get("unit_present") else None,
    )
    prior = str(manifest.get("service_state") or "inactive")
    try:
        current = restore_service_state(paths, prior)
        service_ok = current == prior or (prior == "active" and current == "active")
    except DeployError:
        current = service_state(paths)
        service_ok = False
    sqlite_now = sqlite_identity(paths.state / "receipts.sqlite")
    tokens_now = token_meta(paths.prefix)
    sqlite_ok = sqlite_now == manifest.get("sqlite")
    tokens_ok = _tokens_same(manifest.get("tokens") or {}, tokens_now)
    env_ok = _file_restored(paths.etc / "env", manifest.get("env_present"), dest / "env")
    unit_ok = _file_restored(paths.systemd_dir / paths.unit_name, manifest.get("unit_present"), dest / "unit")
    ok = service_ok and sqlite_ok and tokens_ok and env_ok and unit_ok
    return {
        "ok": ok,
        "service_state": current,
        "sqlite_unchanged": sqlite_ok,
        "tokens_unchanged": tokens_ok,
        "env_restored": env_ok,
        "unit_restored": unit_ok,
        "backup_id": manifest.get("backup_id"),
    }


def _file_restored(dest: Path, present: Any, backup: Path) -> bool:
    if not present:
        return not dest.exists()
    if not dest.exists() or not backup.exists():
        return False
    return dest.read_bytes() == backup.read_bytes()


def _tokens_same(before: dict[str, Any], after: dict[str, Any]) -> bool:
    return before == after


def preflight(paths: DeployPaths) -> list[str]:
    checks: list[str] = []
    if paths.require_root and os.geteuid() != 0:
        raise DeployError("run as root on the GCE VM")
    if not paths.source.is_dir() or not (paths.source / "src" / "bt_intake_proof").is_dir():
        raise DeployError("release tree missing src/bt_intake_proof")
    checks.append("source")
    secrets_dir = paths.source / "secrets"
    if secrets_dir.exists() and any(secrets_dir.glob("*.json")):
        raise DeployError("release tree contains secrets")
    checks.append("no_source_secrets")
    cloud_host = paths.source / "src" / "bt_intake_proof" / "cloud_host.py"
    if cloud_host.exists() and "execute_due_sends(" in cloud_host.read_text(encoding="utf-8"):
        raise DeployError("cloud_host still calls execute_due_sends")
    checks.append("desk_execute_only")
    release = paths.source / "RELEASE.json"
    if release.exists():
        expected = json.loads(release.read_text(encoding="utf-8")).get("tree_sha256")
        actual = _tree_sha256(paths.source)
        if expected and actual != expected:
            raise DeployError("release tree hash mismatch")
        checks.append("release_hash")
    if not paths.prefix.is_dir():
        raise DeployError("missing install prefix")
    checks.append("prefix")
    sqlite = paths.state / "receipts.sqlite"
    if not sqlite.is_file():
        raise DeployError("missing receipts.sqlite; refusing to create or reset it")
    checks.append("sqlite_present")
    ctl = list(paths.systemctl or ["systemctl"])
    if not shutil.which(ctl[0]) and not Path(ctl[0]).exists():
        raise DeployError("systemctl is not available")
    checks.append("systemctl")
    if not (paths.source / "systemd" / paths.unit_name).is_file() and not (
        paths.systemd_dir / paths.unit_name
    ).exists():
        raise DeployError("unit file missing from release and host")
    checks.append("unit_available")
    return checks


def _tree_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        rel = _rel(path, root)
        if rel == "RELEASE.json" or skip_rel(rel):
            continue
        digest.update(rel.encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()


def apply_release(paths: DeployPaths) -> None:
    copy_code_tree(paths.source, paths.prefix)
    remove_stale_code(paths.source, paths.prefix)
    paths.etc.mkdir(parents=True, exist_ok=True)
    existing = load_env_file(paths.etc / "env")
    merged = merge_desk_roundtrip_env(existing, prefix=str(paths.prefix), state=str(paths.state))
    env_path = paths.etc / "env"
    env_path.write_text(render_env(merged), encoding="utf-8")
    os.chmod(env_path, 0o640)
    unit_src = paths.source / "systemd" / paths.unit_name
    if unit_src.is_file():
        paths.systemd_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(unit_src, paths.systemd_dir / paths.unit_name)
        os.chmod(paths.systemd_dir / paths.unit_name, 0o644)
    if paths.after_unit_hook:
        paths.after_unit_hook()


def verify_quiesced_evidence(manifest: dict[str, Any], paths: DeployPaths) -> None:
    sqlite_now = sqlite_identity(paths.state / "receipts.sqlite")
    if sqlite_now != manifest.get("sqlite"):
        raise DeployError("sqlite identity changed during deploy", mutated=True)
    if not _tokens_same(manifest.get("tokens") or {}, token_meta(paths.prefix)):
        raise DeployError("token files changed during deploy", mutated=True)


def default_health(paths: DeployPaths) -> None:
    if paths.health:
        paths.health()
        return
    script = paths.prefix / "scripts" / "desk_roundtrip_health.sh"
    if script.exists():
        completed = subprocess.run(["bash", str(script)], check=False)
        if completed.returncode != 0:
            raise DeployError("health check failed", mutated=True)


def deploy(paths: DeployPaths) -> dict[str, Any]:
    mutated = False
    manifest = None
    dest = None
    try:
        checks = preflight(paths)
        report("preflight", ok=True, checks=checks)
        prior = quiesce(paths)
        report("quiesced", service_state_before=prior)
        manifest = backup_host(paths, service_before=prior)
        dest = paths.state / BACKUP_SUBDIR / str(manifest["backup_id"])
        report("backup", backup_id=manifest["backup_id"], env_present=manifest["env_present"], unit_present=manifest["unit_present"])
        mutated = True
        try:
            apply_release(paths)
            verify_quiesced_evidence(manifest, paths)
            restore_service_state(paths, prior)
            if prior == "active":
                default_health(paths)
        except DeployError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise DeployError(f"{type(exc).__name__}", mutated=True) from exc
        result = {
            "deployment": "PASS",
            "rollback": "NOT_NEEDED",
            "mutated": True,
            "backup_id": manifest["backup_id"],
            "service_state_before": prior,
            "service_state_after": service_state(paths),
            "sqlite_unchanged": True,
            "tokens_unchanged": True,
        }
        report("deploy_result", **result)
        return result
    except DeployError as exc:
        rollback_status = "NOT_ATTEMPTED"
        rollback_detail = None
        if mutated and manifest is not None and dest is not None:
            rollback_detail = restore_backup(paths, manifest, dest)
            rollback_status = "PASS" if rollback_detail.get("ok") else "FAIL"
            report("rollback_result", **rollback_detail, status=rollback_status)
        result = {
            "deployment": "FAIL",
            "rollback": rollback_status,
            "mutated": mutated,
            "backup_id": (manifest or {}).get("backup_id") if manifest else None,
            "sqlite_unchanged": True if not mutated else (rollback_detail or {}).get("sqlite_unchanged"),
            "tokens_unchanged": True if not mutated else (rollback_detail or {}).get("tokens_unchanged"),
            "reason": exc.reason,
        }
        report("deploy_result", **result)
        return result


def rollback(paths: DeployPaths, backup_id: str | None = None) -> dict[str, Any]:
    dest, manifest = load_manifest(paths.state, backup_id)
    prior = quiesce(paths)
    detail = restore_backup(paths, manifest, dest)
    result = {
        "deployment": "NOT_ATTEMPTED",
        "rollback": "PASS" if detail.get("ok") else "FAIL",
        "mutated": False,
        "backup_id": manifest.get("backup_id"),
        "service_state_before": prior,
        "service_state_after": detail.get("service_state"),
        "sqlite_unchanged": detail.get("sqlite_unchanged"),
        "tokens_unchanged": detail.get("tokens_unchanged"),
        "env_restored": detail.get("env_restored"),
        "unit_restored": detail.get("unit_restored"),
    }
    report("rollback_result", **result)
    return result


def record_only(paths: DeployPaths) -> dict[str, Any]:
    """Snapshot code/env/unit after quiesce. Does not copy the new tree."""
    if paths.require_root and os.geteuid() != 0:
        raise DeployError("run as root on the GCE VM")
    prior = quiesce(paths)
    manifest = backup_host(paths, service_before=prior)
    restore_service_state(paths, prior)
    result = {"ok": True, "backup_id": manifest["backup_id"], "service_state": prior}
    report("recorded", **result)
    return result


def paths_from_env(source: Path) -> DeployPaths:
    return DeployPaths(
        source=source,
        prefix=Path(os.environ.get("BT_INTAKE_PREFIX", "/opt/bt-intake-proof")),
        state=Path(os.environ.get("BT_INTAKE_STATE", "/var/lib/bt-intake-proof")),
        etc=Path(os.environ.get("BT_INTAKE_ETC", "/etc/bt-intake-proof")),
        systemd_dir=Path(os.environ.get("BT_INTAKE_SYSTEMD_DIR", "/etc/systemd/system")),
        unit_name=os.environ.get("BT_INTAKE_UNIT", UNIT_NAME),
        systemctl=os.environ.get("BT_INTAKE_SYSTEMCTL", "systemctl").split(),
        require_root=os.environ.get("BT_INTAKE_REQUIRE_ROOT", "1") not in {"0", "false", "no"},
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Guarded desk-roundtrip deploy transaction")
    sub = parser.add_subparsers(dest="cmd", required=True)
    dep = sub.add_parser("deploy")
    dep.add_argument("--source", required=True)
    rec = sub.add_parser("record")
    rec.add_argument("--source", default=".")
    rb = sub.add_parser("rollback")
    rb.add_argument("--backup-id", default="")
    args = parser.parse_args(argv)
    source = Path(getattr(args, "source", ".")).resolve()
    paths = paths_from_env(source)
    if args.cmd == "deploy":
        result = deploy(paths)
        return 0 if result.get("deployment") == "PASS" else 2
    if args.cmd == "record":
        record_only(paths)
        return 0
    result = rollback(paths, args.backup_id or None)
    return 0 if result.get("rollback") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
