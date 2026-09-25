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
