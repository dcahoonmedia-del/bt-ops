#!/usr/bin/env python3
"""Standalone daniel@ gmail.readonly OAuth bootstrap for the live host.

Does not import or change the contactus oauth_consent path. Does not start a
listener. Does not request send/modify/delete. Stdlib only so it can run on the
current /opt/bt-intake-proof host without deploying the new worker.

Daniel completes the Google consent screen. Codex runs this helper on the VM
and finishes the loopback-URL exchange from a 0600 file (not chat, not argv).
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import secrets
import stat
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

DANIEL = "daniel@btpestcontrol.com"
CONTACTUS = "contactus@btpestcontrol.com"
READONLY = "https://www.googleapis.com/auth/gmail.readonly"
FORBIDDEN = (
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.insert",
    "https://www.googleapis.com/auth/gmail.addons.current.action.compose",
    "https://mail.google.com/",
)
HOST_PREFIX = Path("/opt/bt-intake-proof")
HOST_SECRETS = HOST_PREFIX / "secrets"
HOST_STATE = Path("/var/lib/bt-intake-proof")
CLIENT_NAME = "gmail_oauth_client.json"
TOKEN_NAME = "daniel_gmail_readonly_token.json"
CONTACTUS_READONLY = "contactus_gmail_readonly_token.json"
CONTACTUS_SEND = "contactus_gmail_send_token.json"
SETUP_NAME = "daniel-oauth-setup.json"
AUTH_URL_NAME = "daniel-readonly-auth-url.txt"
REDIRECT_NAME = "daniel-oauth-redirect.url"
OWNER = "btintake"
SETUP_TTL_SEC = 15 * 60
WRITE_MARKERS = ("gmail.modify", "gmail.send", "gmail.compose", "gmail.insert", "mail.google.com/")


class BootstrapError(RuntimeError):
    pass


def _now() -> int:
    return int(time.time())


def _iso(ts: int) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


def _normalize_email(value: str | None) -> str:
    raw = str(value or "").strip().lower()
    if "<" in raw and ">" in raw:
        raw = raw[raw.rfind("<") + 1 : raw.rfind(">")].strip()
    return raw


def _redact(text: str) -> str:
    out = str(text or "")
    out = re.sub(r"code=[^&\s]+", "code=<redacted>", out, flags=re.I)
    out = re.sub(r"access_token=[^&\s]+", "access_token=<redacted>", out, flags=re.I)
    out = re.sub(r"refresh_token=[^&\s]+", "refresh_token=<redacted>", out, flags=re.I)
    return out


def _chmod600(path: Path) -> None:
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)


def _chown_btintake(path: Path) -> str | None:
    try:
        import pwd

        info = pwd.getpwnam(OWNER)
        os.chown(path, info.pw_uid, info.pw_gid)
        return OWNER
    except (KeyError, PermissionError, OSError):
        return None


def _atomic_write(path: Path, data: str, *, owner: bool = True) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(data, encoding="utf-8")
    _chmod600(tmp)
    owned = _chown_btintake(tmp) if owner else None
    os.replace(tmp, path)
    _chmod600(path)
    if owner:
        owned = _chown_btintake(path) or owned
    mode = stat.S_IMODE(path.stat().st_mode)
    return {"path": str(path), "mode": oct(mode), "owner": owned}


def _file_fingerprint(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    data = path.read_bytes()
    return {
        "path": str(path),
        "sha256": hashlib.sha256(data).hexdigest(),
        "size": len(data),
        "mtime_ns": path.stat().st_mtime_ns,
    }


def paths_from_env() -> dict[str, Path]:
    secrets_dir = Path(os.environ.get("DANIEL_OAUTH_SECRETS_DIR") or HOST_SECRETS)
    state_dir = Path(os.environ.get("DANIEL_OAUTH_STATE_DIR") or HOST_STATE)
    client = Path(os.environ.get("DANIEL_OAUTH_CLIENT") or secrets_dir / CLIENT_NAME)
    return {
        "secrets_dir": secrets_dir,
        "state_dir": state_dir,
        "client": client,
        "token": Path(os.environ.get("DANIEL_OAUTH_TOKEN") or secrets_dir / TOKEN_NAME),
        "setup": state_dir / SETUP_NAME,
        "auth_url": state_dir / AUTH_URL_NAME,
        "redirect": Path(os.environ.get("DANIEL_OAUTH_REDIRECT_FILE") or state_dir / REDIRECT_NAME),
        "contactus_readonly": secrets_dir / CONTACTUS_READONLY,
        "contactus_send": secrets_dir / CONTACTUS_SEND,
        "oauth_client": secrets_dir / CLIENT_NAME,
    }


def load_desktop_client(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise BootstrapError(f"Desktop OAuth client JSON is not present at {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BootstrapError("OAuth client file is not valid JSON") from exc
    if not isinstance(data, dict):
        raise BootstrapError("OAuth client file must be a JSON object")
    if "web" in data and "installed" not in data:
        raise BootstrapError("This is a Web client. Use the existing Desktop client.")
    installed = data.get("installed")
    if not isinstance(installed, dict):
        raise BootstrapError("Desktop client JSON must contain an 'installed' object")
    if not str(installed.get("client_id") or "").strip():
        raise BootstrapError("Desktop client JSON is missing client_id")
    return installed


def redirect_uri(installed: dict[str, Any]) -> str:
    uris = [str(item) for item in (installed.get("redirect_uris") or []) if item]
    for preferred in ("http://127.0.0.1/", "http://127.0.0.1", "http://localhost/", "http://localhost"):
        if preferred in uris:
            return preferred.rstrip("/") if preferred.endswith("/") and preferred.count("/") > 2 else preferred
    for uri in uris:
        if uri.startswith("http://127.0.0.1") or uri.startswith("http://localhost"):
            return uri
    raise BootstrapError("Desktop client has no loopback redirect_uri; refusing a public redirect")


def pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def parse_redirect(text: str) -> dict[str, str]:
    raw = (text or "").strip()
    if not raw:
        raise BootstrapError("empty authorization response")
    if raw.startswith("http://") or raw.startswith("https://"):
        parsed = urllib.parse.urlparse(raw)
        query = urllib.parse.parse_qs(parsed.query)
        if parsed.fragment:
            query.update(urllib.parse.parse_qs(parsed.fragment))
        if query.get("error"):
            raise BootstrapError(f"Google returned error: {query['error'][0]}")
        code = (query.get("code") or [""])[0]
        state = (query.get("state") or [""])[0]
        if not code:
            raise BootstrapError("redirect URL does not contain a code parameter")
        return {"code": code, "state": state}
    raise BootstrapError("redirect file must contain the full loopback URL, not a bare code")


def _gmail_scopes(scopes: list[str]) -> list[str]:
    found = []
    for scope in scopes:
        if scope in FORBIDDEN or "googleapis.com/auth/gmail" in scope or scope == "https://mail.google.com/":
            found.append(scope)
    return found


def assert_readonly_scopes(scopes: list[str]) -> None:
    if any(scope in FORBIDDEN for scope in scopes):
        raise BootstrapError("token includes forbidden Gmail scopes")
    gmail = _gmail_scopes(scopes)
    if READONLY not in scopes:
        raise BootstrapError("token does not include gmail.readonly")
    if set(gmail) != {READONLY}:
        raise BootstrapError("token Gmail scopes are not exactly gmail.readonly")


def _post_form(url: str, data: dict[str, str]) -> dict[str, Any]:
    body = urllib.parse.urlencode(data).encode("utf-8")
    request = urllib.request.Request(url, data=body, method="POST")
    request.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = _redact(exc.read().decode("utf-8", errors="replace"))
        raise BootstrapError(f"token endpoint HTTP {exc.code}") from exc


def _get_json(url: str, access_token: str | None = None) -> dict[str, Any]:
    request = urllib.request.Request(url, method="GET")
    if access_token:
        request.add_header("Authorization", f"Bearer {access_token}")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise BootstrapError(f"HTTP {exc.code} from verification endpoint") from exc


def start(paths: dict[str, Path] | None = None) -> dict[str, Any]:
    dest = paths or paths_from_env()
    client = load_desktop_client(dest["client"])
    redirect = redirect_uri(client)
    verifier, challenge = pkce_pair()
    state = secrets.token_urlsafe(32)
    created = _now()
    params = {
        "client_id": client["client_id"],
        "redirect_uri": redirect,
        "response_type": "code",
        "scope": READONLY,
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "false",
        "login_hint": DANIEL,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)
    if any(marker in url for marker in WRITE_MARKERS):
        raise BootstrapError("refusing to build an OAuth URL that mentions write scopes")
    if CONTACTUS.split("@")[0] in urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get("login_hint", [""])[0]:
        raise BootstrapError("refusing contactus login_hint on daniel bootstrap")
    setup = {
        "created_at": _iso(created),
        "expires_at": _iso(created + SETUP_TTL_SEC),
        "expires_unix": created + SETUP_TTL_SEC,
        "state": state,
        "code_verifier": verifier,
        "redirect_uri": redirect,
        "client_id": client["client_id"],
        "token_uri": client.get("token_uri") or "https://oauth2.googleapis.com/token",
        "scope": READONLY,
        "mailbox_required": DANIEL,
        "listener": "none",
    }
    _atomic_write(dest["setup"], json.dumps(setup, indent=2) + "\n")
    _atomic_write(dest["auth_url"], url + "\n")
    return {
        "status": "READY_FOR_DANIEL_READONLY_CONSENT",
        "mailbox_required": DANIEL,
        "scope": READONLY,
        "redirect_uri": redirect,
        "listener": "none",
        "pkce": "S256",
        "auth_url_file": str(dest["auth_url"]),
        "setup_file": str(dest["setup"]),
        "redirect_file": str(dest["redirect"]),
        "token_file": str(dest["token"]),
        "expires_at": setup["expires_at"],
        "contactus_oauth_untouched": True,
        "authorization_url_printed": False,
    }


def _wipe(path: Path) -> None:
    if path.exists():
        try:
            path.write_bytes(b"\0" * max(path.stat().st_size, 1))
        except OSError:
            pass
        try:
            path.unlink()
        except OSError:
            pass


def abort(paths: dict[str, Path] | None = None) -> dict[str, Any]:
    dest = paths or paths_from_env()
    _wipe(dest["setup"])
    _wipe(dest["auth_url"])
    _wipe(dest["redirect"])
    return {"status": "ABORTED", "setup_wiped": True, "token_written": False}


def _load_setup(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise BootstrapError("setup state is missing or expired")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BootstrapError("setup state is unreadable") from exc
    if int(data.get("expires_unix") or 0) < _now():
        raise BootstrapError("setup state expired")
    if not data.get("state") or not data.get("code_verifier"):
        raise BootstrapError("setup state is incomplete")
    return data


def contactus_fingerprints(paths: dict[str, Path]) -> dict[str, dict[str, Any] | None]:
    return {
        "contactus_readonly": _file_fingerprint(paths["contactus_readonly"]),
        "contactus_send": _file_fingerprint(paths["contactus_send"]),
        "oauth_client": _file_fingerprint(paths["oauth_client"]),
    }


def assert_contactus_unchanged(before: dict[str, dict[str, Any] | None], paths: dict[str, Path]) -> None:
    after = contactus_fingerprints(paths)
    if before != after:
        raise BootstrapError("refusing to continue: existing contactus/client files changed")


def complete(
    *,
    redirect_file: Path | None = None,
    paths: dict[str, Path] | None = None,
    post_form=_post_form,
    get_json=_get_json,
) -> dict[str, Any]:
    dest = paths or paths_from_env()
    before = contactus_fingerprints(dest)
    setup = _load_setup(dest["setup"])
    source = Path(redirect_file or dest["redirect"])
    if not source.exists():
        raise BootstrapError(f"redirect file is missing: {source}")
    parsed = parse_redirect(source.read_text(encoding="utf-8"))
    if parsed["state"] != setup["state"]:
        raise BootstrapError("OAuth state mismatch")
    client = load_desktop_client(dest["client"])
    if str(client.get("client_id") or "") != str(setup.get("client_id") or ""):
        raise BootstrapError("client_id does not match short-lived setup")
    token = post_form(
        str(setup.get("token_uri") or "https://oauth2.googleapis.com/token"),
        {
            "code": parsed["code"],
            "client_id": client["client_id"],
            "client_secret": str(client.get("client_secret") or ""),
            "redirect_uri": str(setup["redirect_uri"]),
            "grant_type": "authorization_code",
            "code_verifier": str(setup["code_verifier"]),
        },
    )
    scopes = str(token.get("scope") or "").split()
    assert_readonly_scopes(scopes)
    access = str(token.get("access_token") or "")
    if not access:
        raise BootstrapError("token response missing access_token")
    if not token.get("refresh_token"):
        raise BootstrapError("token response missing refresh_token")
    info = get_json("https://oauth2.googleapis.com/tokeninfo", access)
    info_scopes = str(info.get("scope") or " ".join(scopes)).split()
    assert_readonly_scopes(info_scopes)
    profile = get_json("https://gmail.googleapis.com/gmail/v1/users/me/profile", access)
    email = _normalize_email(str(profile.get("emailAddress") or info.get("email") or ""))
    if email != DANIEL:
        raise BootstrapError(f"authenticated mailbox is {email or '(unknown)'}, expected {DANIEL}")
    assert_contactus_unchanged(before, dest)
    if dest["token"].resolve() in {
        dest["contactus_readonly"].resolve(),
        dest["contactus_send"].resolve(),
        dest["oauth_client"].resolve(),
        dest["client"].resolve(),
    }:
        raise BootstrapError("refusing to overwrite an existing contactus or client file")
    record = {
        "token_uri": setup.get("token_uri") or "https://oauth2.googleapis.com/token",
        "client_id": client["client_id"],
        "client_secret": client.get("client_secret"),
        "refresh_token": token.get("refresh_token"),
        "access_token": access,
        "token_type": token.get("token_type") or "Bearer",
        "scopes": [READONLY],
        "scope": READONLY,
        "email": email,
        "account": email,
        "mailbox": DANIEL,
        "purpose": "desk_sent_corroboration_readonly",
    }
    written = _atomic_write(dest["token"], json.dumps(record, indent=2) + "\n")
    assert_contactus_unchanged(before, dest)
    _wipe(dest["setup"])
    _wipe(dest["auth_url"])
    _wipe(source)
    return {
        "status": "PASS",
        "email": email,
        "scopes": [READONLY],
        "readonly_only": True,
        "full_identity_pass": False,
        "token_file": written["path"],
        "token_mode": written["mode"],
        "token_owner": written["owner"],
        "contactus_tokens_unchanged": True,
        "setup_wiped": True,
        "listener": "none",
    }


def status(paths: dict[str, Path] | None = None) -> dict[str, Any]:
    dest = paths or paths_from_env()
    setup_ok = dest["setup"].exists()
    expires = None
    if setup_ok:
        try:
            expires = json.loads(dest["setup"].read_text(encoding="utf-8")).get("expires_at")
        except (OSError, json.JSONDecodeError):
            expires = "unreadable"
    return {
        "status": "READY" if dest["token"].exists() else "BLOCKED",
        "token_present": dest["token"].exists(),
        "setup_present": setup_ok,
        "setup_expires_at": expires,
        "auth_url_present": dest["auth_url"].exists(),
        "mailbox_required": DANIEL,
        "scope": READONLY,
        "listener": "none",
        "contactus_readonly_present": dest["contactus_readonly"].exists(),
        "contactus_send_present": dest["contactus_send"].exists(),
        "oauth_client_present": dest["client"].exists(),
    }


def _print(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True), flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Standalone daniel@ gmail.readonly bootstrap")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("start")
    complete_p = sub.add_parser("complete")
    complete_p.add_argument("--redirect-file", help="0600 file containing the Mac loopback redirect URL")
    sub.add_parser("abort")
    sub.add_parser("status")
    args = parser.parse_args(argv)
    try:
        if args.cmd == "start":
            _print(start())
            return 0
        if args.cmd == "complete":
            _print(complete(redirect_file=Path(args.redirect_file) if args.redirect_file else None))
            return 0
        if args.cmd == "abort":
            _print(abort())
            return 0
        _print(status())
        return 0
    except BootstrapError as exc:
        _print({"status": "FAIL", "error": _redact(str(exc)), "mailbox_required": DANIEL, "scope": READONLY})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
