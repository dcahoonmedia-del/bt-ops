# Phase 2 core reads

Offline only. No live Fieldwork calls, no deployment, and no write expansion. Approval and Auth0 behavior are unchanged.

API base remains `https://api3.fieldworkhq.com/v3.1`. Public specs fetched from `https://api.fieldworkhq.com/apidocs/api/v3/`.

## Customers

- `GET /customers/search` documents `query`, `filter[customer_status]`, `filter[postal_code]`, `filter[date_added]`, `start_date`, `end_date`, `page`, and `per_page`.
- `filter[postal_code]` is documented as postal code. It is not documented as billing-only.
- `filter[date_added]` is one added day. `start_date` and `end_date` are documented labels only. This connector does not claim they mean a created-date range.
- `GET /customers/search_by_phone` documents `phone` and `as_object` only. Phone is not combined with the search filters.
- `name` is a local filter. A truncated scan stays incomplete.
- `branch` and any other undocumented filter is rejected.
- Detail projection keeps present billing, balance, terms, tags, contacts, and locations. Card and `stripe_pk` fields are dropped.

## Service locations

- `GET /customers/{customer_id}/service_locations` is the documented list. Customer id is required. The spec note mentioning `/service_locations` is not a separate verified global path, so no global call is made.
- Documented list filters: `page`, `per_page`, `filter[phone]`, `filter[updated_after]`.
- `query`, `active`, and `branch` are rejected.
- Rows whose `customer_id` belongs to someone else are omitted. A full page sets `truncated` and `next_page`.

## Work orders and schedule

- `GET /work_orders` documents dates, page, per_page, current_technician, sort_direction, work_pool, `filter[status]`, and `filter[service_routes_ids][]`.
- Customer and service-location filters are local. The index spec does not document those query parameters.
- Route filtering is still treated as ignored upstream and rechecked locally. `server_side_filtering` stays false.
- Responses include scanned count, pages read, completeness, and `next_page`. A repeated page or a later-page error sets `complete` false and does not claim a finished scan. Rows missing a requested filter field are counted and excluded. Occurrence id and service-appointment id stay distinct.

## Users and routes

- `GET /users` is documented with no query parameters. The projection is id, name, email, phone, technician flag, admin flag, job title, route id, route name, and branch id, name, company name, address, and time zone.
- `stripe_pk`, account, and feature payloads are not returned. Staff with `is_technician` false stay in the directory when they have a route. Route id `-1` is unassigned.
- Several staff on one route are listed together. `assignee` is null.
- `GET /service_routes` may be an empty array. Route relationships then come from the live user directory. A configured snapshot is used only when that user read is unavailable, and the response names that reason and source.

## Arrival windows

Fieldwork documents fixed, relative, and manual windows: https://intercom.help/fieldwork/en/articles/3472212-settings-arrival-time-windows. Fixed windows are chosen from the start time and do not depend on duration. Manual windows do not move when the start changes.

Verified B&T settings at `/settings/account/time_windows` use Auto-select from Fixed Time Windows. The catalog is hourly 08:00–09:00 through 16:00–17:00 America/New_York, ids 590–598. No relative windows are listed. Tim occurrence 8210560’s schedule form selects fixed (`time_window_kind` option 1). Typed GET, `/show_plain`, and profile do not return that field, so it is not added to API snapshots.

Prediction runs only when that company catalog and a matching occurrence record are inside their freshness window and bound to the work order, appointment, customer, and location. Anything else, including a window that merely equals start plus duration, returns `schedule_coupling_unverified` with the reason. The stored Tim result still reconciles by this rule: a 13:00 start selects window 595 (13:00–14:00). Reconciliation does not PATCH and does not edit the approved payload.

## Work Pool scheduling

Verified from one user-performed scheduler drag of occurrence 50268730, service appointment 8961994, customer 3675473, location 4491834, on 2026-09-29. The occurrence was Extra Service / Follow-up, one-time, price and production 0. Before the drag it was nominal 12:00–13:00 Eastern, route 2557, status Work Pool, specific false, confirmed false, instructions "test account", private notes empty.

The browser request was `POST https://app.fieldworkhq.com/work_orders/scheduler_action?editing=true`. The scheduling fields were `id=50268730`, `start_date=2026-09-29 20:00`, `end_date=2026-09-29 21:00`, `duration=60`, `service_route_ids=2557`, `specific=true`, `status=Scheduled`, `confirmed=false`, `repeating=false`, `frequency=none`, and `!nativeeditor_status=inserted`. The scheduler serializes those clock times as UTC. `2026-09-29 20:00` UTC is `2026-09-29T16:00:00-04:00`. The request did not send `time_window_kind`, `use_time_window`, or an arrival-window field. `service_appointment_id` was not its own field. `seriesUrl` referenced `/work_orders/services/8961994/edit`. HTTP 200 was `<data><action type="inserted" sid="50268730" tid="50268730" /></data>`. `inserted` is the calendar protocol action. The occurrence id did not change.

The connector GET afterward kept those same occurrence, appointment, customer, and location ids. `starts_at` was `2026-09-29T16:00:00-04:00`, `finished_at` was `2026-09-29T17:00:00-04:00`, the arrival window was 16:00–17:00 Eastern, duration was 60, the route was `[2557]`, status was Scheduled, specific was true, confirmed was false, instructions stayed "test account", private notes stayed empty, and production value stayed 0.0. That public GET still does not verify `repeat_type`.

Copied display and tooltip text, and stale camelCase `startDate` / `endDate` values in the browser request, are not the schedule.

These facts are not public-API equivalence. The saved work-order spec documents nested occurrence `specific` as a boolean Work Pool setting. It also documents `unspecified` and `use_time_window`. Their presence does not prove what a public PATCH does, and this connector does not send them. `PATCH /v3.1/work_orders/{service_appointment_id}` with nested `specific=true` plus `starts_at`, `duration`, and `service_route_ids` has not been executed. Whether that PATCH changes status to Scheduled, recomputes an arrival window, or leaves both unchanged is unknown. The connector does not call `scheduler_action` and does not use a browser cookie.

`schedule_work_pool_occurrence` seals that public body for an occurrence that is still specific false, status Work Pool, and confirmed false. Ordinary `update_work_order_schedule` still requires fresh fixed-window evidence and still does not send `specific`. The prepared Work Pool transition does not execute until the public PATCH above is compared with a GET of the same occurrence. Matching arrival bounds are not `time_window_kind` and do not extend the fixed-window evidence dates.
