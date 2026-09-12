import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

from bt_intake_proof.desk_deploy_txn import (
    BACKUP_SUBDIR,
    DeployPaths,
    deploy,
    rollback,
)
from bt_intake_proof.store import ReceiptStore


FAKE_SYSTEMCTL = r'''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
path = Path(os.environ["BT_FAKE_SYSTEMCTL_STATE"])
data = json.loads(path.read_text(encoding="utf-8"))
args = sys.argv[1:]
if args and args[0] == "list-unit-files":
    sys.exit(0)
if args[:1] == ["is-active"]:
    print("active" if data.get("active") else "inactive")
    sys.exit(0 if data.get("active") else 3)
if args[:1] == ["stop"]:
    data["active"] = False
    data["calls"] = data.get("calls") or []
    data["calls"].append(args)
    path.write_text(json.dumps(data))
    sys.exit(0)
if args[:1] == ["start"]:
    data["calls"] = data.get("calls") or []
    data["calls"].append(args)
    if data.get("fail_start"):
        path.write_text(json.dumps(data))
        sys.exit(1)
    data["active"] = True
    path.write_text(json.dumps(data))
    sys.exit(0)
if args[:1] == ["daemon-reload"]:
    data["calls"] = data.get("calls") or []
    data["calls"].append(args)
    path.write_text(json.dumps(data))
    sys.exit(0)
print("unexpected", args, file=sys.stderr)
sys.exit(2)
'''


class DeskDeployTxnTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.prefix = self.root / "opt"
        self.state = self.root / "var"
        self.etc = self.root / "etc"
        self.systemd = self.root / "systemd"
        self.source = self.root / "release"
        self.state.mkdir()
        self.etc.mkdir()
        self.systemd.mkdir()
        self._write_installed()
        self._write_release()
        self.ctl = self.root / "fake-systemctl"
        self.ctl.write_text(FAKE_SYSTEMCTL, encoding="utf-8")
        self.ctl.chmod(0o755)
        self.ctl_state = self.root / "fake-systemctl.state"
        self.ctl_state.write_text(json.dumps({"active": True, "calls": []}), encoding="utf-8")
        os.environ["BT_FAKE_SYSTEMCTL_STATE"] = str(self.ctl_state)

    def tearDown(self) -> None:
        os.environ.pop("BT_FAKE_SYSTEMCTL_STATE", None)
        self.tmp.cleanup()

    def _write_installed(self) -> None:
        (self.prefix / "src" / "bt_intake_proof").mkdir(parents=True)
        (self.prefix / "src" / "bt_intake_proof" / "old.py").write_text("OLD=1\n", encoding="utf-8")
        secrets = self.prefix / "secrets"
        secrets.mkdir()
        for name in (
            "contactus_gmail_readonly_token.json",
            "contactus_gmail_send_token.json",
            "gmail_oauth_client.json",
            "daniel_gmail_readonly_token.json",
        ):
            path = secrets / name
            path.write_text(json.dumps({"marker": name, "keep": True}), encoding="utf-8")
            path.chmod(0o600)
        store = ReceiptStore(self.state / "receipts.sqlite")
        store.conn.execute("CREATE TABLE IF NOT EXISTS evidence (id INTEGER PRIMARY KEY, note TEXT)")
        store.conn.execute("INSERT INTO evidence (note) VALUES ('phase-e-keep')")
        store.conn.execute(
            "CREATE TABLE IF NOT EXISTS case_decisions (id INTEGER PRIMARY KEY, decision TEXT)"
        )
        store.conn.execute("INSERT INTO case_decisions (decision) VALUES ('phase-e-consumed')")
        store.close()
        (self.etc / "env").write_text("LEGACY=keep\nBT_INTAKE_MODE=isolated_test\n", encoding="utf-8")
        os.chmod(self.etc / "env", 0o640)
        (self.systemd / "bt-intake-receiver.service").write_text("[Service]\nExecStart=/old\n", encoding="utf-8")

    def _write_release(self, *, cloud_host: str | None = None) -> None:
        pkg = self.source / "src" / "bt_intake_proof"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").write_text("", encoding="utf-8")
        (pkg / "cloud_host.py").write_text(
            cloud_host
            or "def serve():\n    from .desk_runtime import finish_desk_roundtrip\n    return finish_desk_roundtrip\n",
            encoding="utf-8",
        )
        (self.source / "systemd").mkdir(exist_ok=True)
        (self.source / "systemd" / "bt-intake-receiver.service").write_text(
            "[Service]\nExecStart=/new\n",
            encoding="utf-8",
        )
        (self.source / "scripts").mkdir(exist_ok=True)
        (self.source / "scripts" / "desk_roundtrip_health.sh").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")

    def _paths(self, **extra) -> DeployPaths:
        return DeployPaths(
            source=self.source,
            prefix=self.prefix,
            state=self.state,
            etc=self.etc,
            systemd_dir=self.systemd,
            systemctl=[str(self.ctl)],
            require_root=False,
            health=lambda: None,
            **extra,
        )

    def _sqlite_bytes(self) -> bytes:
        return (self.state / "receipts.sqlite").read_bytes()

    def _token_bytes(self) -> dict[str, bytes]:
        return {
            path.name: path.read_bytes()
            for path in (self.prefix / "secrets").glob("*.json")
        }

    def _ctl(self) -> dict:
        return json.loads(self.ctl_state.read_text(encoding="utf-8"))

    def test_missing_systemctl_fails_before_mutation(self) -> None:
        env_before = (self.etc / "env").read_bytes()
        unit_before = (self.systemd / "bt-intake-receiver.service").read_bytes()
        sqlite_before = self._sqlite_bytes()
        tokens_before = self._token_bytes()
        paths = self._paths()
        paths.systemctl = [str(self.root / "missing-systemctl")]
        result = deploy(paths)
        self.assertEqual(result["deployment"], "FAIL")
        self.assertEqual(result["rollback"], "NOT_ATTEMPTED")
        self.assertFalse(result["mutated"])
        self.assertFalse((self.state / BACKUP_SUBDIR).exists())
        self.assertEqual((self.etc / "env").read_bytes(), env_before)
        self.assertEqual((self.systemd / "bt-intake-receiver.service").read_bytes(), unit_before)
        self.assertEqual(self._sqlite_bytes(), sqlite_before)
        self.assertEqual(self._token_bytes(), tokens_before)
        self.assertTrue(self._ctl()["active"])
        self.assertTrue((self.prefix / "src" / "bt_intake_proof" / "old.py").exists())

    def test_missing_source_fails_before_mutation(self) -> None:
        paths = self._paths()
        paths.source = self.root / "missing-release"
        result = deploy(paths)
        self.assertEqual(result["deployment"], "FAIL")
        self.assertEqual(result["rollback"], "NOT_ATTEMPTED")
        self.assertFalse(result["mutated"])
        self.assertFalse((self.state / BACKUP_SUBDIR).exists())
        self.assertTrue(self._ctl()["active"])

    def test_failure_after_env_unit_change_rolls_back(self) -> None:
        env_before = (self.etc / "env").read_bytes()
        unit_before = (self.systemd / "bt-intake-receiver.service").read_bytes()
        sqlite_before = self._sqlite_bytes()
        tokens_before = self._token_bytes()

        def boom() -> None:
            self.assertIn("BT_INTAKE_MODE=isolated_test", (self.etc / "env").read_text(encoding="utf-8"))
            self.assertIn("ExecStart=/new", (self.systemd / "bt-intake-receiver.service").read_text(encoding="utf-8"))
            raise RuntimeError("injected failure after env/unit")

        result = deploy(self._paths(after_unit_hook=boom))
        self.assertEqual(result["deployment"], "FAIL")
        self.assertEqual(result["rollback"], "PASS")
        self.assertTrue(result["mutated"])
        self.assertTrue(result["sqlite_unchanged"])
        self.assertTrue(result["tokens_unchanged"])
        self.assertEqual((self.etc / "env").read_bytes(), env_before)
        self.assertEqual((self.systemd / "bt-intake-receiver.service").read_bytes(), unit_before)
        self.assertEqual(self._sqlite_bytes(), sqlite_before)
        self.assertEqual(self._token_bytes(), tokens_before)
        store = ReceiptStore(self.state / "receipts.sqlite")
        try:
            notes = [row[0] for row in store.conn.execute("SELECT note FROM evidence")]
            decisions = [row[0] for row in store.conn.execute("SELECT decision FROM case_decisions")]
        finally:
            store.close()
        self.assertEqual(notes, ["phase-e-keep"])
        self.assertEqual(decisions, ["phase-e-consumed"])
        self.assertTrue((self.prefix / "src" / "bt_intake_proof" / "old.py").exists())
        self.assertFalse((self.prefix / "src" / "bt_intake_proof" / "cloud_host.py").exists())
        self.assertTrue(self._ctl()["active"])

    def test_retry_keeps_prior_backup(self) -> None:
        def boom() -> None:
            raise RuntimeError("fail once")

        first = deploy(self._paths(after_unit_hook=boom))
        second = deploy(self._paths(after_unit_hook=boom))
        self.assertEqual(first["rollback"], "PASS")
        self.assertEqual(second["rollback"], "PASS")
        self.assertNotEqual(first["backup_id"], second["backup_id"])
        backups = sorted(p.name for p in (self.state / BACKUP_SUBDIR).iterdir() if p.is_dir())
        self.assertEqual(len(backups), 2)
        self.assertIn(first["backup_id"], backups)
        self.assertIn(second["backup_id"], backups)

    def test_successful_deploy_then_manual_rollback(self) -> None:
        sqlite_before = self._sqlite_bytes()
        tokens_before = self._token_bytes()
        env_before = (self.etc / "env").read_bytes()
        unit_before = (self.systemd / "bt-intake-receiver.service").read_bytes()
        result = deploy(self._paths())
        self.assertEqual(result["deployment"], "PASS")
        self.assertEqual(result["rollback"], "NOT_NEEDED")
        self.assertTrue((self.prefix / "src" / "bt_intake_proof" / "cloud_host.py").exists())
        self.assertIn("BT_DANIEL_GMAIL_TOKEN", (self.etc / "env").read_text(encoding="utf-8"))
        self.assertIn("ExecStart=/new", (self.systemd / "bt-intake-receiver.service").read_text(encoding="utf-8"))
        rolled = rollback(self._paths())
        self.assertEqual(rolled["rollback"], "PASS")
        self.assertEqual(rolled["deployment"], "NOT_ATTEMPTED")
        self.assertTrue(rolled["env_restored"])
        self.assertTrue(rolled["unit_restored"])
        self.assertTrue(rolled["sqlite_unchanged"])
        self.assertTrue(rolled["tokens_unchanged"])
        self.assertEqual((self.etc / "env").read_bytes(), env_before)
        self.assertEqual((self.systemd / "bt-intake-receiver.service").read_bytes(), unit_before)
        self.assertEqual(self._sqlite_bytes(), sqlite_before)
        self.assertEqual(self._token_bytes(), tokens_before)
        self.assertTrue((self.prefix / "src" / "bt_intake_proof" / "old.py").exists())

    def test_report_does_not_include_env_or_secrets(self) -> None:
        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf):
            deploy(self._paths())
        printed = buf.getvalue()
        self.assertNotIn("LEGACY=keep", printed)
        self.assertNotIn("keep\": true", printed)
        self.assertNotIn("phase-e-keep", printed)
        self.assertNotIn("client_secret", printed)
        for line in printed.splitlines():
            json.loads(line)


if __name__ == "__main__":
    unittest.main()
