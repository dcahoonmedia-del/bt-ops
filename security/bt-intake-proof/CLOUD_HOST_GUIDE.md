# Phase B — cloud host (stopped for billing)

The Mac/agent intake path is **PASS**. I did **not** create a VM.

Compute Engine API is **disabled** on `bt-intake-proof`. Cloud Billing API is also disabled, so I cannot see whether billing is already linked. A GCE VM always requires billing. That is a material billing choice.

## What I need from you

Reply **billing ok** only if you want me to use a small always-on VM in `bt-intake-proof` for this proof.

Recommended VM (smallest that can run Docker + isolated Codex):

- Machine: **e2-small** (2 GB). e2-micro is too small for the proven 2 GB Codex container.
- Disk: 20 GB persistent boot disk
- Zone: `us-central1-a` unless you prefer another
- Service account: existing `bt-intake-proof-receiver` (Pub/Sub Subscriber already granted)
- No public application port
- No JSON key

Approximate cost is a small always-on e2-small plus disk. I will not pick a billing account or enable Compute Engine until you say **billing ok**.

If Google asks you to link a billing account, do that yourself and tell me. I will not link one.

## After billing ok, I will ask you to click only

1. Enable **Compute Engine API** in project `bt-intake-proof`  
   https://console.developers.google.com/apis/api/compute.googleapis.com/overview?project=bt-intake-proof
2. On the receiver SA Permissions page, grant `daniel@btpestcontrol.com` **Service Account User** (so the VM can attach that SA). Do not grant Owner/Editor.  
   https://console.cloud.google.com/iam-admin/serviceaccounts/details/bt-intake-proof-receiver@bt-intake-proof.iam.gserviceaccount.com/permissions?project=bt-intake-proof

Do not download a key. Do not send cloud test emails yet.
