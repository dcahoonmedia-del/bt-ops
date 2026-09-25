"""Fixed arrival windows are selected from verified settings, not from the API payload.

Docs: https://intercom.help/fieldwork/en/articles/3472212-settings-arrival-time-windows
A fixed window follows the start time and does not depend on duration.
Manual windows do not move with the start. Typed GET and profile do not
return time_window_kind, so missing occurrence evidence stays unsupported.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

SCHEDULE_MODEL = "fixed_window_by_start_v1"
OCCURRENCE_FORM_FIELD = "service_appointment[appointment_occurrences_attributes][0][time_window_kind]"
OBSERVED_AT = "2026-09-25T03:10:00Z"
FRESH_UNTIL = "2026-09-26T03:10:00Z"
NY = ZoneInfo("America/New_York")
PROTECTED = (
    "work_order_id",
    "service_appointment_id",
    "customer_id",
    "location_id",
    "instructions",
    "private_notes",
)


def instant(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc).replace(microsecond=0)


def same_instant(left: Any, right: Any) -> bool:
    a, b = instant(left), instant(right)
    return a is not None and a == b


def clock_hhmm(value: Any) -> str | None:
    if isinstance(value, str) and len(value) >= 5 and value[2] == ":":
        hour, minute = value[:2], value[3:5]
        if hour.isdigit() and minute.isdigit():
            return f"{int(hour):02d}:{int(minute):02d}"
    parsed = instant(value)
    if parsed is None:
        return None
    local = parsed.astimezone(NY)
    return f"{local.hour:02d}:{local.minute:02d}"


def same_id(left: Any, right: Any) -> bool:
    def norm(value: Any) -> str:
        if isinstance(value, bool):
            return ""
        if isinstance(value, int):
            return str(value)
        text = str(value or "").strip()
        return str(int(text)) if text.isdigit() else text

    return norm(left) == norm(right) and norm(left) != ""


def same_routes(left: Any, right: Any) -> bool:
    def norm(value: Any) -> set[str]:
        if not isinstance(value, list):
            return set()
        return {str(int(item)) for item in value if isinstance(item, int) or (isinstance(item, str) and item.isdigit())}

    return norm(left) == norm(right) and bool(norm(left))


@dataclass(frozen=True)
class OccurrenceEvidence:
    work_order_id: str
    service_appointment_id: str
    customer_id: str
    location_id: str
    kind: str
    option_value: str
    observed_at: str = OBSERVED_AT
    fresh_until: str = FRESH_UNTIL
    source: str = "schedule_form_ui"
    field_name: str = OCCURRENCE_FORM_FIELD


@dataclass
class WindowEvidence:
    """Settings and occurrence observations. These are not API response fields."""

    company_source: str = "ui:/settings/account/time_windows"
    company_selection: str = "auto_select_fixed"
    time_zone: str = "America/New_York"
    windows: tuple[tuple[int, str, str], ...] = tuple((590 + hour, f"{8 + hour:02d}:00", f"{9 + hour:02d}:00") for hour in range(9))
    relative_windows: tuple[Any, ...] = ()
    observed_at: str = OBSERVED_AT
    fresh_until: str = FRESH_UNTIL
    api_exposes_mode: bool = False
    occurrences: dict[tuple[str, str], OccurrenceEvidence] = field(default_factory=dict)

    def with_occurrence(self, item: OccurrenceEvidence) -> "WindowEvidence":
        copied = WindowEvidence(
            company_source=self.company_source,
            company_selection=self.company_selection,
            time_zone=self.time_zone,
            windows=self.windows,
            relative_windows=self.relative_windows,
            observed_at=self.observed_at,
            fresh_until=self.fresh_until,
            api_exposes_mode=self.api_exposes_mode,
            occurrences=dict(self.occurrences),
        )
        copied.occurrences[(item.work_order_id, item.service_appointment_id)] = item
        return copied


def verified_window_evidence() -> WindowEvidence:
    evidence = WindowEvidence()
    tim = OccurrenceEvidence("8210560", "1501269", "644133", "727573", "fixed", "1")
    evidence.occurrences[(tim.work_order_id, tim.service_appointment_id)] = tim
    return evidence


def _fresh(observed_at: str, fresh_until: str, now: datetime) -> bool:
    start, end = instant(observed_at), instant(fresh_until)
    current = now.astimezone(timezone.utc).replace(microsecond=0)
    return start is not None and end is not None and start <= current <= end


def select_fixed_window(starts_at: str, evidence: WindowEvidence) -> tuple[int, str, str] | None:
    start = instant(starts_at)
    if start is None:
        return None
    local = start.astimezone(NY)
    for window_id, open_at, close_at in evidence.windows:
        opened = local.replace(hour=int(open_at[:2]), minute=int(open_at[3:5]), second=0, microsecond=0)
        closed = local.replace(hour=int(close_at[:2]), minute=int(close_at[3:5]), second=0, microsecond=0)
        if opened <= local < closed:
            return window_id, open_at, close_at
    return None


def _window_bounds(starts_at: str, open_at: str, close_at: str) -> tuple[str, str]:
    start = instant(starts_at)
    assert start is not None
    local = start.astimezone(NY)

    def at(hhmm: str) -> str:
        return local.replace(hour=int(hhmm[:2]), minute=int(hhmm[3:5]), second=0, microsecond=0).isoformat()

    return at(open_at), at(close_at)


def predict_fixed_shift(
    before: dict[str, Any],
    starts_at: str,
    duration: int,
    routes: list[int],
    evidence: WindowEvidence,
    now: datetime,
) -> tuple[dict[str, Any] | None, str]:
    if not evidence.api_exposes_mode and not _fresh(evidence.observed_at, evidence.fresh_until, now):
        return None, "window_evidence_stale: company fixed-window settings are outside their verified freshness window"
    if evidence.company_selection != "auto_select_fixed" or evidence.relative_windows:
        return None, "arrival_window_mode_unverified: company window selection is not the verified fixed catalog"
    item = evidence.occurrences.get((str(before.get("work_order_id")), str(before.get("service_appointment_id"))))
    if item is None:
        return None, "arrival_window_mode_unverified: API GET does not return time_window_kind, and this occurrence has no verified form evidence"
    if not _fresh(item.observed_at, item.fresh_until, now):
        return None, "window_evidence_stale: occurrence window evidence is outside its verified freshness window"
    if not same_id(before.get("customer_id"), item.customer_id) or not same_id(before.get("location_id"), item.location_id):
        return None, "arrival_window_mode_unverified: occurrence evidence identity does not match this customer and location"
    if item.kind == "manual":
        return None, "manual_window_does_not_follow_start: a manual window is not updated when the start time changes"
    if item.kind != "fixed" or item.option_value != "1":
        return None, "arrival_window_mode_unverified: occurrence window kind is not verified fixed"
    selected = select_fixed_window(starts_at, evidence)
    if selected is None:
        return None, "fixed_window_not_selected: start is outside the verified hourly windows; the outside-window fallback is not verified"
    window_id, open_at, close_at = selected
    new_start = instant(starts_at)
    assert new_start is not None
    new_end = new_start + timedelta(minutes=duration)
    window_start, window_end = _window_bounds(starts_at, open_at, close_at)
    after = dict(before)
    after["starts_at"] = new_start.astimezone(NY).replace(microsecond=0).isoformat()
    after["duration"] = duration
    after["service_route_ids"] = list(routes)
    after["ends_at"] = new_end.astimezone(NY).replace(microsecond=0).isoformat()
    after["finished_at"] = after["ends_at"]
    after["arrival_time_window"] = [window_start, window_end]
    after["arrival_time_window_start"] = open_at
    after["arrival_time_window_end"] = close_at
    after["schedule_model"] = SCHEDULE_MODEL
    after["arrival_coupling"] = "fixed_window_selected_by_start"
    after["fixed_window_id"] = window_id
    after["window_evidence_source"] = evidence.company_source
    after["occurrence_evidence_field"] = item.field_name
    return after, ""


def apply_fixed_window_double(row: dict[str, Any], evidence: WindowEvidence | None = None) -> None:
    """Fake transport stand-in for fixed-window selection. Not a live call."""
    evidence = evidence or verified_window_evidence()
    selected = select_fixed_window(str(row.get("starts_at") or ""), evidence)
    duration = row.get("duration")
    start = instant(row.get("starts_at"))
    if selected is None or start is None or isinstance(duration, bool) or not isinstance(duration, int):
        return
    window_id, open_at, close_at = selected
    window_start, window_end = _window_bounds(str(row.get("starts_at")), open_at, close_at)
    end = start + timedelta(minutes=duration)
    row["ends_at"] = end.astimezone(NY).replace(microsecond=0).isoformat()
    row["finished_at"] = row["ends_at"]
    row["arrival_time_window"] = [window_start, window_end]
    row["arrival_time_window_start"] = open_at
    row["arrival_time_window_end"] = close_at
    row["fixed_window_id"] = window_id


def compare_schedule(expected: dict[str, Any], actual: dict[str, Any], before: dict[str, Any]) -> list[dict[str, Any]]:
    mismatches: list[dict[str, Any]] = []

    def check(field: str, ok: bool, wanted: Any, seen: Any) -> None:
        if not ok:
            mismatches.append({"field": field, "expected": wanted, "actual": seen})

    check("starts_at", same_instant(expected.get("starts_at"), actual.get("starts_at")), expected.get("starts_at"), actual.get("starts_at"))
    check("duration", expected.get("duration") == actual.get("duration"), expected.get("duration"), actual.get("duration"))
    check("service_route_ids", same_routes(expected.get("service_route_ids"), actual.get("service_route_ids")), expected.get("service_route_ids"), actual.get("service_route_ids"))
    check("ends_at", same_instant(expected.get("ends_at"), actual.get("ends_at") or actual.get("finished_at")), expected.get("ends_at"), actual.get("ends_at") or actual.get("finished_at"))
    window = actual.get("arrival_time_window")
    wanted = expected.get("arrival_time_window") or []
    window_ok = isinstance(window, list) and len(window) == 2 and len(wanted) == 2 and same_instant(window[0], wanted[0]) and same_instant(window[1], wanted[1])
    check("arrival_time_window", window_ok, wanted, window)
    check("arrival_time_window_start", clock_hhmm(actual.get("arrival_time_window_start")) == expected.get("arrival_time_window_start"), expected.get("arrival_time_window_start"), actual.get("arrival_time_window_start"))
    check("arrival_time_window_end", clock_hhmm(actual.get("arrival_time_window_end")) == expected.get("arrival_time_window_end"), expected.get("arrival_time_window_end"), actual.get("arrival_time_window_end"))
    for field in PROTECTED:
        if field == "location_id":
            seen = actual.get("location_id") if actual.get("location_id") is not None else actual.get("service_location_id")
            check(field, same_id(before.get(field), seen), before.get(field), seen)
        elif field in {"work_order_id", "service_appointment_id", "customer_id"}:
            check(field, same_id(before.get(field), actual.get(field)), before.get(field), actual.get(field))
        else:
            check(field, before.get(field) == actual.get(field), before.get(field), actual.get(field))
    return mismatches
