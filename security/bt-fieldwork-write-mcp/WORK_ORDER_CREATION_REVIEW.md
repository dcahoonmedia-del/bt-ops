# Work order creation review

Schema-ready. Not live-tested. Nothing in this pass was deployed. Occurrence `50089280` and appointment `8930085` were not read or changed. Branch, route, tax, term, and location-type ids from that occurrence are not hardcoded.

## Contract evidence

Each proposal lists `GET /work_order_templates` and `GET /services`, then `GET /work_order_templates/{id}`. The show body must use root `service_appointment_template`. The fake catalog evidence is template `8835901` PestGuard - Initial 2026, `repeat_type` none, `repeat_period` 1, `billing_frequency` 0, `discount` 0, `tax_amount` 0, line payable `38814` / `Service` / type `service` / name PestGuard - Set-up / quantity 1 / price 150 / taxable false, defaults duration 60, production_value 150, and instructions, specific, and callback present. Service rows are matched on `description`, not `name`. A price or label disagreement is `catalog_disagreement`. Those ids are whatever the read returned. They are not copied onto the new occurrence or appointment.

`POST /work_orders` sends root `service_appointment` with customer, location, `repeat_type` none, integer `repeat_period`, one occurrence, and one initial line. The catalog price is the standard price. A caller line for the same service and quantity keeps the caller's price, and the proposal digest binds that price, the quantity-times-price total, and the production value. A date-only `starts_at` is one POST. An offset timestamp posts the calendar date and then one PATCH sets the approved offset, because the saved create spec types `starts_at` as `date` and a fresh public create-page fetch returned HTTP 404. GET evidence is not POST support. Posting a clock time is not live-tested. `started_at_time`, `finished_at_time`, `private_notes`, `status`, and `use_time_window` are `unknown_field`. Promised-window enforcement is false. There is no agreement, recurrence, monthly price, or future visit. `billing_frequency` 0 is disclosed as normal invoice generation even when `auto_generates_invoice` is absent. Template defaults are read from `work_order`. The schedule snapshot is compared again immediately before POST; a difference is `stale_state`.

The proposal shows the customer/location pair, route staff with `assignee` null, the complete schedule for that date, America/New_York, duration, price, and instructions. References, template, and schedule are read again immediately before the single POST. Readback requires distinct occurrence and appointment ids and the occurrence on a complete `list_schedule`. An ambiguous POST reconciles from that list and does not POST again. `auto_generates_invoice` is disclosed when the fetched template says it is on. It is not turned on by this client.

## Tests

Fake catalog, route staff, stale template, price mismatch, id collision, approval, digest, and cross-user cases are in `tests/test_creation_workflow.py`. `report_gates` sets `creation_schema_ready` true and `creation_live_tested` false.

## First live test (not run)

1. Do not target occurrence 50089280 or appointment 8930085.
2. On a non-production writer key, list templates and services and stop if the PestGuard line and the service `description`/price disagree.
3. Propose one work order for an already active test customer and location, with a route the live user directory actually returned.
4. Show the operator the association, staff list, schedule conflicts, date, duration, price, and instructions. Do not describe an arrival window as promised.
5. After one approved POST, GET the occurrence, confirm the appointment id is different, and require that occurrence id on a complete schedule list. If the POST is ambiguous, reconcile that list and do not create another work order.
6. For a timed visit, approve the disclosed date POST plus one schedule PATCH of the exact offset. Re-read the Sep 25 2PM opening before any later live test. Do not reserve it in this checkout. A quoted initial price must be the approved line price, total, and production value on readback. Missing proof: the public create page returned HTTP 404, so this test is the first proof of whether Fieldwork accepts the date POST and the follow-up offset PATCH.
