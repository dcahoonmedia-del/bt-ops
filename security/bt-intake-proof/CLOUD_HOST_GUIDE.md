# Phase B — fix the existing VM, then I install

SSH to `35.243.167.73` works. I did **not** install the receiver. Current VM is off-spec:

| Setting | Found | Required |
| --- | --- | --- |
| Zone | `us-east1-c` | OK |
| Machine | **e2-medium** | **e2-small** |
| Service account | **default compute** `1028131400538-compute@` | `bt-intake-proof-receiver@...` |
| Scopes | logging/monitoring/storage, **no Pub/Sub** | **Cloud Pub/Sub only** |
| Boot disk | **10 GB** | **20 GB** |

I will not use the default compute service account (it is broader than the proof) or keep the larger e2-medium.

## Fix on this same VM

https://console.cloud.google.com/compute/instances?project=bt-intake-proof

1. Select `instance-20260912-024540` → **Stop** → wait until stopped.
2. **Edit**
3. Machine type → **e2-small**
4. **Service account** → `bt-intake-proof-receiver@bt-intake-proof.iam.gserviceaccount.com`  
   If missing: grant yourself **Service Account User** on that SA, refresh, try again.
5. Access scopes → **Set access for each API** → enable **Cloud Pub/Sub** only.
6. Boot disk → resize to **20 GB** (same disk, do not add a second disk).
7. HTTP/HTTPS stay **unchecked**.
8. **Save** → **Start**

Reply **vm fixed**. I will SSH again, confirm the receiver SA, then install. No JSON key.
