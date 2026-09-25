# Write contract v7

Patch only. Codex owns `fieldwork.py`, Auth0, server, and config. This package calls `client.patch_work_order_fields(before, after, fields)` and `client.get_api_role()`. It does not build the Fieldwork form body.

## Notes (`update_work_order_notes`)

Propose reads the occurrence, then the customer and service location. Lead, inactive, missing, or conflicting status fails before a proposal is stored. `instructions` and `private_notes` must be strings. Before and after include customer id, status, location id, name, tax rate, and address id, plus the arrival-window fields copied unchanged.

Stale and readback rebuild that same snapshot. A customer, location, note, schedule, or arrival change after propose is `stale_state`. Readback must match after, including the preserved arrival window.

## Schedule (`update_work_order_schedule`)

Single occurrence only. `starts_at` is offset ISO8601 (`-04:00` / `+00:00`, not `Z` and not naive). `duration` is a positive integer minute count. `service_route_ids` is a non-empty list of positive integers. Recurring `repeat_type`, `series_id`, `recurring`, or more than one `appointment_occurrences` entry is `recurring_series_rejected`. Arrival-window keys in the payload are unknown fields and are not written. Before and after keep the four arrival-window values from the typed read.

Execute sends `patch_work_order_fields(before, after, ["starts_at", "duration", "service_route_ids"])`. Notes send only the text fields present in the payload. The PATCH path and nested `service_appointment[appointment_occurrences_attributes][][id]` body belong to Codex's client. This service never sends an `appointment_occurrence` root.

## Older tests

`tests/test_write_contract_v7.py` is the contract. Older execute tests that set `settings.api_role` and do not provide `get_api_role()` now fail closed at `readonly_api_role` before operator, stale, or schema gates. Older work-order note proposals that omit `customer_id` and `service_location_id` on the occurrence fail `identity_mismatch`. Those files were not edited.

## Role

Execute calls `client.get_api_role()`. Missing, unreadable, or readonly (including `read_only`) blocks with `readonly_api_role` and does not patch. `FIELDWORK_API_ROLE` / `settings.api_role` is not the execute gate. Older tests that set `api_role="writer"` without `get_api_role()` now stop at readonly. That is the live profile safeguard.

## Create

Customer create and one-time work-order create are documented in `CREATE_CONTRACT.md`. An empty occurrence list or empty line-item list is `missing_field`. Messaging and arrival-window writes stay closed.
