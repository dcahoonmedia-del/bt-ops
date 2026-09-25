# Create contract

Offline only. Nothing in this pass was deployed. Tests use `FakeTransport`. No live Fieldwork, GCP, or Auth0 call is made.

Swagger create responses are null. A successful readback is a test double that echoed the documented request and included an integer `id`. It is not a verified live schema. The live customer POST that created the known account did not retain its HTTP status or body, so that response stays unknown. Diagnostics recorded after this change are status, content type, top-level key names, and parser stage only. A top-level positive integer `id` on HTTP 200 or 201 is the only create id taken from the response. Any other body, including an unverified wrapper, is not an id. The customer POST is not repeated. One new account is bound only when search and GET prove it was absent from the approved duplicate preflight and matches the approved type, active status, billing address, and primary location.

## Customer `POST /v3.1/customers`

Accepted:

- `customer_type`: `Residential` or `Commercial` (case-sensitive)
- Commercial requires `name`. Residential requires `last_name`. `first_name` is optional once `last_name` is filled.
- `service_locations`: one object, or a list of exactly one object, with only `name` and `same_as_billing_address`. The customer POST sends that as `service_locations_attributes`, not as `service_locations`. Omitting the location is `nested_location_required`.
- `status` when present: `active`, `inactive`, `financial_hold`, `sent_to_collections`. Omitted status is sent as `active`.
- Optional billing fields from the create spec: `billing_name`, `billing_attention`, `billing_street`, `billing_street2`, `billing_city`, `billing_state`, `billing_zip`, `billing_county`, `billing_term_id`, `billing_phone`, `billing_phone_ext`, `billing_phone_note`, `billing_phone_kind` (`Home`, `Office`, `Mobile`, `Fax`, `Other`), and the billing phone arrays
- `note`
- `primary_email` is accepted as caller intent and is not posted. The customer write spec has no `invoice_email`. A caller key named `invoice_email` is `unknown_field`.
- `location_email` and `location_type_id` are location PATCH fields, together with `reminders_type` `0`. `send_report_email` is not sent. Inherited true may still send a completion report after a location email is added. Inactive reminders do not disable every notice.
- Name and phone are the only documented duplicate queries. A supplied email or street stays incomplete until `acknowledge_duplicate_coverage` lists that exact gap. The acknowledgment is bound to the proposal and is not a no-duplicate result.

## Work order `POST /v3.1/work_orders`

Accepted:

- `customer_id`, `service_location_id` (existing active customer and location)
- `repeat_type`: `none` only
- `repeat_period`: required integer, sent as given, including `0`
- one occurrence. `starts_at` and `service_route_ids` may be top-level or inside one `occurrences` item. Omitting them is `missing_field`, not `unknown_field` on `occurrences`. Optional `duration` and `instructions` use the same place.
- `starts_at` as `YYYY-MM-DD` is the POST value. An offset timestamp is kept on the proposal. The POST body uses that calendar date because the saved create spec types `starts_at` as `date`. One later PATCH sets the approved offset, duration, and routes after distinct occurrence and appointment ids are known. A fresh public create-page fetch returned HTTP 404, so the POST clock itself is not verified.
- line items: `name`, `type` (`service`, `material`, `other`, `fee`), `quantity`, `price`
- The catalog line price is the standard initial price when the caller omits `line_items`. A caller line for that same service, quantity, and payable may set a different `price`. That price is the approved line price. The line total is quantity times price. When that price differs from the catalog price and the caller omits `production_value`, production value is that line total. The template price is not written over a specified price.
- `payable_id` and `payable_type` (`Service`, `Material`, `Fee`) when `type` is `service` or `material`

`starts_at` is swagger type `date` with no format example. Offset-ISO and Zulu are not treated as the documented create format. That datetime gap stays unverified.

## Rejected gaps

| Gap | Gate |
| --- | --- |
| `repeat_type` `never` or any value outside the documented enum | `unknown_field` on `repeat_type` (not mapped to `none`) |
| Any other documented `repeat_type` (`daily`, `weekly`, `monthly`, `bimonthly`, `quarterly`, `tri_annually`, `semi_annually`, `seasonal`, `yearly`) | `recurring_series_rejected` |
| More than one occurrence | `recurring_series_rejected` |
| `use_time_window` included | `arrival_window_unverified` (the field is not sent) |
| Zulu or other datetime `starts_at` | `starts_at_datetime_unverified` |
| `tax_rate_id`, `tax_amount`, `discount`, billing frequency, PDF forms, units, worker lat/lng, `production_value` | `unknown_field` |
| Line item `taxable: true` | `taxable_requires_tax_rate` |
| Customer `status` lead | `never_lead_status_accounts` |
| Nested location `tax_rate_id` or `address_attributes` on customer create | `unknown_field` |
| Invoicing, autopay, credit card, stripe, tags, contacts | `unknown_field` |
| Standalone `POST /customers/{id}/service_locations` | `unknown_operation` |
| Create response with no integer `id` | `create_response_unverified`, `retry: false`, no second POST |
| Echo of sent fields does not match | `readback_failed`, no retry |

Approval, digest, identity, and the ambiguous no-retry guard still apply.
