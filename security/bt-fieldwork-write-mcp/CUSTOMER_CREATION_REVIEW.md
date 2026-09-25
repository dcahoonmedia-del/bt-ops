# Customer creation review

Schema-ready. Not live-tested. Nothing in this pass was deployed, and no live Fieldwork call was made.

## Contract evidence

Public `POST /v3.1/customers` still sends only `customer_type`, name rules, documented billing fields, `note`, `status` (default `active`, never `lead`), and one nested location with `name` and `same_as_billing_address`.

Distinct service addresses are not nested on that POST. After the returned location is read, a documented `PATCH` sends `name`, caller-supplied `tax_rate_id`, and `address_attributes` including the address id from that read. A second location is created only when `additional_location` supplies `name` and `tax_rate_id`.

`POST /customers/{id}/contacts` runs only when the caller supplies `first_name`, `last_name`, and `email`. The proposal stores that contact. Portal, reminder, and autopay fields are not sent.

Duplicate search runs before propose and again before the customer POST. Documented queries are normalized name (`GET /customers/search`) and phone (`GET /customers/search_by_phone`). There is no documented email or street query, and none was added. Returned customer, contact, and location rows are inspected for `email`, `invoice_email`, contact email, location email, and street. A supplied `primary_email`, `location_email`, contact email, billing street, service street, or additional-location street is a coverage gap (`email_or_address_coverage_gap`). That result is not a complete no-duplicate search. `confirmed_new` does not bypass the gap. Incomplete, failed, or repeated pages use `duplicate_search_incomplete`. Name or phone matches still require `confirmed_new` or `existing_customer_id` (`duplicate_unresolved`). A match that appears after approval is `new_match_requires_approval`.

## Email, phone, and location mapping

Verified write fields: `billing_phone_kind` is `Home`, `Office`, `Mobile`, `Fax`, or `Other` and is sent only when supplied. A missing kind is omitted. Location PATCH may send `email`, `location_type_id`, and `reminders_type` `0`. `send_report_email` exists on the location write spec and is not sent.

Unverified: customer `invoice_email` is not in the customer write spec. `primary_email` is stored as a candidate body only. Execute fails closed with `invoice_email_write_unverified` and does not create a contact for that email. GET location omits `reminders_type`, so readback stays `unverified` with a manual office check. A present value other than `0` is a mismatch. Customer-creation notice behavior is unknown. UI form names are not API routes.

`FW_RESIDENTIAL_LOCATION_TYPE_ID` is the configured residential property type. The observed id is `8736`, and GET `/location_types` must list that id with name `Residential`. An empty setting is `location_type_unconfigured`. Commercial without an explicit `location_type_id` is `location_type_required`.

Notification effects on the proposal: appointment reminders are set inactive, and that setting does not disable every notice. Inherited `send_report_email=true` may send a completion report once a location email is added.

## Journal

Each POST/PATCH is an intended journal row before the call and a succeeded row with customer, contact, and location ids as soon as they are known. A crash sweeps intended rows to ambiguous. An ambiguous or partial result does not replay the POST and does not delete the account. Recovery is a new approved proposal, usually with `existing_customer_id`.

Success reads the customer (`active`), the contact list when a contact was requested (zero contacts is valid), the location, and a complete search that finds the customer.

## Tests

`tests/test_creation_workflow.py` and the updated create cases in `tests/test_write_mcp.py`. Fake transport only.

## First live test (not run)

1. Writer key, writes flag, and ChatGPT approval mode on a non-production branch only after a separate go-ahead.
2. Search a unique test name and confirm the page scan is complete.
3. Propose a residential customer with `confirmed_new`, one nested location, and no contact. Inspect the POST body before approval.
4. Execute once. Require active GET, location GET, and search hit. Stop on any partial journal.
5. Do not treat a supplied email or street as searched. Those creates stay closed until a documented query exists. Location email, property type, and `reminders_type` 0 belong on the location PATCH. `primary_email` stays unsent. Reminders readback stays unverified when GET omits the field. Do not target Jim Doe `3675473` / `4491834`, and do not create a work order in that test.
