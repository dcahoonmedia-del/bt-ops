# Create contract

Offline only. Nothing in this pass was deployed. Tests use `FakeTransport`. No live Fieldwork, GCP, or Auth0 call is made.

Swagger create responses are null. A successful readback is a test double that echoed the documented request and included an integer `id`. It is not a verified live schema. Execute sends one POST and does not PATCH.

## Customer `POST /v3.1/customers`

Accepted:

- `customer_type`: `Residential` or `Commercial` (case-sensitive)
- Commercial requires `name`. Residential requires `last_name`. `first_name` is optional once `last_name` is filled.
- `service_locations`: one or more entries, each with only `name` and `same_as_billing_address`
- `status` when present: `active`, `inactive`, `financial_hold`, `sent_to_collections`. Omitted status is sent as `active`.
- Optional billing fields from the create spec: `billing_name`, `billing_attention`, `billing_street`, `billing_street2`, `billing_city`, `billing_state`, `billing_zip`, `billing_county`, `billing_term_id`, `billing_phone`, `billing_phone_ext`, `billing_phone_note`, `billing_phone_kind` (`Home`, `Office`, `Mobile`, `Fax`, `Other`), and the billing phone arrays
- `note`

## Work order `POST /v3.1/work_orders`

Accepted:

- `customer_id`, `service_location_id` (existing active customer and location)
- `repeat_type`: `none` only
- `repeat_period`: required integer, sent as given, including `0`
- one occurrence with `service_route_ids` and `starts_at` as `YYYY-MM-DD`
- optional occurrence `duration` integer
- line items: `name`, `type` (`service`, `material`, `other`, `fee`), `quantity`, `price`
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
