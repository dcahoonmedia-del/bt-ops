"""Create only the dedicated B&T watch/Pub/Sub resources after Daniel approves."""

from __future__ import annotations

from typing import Any

from .constants import (
    DEFAULT_SUBSCRIPTION_ID,
    DEFAULT_TOPIC_ID,
    GMAIL_PUSH_SERVICE_ACCOUNT,
    MAILBOX,
)
from .gates import allow_resource_create, diagnose_google, project_id
from .store import ReceiptStore


def blocked_setup(diagnosis: dict[str, Any] | None = None) -> dict[str, Any]:
    diagnosis = diagnosis or diagnose_google()
    return {
        "status": diagnosis.get("status") or "BLOCKED",
        "phase": "google_setup",
        "watch_registered": False,
        "pubsub_ready": False,
        "history_id": None,
        "expiration": None,
        "diagnosis": diagnosis,
        "stop": True,
        "message": diagnosis.get("next_action"),
    }


def topic_path(pid: str, topic_id: str = DEFAULT_TOPIC_ID) -> str:
    return f"projects/{pid}/topics/{topic_id}"


def subscription_path(pid: str, subscription_id: str = DEFAULT_SUBSCRIPTION_ID) -> str:
    return f"projects/{pid}/subscriptions/{subscription_id}"


def register_watch(store: ReceiptStore, gmail: Any, topic: str) -> dict[str, Any]:
    response = gmail.watch(topic, label_ids=["INBOX"])
    history_id = str(response.get("historyId") or "")
    expiration = str(response.get("expiration") or "")
    store.upsert_watch(MAILBOX, history_id=history_id, expiration=expiration, topic=topic)
    return {
        "status": "PASS" if history_id else "FAIL",
        "history_id": history_id,
        "expiration": expiration,
        "topic": topic,
        "mailbox": MAILBOX,
        "watch_response_keys": sorted(response.keys()),
    }


def ensure_pubsub(pid: str, publisher: Any, subscriber: Any) -> dict[str, Any]:
    if not allow_resource_create():
        raise RuntimeError("refusing to create Pub/Sub resources without BT_GCP_ALLOW_RESOURCE_CREATE=yes")
    if project_id() != pid:
        raise RuntimeError("refusing to use a project ID that Daniel did not set")
    topic = topic_path(pid)
    sub = subscription_path(pid)
    publisher.create_topic(request={"name": topic})
    policy = publisher.get_iam_policy(request={"resource": topic})
    member = f"serviceAccount:{GMAIL_PUSH_SERVICE_ACCOUNT}"
    binding_found = False
    for binding in policy.bindings:
        if binding.role == "roles/pubsub.publisher" and member in binding.members:
            binding_found = True
            break
    if not binding_found:
        policy.bindings.add(role="roles/pubsub.publisher", members=[member])
        publisher.set_iam_policy(request={"resource": topic, "policy": policy})
    try:
        subscriber.create_subscription(request={"name": sub, "topic": topic, "ackDeadlineSeconds": 60})
    except Exception as exc:  # noqa: BLE001
        if "AlreadyExists" not in type(exc).__name__ and "already exists" not in str(exc).lower():
            raise
    return {
        "topic": topic,
        "subscription": sub,
        "gmail_publisher_member": member,
        "gmail_publisher_granted": True,
    }
