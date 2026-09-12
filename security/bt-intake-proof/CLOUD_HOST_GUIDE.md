# Phase B — delete the messed-up VM and create one e2-small

Do this in project **bt-intake-proof**. Do not download a JSON key. Do not enable HTTP.

## 1. Delete the current VM and its disk

https://console.cloud.google.com/compute/instances?project=bt-intake-proof

1. Check the box next to `instance-20260912-024540`.
2. Click **Delete**.
3. Confirm it will delete the **boot disk** too. If there is a checkbox **Delete boot disk**, leave it **checked**.
4. Delete. Wait until the VM disappears from the list.

If a disk is left behind: **Compute Engine → Disks** → delete the disk named like `instance-20260912-024540`.

## 2. If the receiver SA is missing later, do this first

https://console.cloud.google.com/iam-admin/serviceaccounts/details/bt-intake-proof-receiver@bt-intake-proof.iam.gserviceaccount.com/permissions?project=bt-intake-proof

**Grant Access** → principal: the Google account you are using now → role: **Service Account User** → Save.

## 3. Create the replacement VM

https://console.cloud.google.com/compute/instancesAdd?project=bt-intake-proof

Set these **before** you click Create:

- **Name:** `bt-intake-cloud`
- **Region:** `us-east1 (South Carolina)`
- **Zone:** `us-east1-c` (or `us-east1-b` if `-c` is greyed out)
- **Series:** E2
- **Machine type:** **e2-small** (2 vCPU, 2 GB). Not e2-medium.
- **Boot disk → Change:** Debian 12, size **20**, type Balanced. Confirm.
- **Firewall:** **Allow HTTP** and **Allow HTTPS** both **unchecked**
- **Management / Security / Disks / Networking / Sole tenancy** (or **Advanced**):
  - **Identity and API access**
    - Service account: `bt-intake-proof-receiver@bt-intake-proof.iam.gserviceaccount.com`
    - Access scopes: **Set access for each API** → **Cloud Pub/Sub = Enabled**. Everything else Disabled.
  - **Networking** → Network interface → External IPv4: **Ephemeral** (not None)
  - **Security** → **Manage access** / SSH keys → add this **one** line:

```
btadmin:ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIC/DKOmrbwVG08WuDE4IREYQoVVmgXy5coIYC3pxPbzu bt-intake-cloud-e9a8
```

Click **Create**. Wait until Status is **Running**.

## 4. Send me these three values from the new VM details page

- Name (should be `bt-intake-cloud`)
- Machine type (should be `e2-small`)
- External IP (search the page for `Network interfaces`)

Reply **vm up** and the External IP. I will SSH as `btadmin` and install. No JSON key.
