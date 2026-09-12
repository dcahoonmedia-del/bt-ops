# Create the receiver service account in the console

The Cloud login cannot call `iam.serviceAccounts.create`. Create **only** this account and two grants. Do not download a key. If Google asks for billing, stop and tell me.

## 1. Create the service account

https://console.cloud.google.com/iam-admin/serviceaccounts/create?project=bt-intake-proof

- Service account ID: `bt-intake-proof-receiver`
- Name: `B&T intake proof receiver`
- Skip any optional role on the **project**
- **Done / Create**
- If Google offers **Create key** / **Add key**, click **Done** or **Skip**. Do not download JSON.

Confirm it appears:
https://console.cloud.google.com/iam-admin/serviceaccounts?project=bt-intake-proof

The email should be:
`bt-intake-proof-receiver@bt-intake-proof.iam.gserviceaccount.com`

## 2. Subscriber on the one subscription only

https://console.cloud.google.com/cloudpubsub/subscription/detail/bt-intake-proof-contactus-sub?project=bt-intake-proof

1. **Permissions**
2. **Add principal**
3. Principal: `bt-intake-proof-receiver@bt-intake-proof.iam.gserviceaccount.com`
4. Role: **Pub/Sub Subscriber**
5. Save

Do not grant Editor, Owner, Pub/Sub Admin, or Publisher.

## 3. Allow impersonation (no key)

https://console.cloud.google.com/iam-admin/serviceaccounts/details/bt-intake-proof-receiver@bt-intake-proof.iam.gserviceaccount.com?project=bt-intake-proof

1. **Permissions**
2. **Grant access**
3. Principal: `daniel@btpestcontrol.com`
4. Role: **Service Account Token Creator**
5. Save

Then reply **done**. I will impersonate that account and pull. Do not send `BT-INTAKE-PROOF-*` emails yet.
