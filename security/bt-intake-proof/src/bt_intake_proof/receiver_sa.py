"""Create the authorized receiver SA and impersonate it. Never downloads a JSON key."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from .cloud_auth import impersonation_possible_without_key
from .constants import (
    ALLOWED_SENDER,
    DEFAULT_SUBSCRIPTION_ID,
    RECEIVER_SA_ID,
)
from .gates import cloud_token_path, project_id
from .oauth_consent import OAuthClientError
from .setup_google import subscription_path


class KeyCreationBlocked(RuntimeError):
    pass


def receiver_sa_email(pid: str | None = None) -> str:
    return f"{RECEIVER_SA_ID}@{pid or project_id()}.iam.gserviceaccount.com"


def _cloud_token() -> dict[str, Any]:
    path = cloud_token_path()
    if not path.exists():
        raise OAuthClientError("project-owner Cloud token is not present")
    return json.loads(path.read_text(encoding="utf-8"))


def _request(method: str, url: str, access_token: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
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
        raise OAuthClientError(f"{method} {url} HTTP {exc.code}: {detail}") from exc


def create_receiver_sa_and_grant(access_token: str, owner_email: str) -> dict[str, Any]:
    pid = project_id()
    sa_email = receiver_sa_email(pid)
    create_url = f"https://iam.googleapis.com/v1/projects/{pid}/serviceAccounts"
    try:
        _request(
            "POST",
            create_url,
            access_token,
            {
                "accountId": RECEIVER_SA_ID,
                "serviceAccount": {
                    "displayName": "B&T intake proof receiver",
                    "description": "Pull only bt-intake-proof-contactus-sub",
                },
            },
        )
        created = True
    except OAuthClientError as exc:
        if "already exists" not in str(exc).lower() and "ALREADY_EXISTS" not in str(exc):
            raise
        created = False

    sub = subscription_path(pid, DEFAULT_SUBSCRIPTION_ID)
    policy = _request("GET", f"https://pubsub.googleapis.com/v1/{sub}:getIamPolicy", access_token)
    bindings = list(policy.get("bindings") or [])
    member = f"serviceAccount:{sa_email}"
    found = any(
        item.get("role") == "roles/pubsub.subscriber" and member in (item.get("members") or [])
        for item in bindings
    )
    if not found:
        bindings.append({"role": "roles/pubsub.subscriber", "members": [member]})
        _request(
            "POST",
            f"https://pubsub.googleapis.com/v1/{sub}:setIamPolicy",
            access_token,
            {"policy": {"etag": policy.get("etag"), "bindings": bindings}},
        )

    sa_resource = f"projects/{pid}/serviceAccounts/{sa_email}"
    sa_policy = _request("POST", f"https://iam.googleapis.com/v1/{sa_resource}:getIamPolicy", access_token, {})
    sa_bindings = list(sa_policy.get("bindings") or [])
    owner_member = f"user:{owner_email or ALLOWED_SENDER}"
    token_creator = any(
        item.get("role") == "roles/iam.serviceAccountTokenCreator" and owner_member in (item.get("members") or [])
        for item in sa_bindings
    )
    if not token_creator:
        sa_bindings.append({"role": "roles/iam.serviceAccountTokenCreator", "members": [owner_member]})
        _request(
            "POST",
            f"https://iam.googleapis.com/v1/{sa_resource}:setIamPolicy",
            access_token,
            {"policy": {"etag": sa_policy.get("etag"), "bindings": sa_bindings}},
        )
    return {
        "service_account": sa_email,
        "created": created,
        "subscription": sub,
        "subscription_role": "roles/pubsub.subscriber",
        "project_wide_role_granted": False,
        "json_key_created": False,
        "token_creator": owner_member,
    }


def impersonate_receiver(access_token: str) -> str:
    sa_email = receiver_sa_email()
    body = {
        "delegates": [],
        "scope": ["https://www.googleapis.com/auth/pubsub"],
        "lifetime": "3600s",
    }
    result = _request(
        "POST",
        f"https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/{sa_email}:generateAccessToken",
        access_token,
        body,
    )
    token = str(result.get("accessToken") or "")
    if not token:
        raise OAuthClientError("impersonation returned no accessToken")
    return token


def pull_subscription(access_token: str, max_messages: int = 10) -> dict[str, Any]:
    sub = subscription_path(project_id(), DEFAULT_SUBSCRIPTION_ID)
    result = _request(
        "POST",
        f"https://pubsub.googleapis.com/v1/{sub}:pull",
        access_token,
        {"maxMessages": max_messages, "returnImmediately": True},
    )
    received = result.get("receivedMessages") or []
    return {
        "subscription": sub,
        "received_count": len(received),
        "message_ids": [item.get("message", {}).get("messageId") for item in received],
        "ack_ids_present": all(item.get("ackId") for item in received) if received else False,
        "raw_count": len(received),
        "received_messages": received,
    }


def refuse_json_key() -> None:
    probe = impersonation_possible_without_key()
    if not probe["adc_present"] and not probe["cloud_user_token_present"] and not probe["gce_metadata"]:
        raise KeyCreationBlocked(
            "This environment cannot impersonate yet because there is no project-owner Cloud login. "
            "A JSON service-account key was not created. Complete the Cloud OAuth URL as the project owner."
        )
