# Customer creation review

Schema-ready. Not live-tested. Nothing in this pass was deployed, and no live Fieldwork call was made.

## Contract evidence

Public `POST /v3.1/customers` still sends only `customer_type`, name rules, documented billing fields, `note`, `status` (default `active`, never `lead`), and one nested location with `name` and `same_as_billing_address`.

Distinct service addresses are not nested on that POST. After the returned location is read, a documented `PATCH` sends `name`, caller-supplied `tax_rate_id`, and `address_attributes` including the address id from that read. A second location is created only when `additional_location` supplies `name` and `tax_rate_id`.

`POST /customers/{id}/contacts` runs only when the caller supplies `first_name`, `last_name`, and `email`. The proposal stores that contact. Portal, reminder, and autopay fields are not sent.

Duplicate search runs before propose and again before the customer POST. Name and phone are normalized. Candidates include email, billing address, and locations. Incomplete, failed, or repeated pages use `duplicate_search_incomplete`. Matches require `confirmed_new` or `existing_customer_id` (`duplicate_unresolved`).

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
5. Only then repeat with a distinct service address and an explicit contact email the operator typed.
