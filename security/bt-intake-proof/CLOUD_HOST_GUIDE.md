# Phase B — enable Compute Engine, then I will create the VM

Billing is authorized for one e2-small in `us-east1`. I did **not** create a VM or a JSON key.

This Cloud login cannot enable APIs (`serviceusage` permission denied). Enable these two APIs in project **bt-intake-proof**, signed in as the project owner if `daniel@` is denied.

## 1. Compute Engine API

https://console.developers.google.com/apis/api/compute.googleapis.com/overview?project=bt-intake-proof

Click **Enable**. Do not enable other APIs.

## 2. Cloud Billing API

Needed only so I can confirm the project is linked to the billing account you just created.

https://console.developers.google.com/apis/api/cloudbilling.googleapis.com/overview?project=bt-intake-proof

Click **Enable**.

## 3. Confirm billing is linked (do not pick a different account)

https://console.cloud.google.com/billing/linkedaccount?project=bt-intake-proof

- If it already shows the billing account you just created, leave it.
- If it says the project is not linked, click **Link a billing account** and choose **that same account**. Do not create another billing account.

## 4. Reply **apis on**

I will then create only:

- one `e2-small` VM in `us-east1`
- persistent boot disk
- attached service account `bt-intake-proof-receiver`
- no public application ports
- no JSON key
