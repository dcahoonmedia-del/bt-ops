"""Live Google calls limited to the four authorized intake-proof resources."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlencode

from .constants import (
    DEFAULT_SUBSCRIPTION_ID,
    DEFAULT_TOPIC_ID,
    GMAIL_PUSH_SERVICE_ACCOUNT,
    GMAIL_READONLY_SCOPE,
    MAILBOX,
)
from .eligibility import normalize_email
from .gates import allow_resource_create, project_id, token_path
from .gmail_readonly import GmailAuthError, assert_readonly_credentials
from .oauth_consent import OAuthClientError, _get_json, refresh_access_token
from .setup_google import subscription_path, topic_path
from .store import ReceiptStore


class BillingRequired(RuntimeError):
    pass


def _token_record() -> dict[str, Any]:
    path = token_path()
    if not path.exists():
        raise OAuthClientError("contactus Gmail token is not present")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert_readonly_credentials(list(data.get("scopes") or [data.get("scope") or GMAIL_READONLY_SCOPE]), data.get("email") or "")
    return data


class HttpReadOnlyGmail:
    """users.getProfile / watch / history / messages.get / threads.get only."""

    def __init__(self, access_token: str, email: str, scopes: list[str]) -> None:
        assert_readonly_credentials(scopes, email)
        self.access_token = access_token
        self.email = normalize_email(email)
        self.scopes = list(scopes)

    def _get(self, url: str) -> dict[str, Any]:
        return _get_json(url, self.access_token)

    def profile(self) -> dict[str, Any]:
        return gmail_profile(self.access_token)

    def history(self, start_history_id: str) -> dict[str, Any]:
        params = {"startHistoryId": str(start_history_id), "historyTypes": "messageAdded"}
        url = "https://gmail.googleapis.com/gmail/v1/users/me/history?" + urlencode(params)
        merged: dict[str, Any] = {"history": [], "historyId": str(start_history_id)}
        while url:
            page = self._get(url)
            merged["history"].extend(page.get("history") or [])
            if page.get("historyId"):
                merged["historyId"] = str(page["historyId"])
            token = page.get("nextPageToken")
            if not token:
                break
            url = "https://gmail.googleapis.com/gmail/v1/users/me/history?" + urlencode(
                {**params, "pageToken": token}
            )
        return merged

    def get_message(self, message_id: str, fmt: str = "raw") -> dict[str, Any]:
        if fmt not in {"raw", "metadata", "minimal", "full"}:
            raise GmailAuthError(f"unsupported Gmail format {fmt}")
        return self._get(
            f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}?format={fmt}"
        )

    def get_thread_message_ids(self, thread_id: str) -> list[str]:
        thread = self._get(
            f"https://gmail.googleapis.com/gmail/v1/users/me/threads/{thread_id}?format=minimal"
        )
        ids = []
        for message in thread.get("messages") or []:
            mid = message.get("id")
            if mid:
                ids.append(mid)
        return ids


def contactus_gmail() -> HttpReadOnlyGmail:
    token = refresh_access_token()
    return HttpReadOnlyGmail(
        str(token.get("access_token") or ""),
        str(token.get("email") or MAILBOX),
        list(token.get("scopes") or [GMAIL_READONLY_SCOPE]),
    )


def gmail_profile(access_token: str) -> dict[str, Any]:
    profile = _get_json("https://gmail.googleapis.com/gmail/v1/users/me/profile", access_token)
    email = normalize_email(str(profile.get("emailAddress") or ""))
    if email != MAILBOX:
        raise GmailAuthError(f"authenticated mailbox is {email or '(unknown)'}, expected {MAILBOX}")
    return profile


def gmail_watch(access_token: str, topic: str) -> dict[str, Any]:
    body = json.dumps({"topicName": topic, "labelIds": ["INBOX"], "labelFilterBehavior": "include"}).encode("utf-8")
    request = urllib.request.Request(
        "https://gmail.googleapis.com/gmail/v1/users/me/watch",
        data=body,
        method="POST",
    )
    request.add_header("Authorization", f"Bearer {access_token}")
    request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise OAuthClientError(f"users.watch HTTP {exc.code}: {detail}") from exc


def _pubsub_request(method: str, url: str, access_token: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Authorization", f"Bearer {access_token}")
    if payload is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        lowered = detail.lower()
        if exc.code in {403, 400} and ("billing" in lowered or "accountdisabled" in lowered or "billing account" in lowered):
            raise BillingRequired(detail) from exc
        raise OAuthClientError(f"Pub/Sub HTTP {exc.code}: {detail}") from exc


def try_authorized_pubsub(access_token: str, pid: str) -> dict[str, Any]:
    """Create only the authorized topic, IAM grant, and subscription."""
    if not allow_resource_create():
        raise RuntimeError("resource create is not authorized")
    if project_id() != pid:
        raise RuntimeError("refusing to use a project ID that Daniel did not set")
    topic = topic_path(pid, DEFAULT_TOPIC_ID)
    sub = subscription_path(pid, DEFAULT_SUBSCRIPTION_ID)
    member = f"serviceAccount:{GMAIL_PUSH_SERVICE_ACCOUNT}"
    _pubsub_request("PUT", f"https://pubsub.googleapis.com/v1/{topic}", access_token, {})
    policy = _pubsub_request("GET", f"https://pubsub.googleapis.com/v1/{topic}:getIamPolicy", access_token)
    bindings = list(policy.get("bindings") or [])
    found = any(
        item.get("role") == "roles/pubsub.publisher" and member in (item.get("members") or [])
        for item in bindings
    )
    if not found:
        bindings.append({"role": "roles/pubsub.publisher", "members": [member]})
        _pubsub_request(
            "POST",
            f"https://pubsub.googleapis.com/v1/{topic}:setIamPolicy",
            access_token,
            {"policy": {"bindings": bindings}},
        )
    try:
        _pubsub_request(
            "PUT",
            f"https://pubsub.googleapis.com/v1/{sub}",
            access_token,
            {"topic": topic, "ackDeadlineSeconds": 60},
        )
    except OAuthClientError as exc:
        if "already exists" not in str(exc).lower() and "ALREADY_EXISTS" not in str(exc):
            raise
    return {
        "topic": topic,
        "subscription": sub,
        "gmail_publisher_member": member,
        "gmail_publisher_granted": True,
    }


def register_watch_on_existing_topic(store: ReceiptStore) -> dict[str, Any]:
    """Register users.watch only. Does not create Cloud resources."""
    pid = project_id()
    token = refresh_access_token()
    access = str(token.get("access_token") or "")
    profile = gmail_profile(access)
    topic = topic_path(pid, DEFAULT_TOPIC_ID)
    sub = subscription_path(pid, DEFAULT_SUBSCRIPTION_ID)
    evidence: dict[str, Any] = {
        "project_id": pid,
        "mailbox": MAILBOX,
        "topic": topic,
        "subscription": sub,
        "gmail_consent": {
            "email": token.get("email"),
            "scopes": token.get("scopes"),
            "readonly_only": True,
            "profile_history_id": str(profile.get("historyId") or ""),
        },
    }
    try:
        watch = gmail_watch(access, topic)
    except OAuthClientError as exc:
        evidence["status"] = "BLOCKED"
        evidence["blocked_on"] = "gmail_watch"
        evidence["error"] = str(exc)
        return evidence
    store.upsert_watch(
        MAILBOX,
        history_id=str(watch.get("historyId") or profile.get("historyId") or ""),
        expiration=str(watch.get("expiration") or ""),
        topic=topic,
    )
    evidence["watch"] = {
        "status": "PASS" if watch.get("historyId") else "FAIL",
        "history_id": str(watch.get("historyId") or ""),
        "expiration": str(watch.get("expiration") or ""),
        "topic": topic,
        "mailbox": MAILBOX,
        "subscription": sub,
    }
    evidence["status"] = evidence["watch"]["status"]
    return evidence


def run_authorized_setup(store: ReceiptStore) -> dict[str, Any]:
    pid = project_id()
    token = _token_record()
    access = str(token.get("access_token") or "")
    profile = gmail_profile(access)
    evidence: dict[str, Any] = {
        "project_id": pid,
        "mailbox": MAILBOX,
        "gmail_consent": {
            "email": token.get("email"),
            "scopes": token.get("scopes"),
            "readonly_only": True,
            "profile_history_id": str(profile.get("historyId") or ""),
        },
        "pubsub": None,
        "watch": None,
    }
    try:
        evidence["pubsub"] = try_authorized_pubsub(access, pid)
    except BillingRequired as exc:
        evidence["status"] = "BLOCKED"
        evidence["blocked_on"] = "billing"
        evidence["message"] = (
            "Google requires a billing account on project bt-intake-proof before Pub/Sub can be created. "
            "I did not link or choose a billing account."
        )
        evidence["error"] = str(exc)
        return evidence
    except (OAuthClientError, GmailAuthError, RuntimeError) as exc:
        evidence["status"] = "BLOCKED"
        evidence["blocked_on"] = "gcp_admin_credentials"
        evidence["message"] = (
            "contactus@ Gmail read-only cannot create Pub/Sub resources. "
            "I need a Cloud login that can create only the authorized topic, subscription, and IAM grant in bt-intake-proof, "
            "or you can create those three in Cloud Console and I will register users.watch."
        )
        evidence["error"] = str(exc)
        return evidence

    topic = evidence["pubsub"]["topic"]
    try:
        watch = gmail_watch(access, topic)
    except OAuthClientError as exc:
        evidence["status"] = "BLOCKED"
        evidence["blocked_on"] = "gmail_watch"
        evidence["error"] = str(exc)
        return evidence
    store.upsert_watch(
        MAILBOX,
        history_id=str(watch.get("historyId") or profile.get("historyId") or ""),
        expiration=str(watch.get("expiration") or ""),
        topic=topic,
    )
    evidence["watch"] = {
        "status": "PASS" if watch.get("historyId") else "FAIL",
        "history_id": str(watch.get("historyId") or ""),
        "expiration": str(watch.get("expiration") or ""),
        "topic": topic,
        "mailbox": MAILBOX,
        "subscription": evidence["pubsub"]["subscription"],
    }
    evidence["status"] = evidence["watch"]["status"]
    return evidence
