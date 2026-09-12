# Phase B — create page: use the LEFT menu

The new Create instance screen only shows name/region/machine at first. Boot disk, network, and service account are **left-side tabs**, not on the first page.

Stay in project **bt-intake-proof**. Delete the old VM first if it is still there.

Open:

https://console.cloud.google.com/compute/instancesAdd?project=bt-intake-proof

## A. First screen (Machine configuration)

This is the page you already see.

- **Name:** `bt-intake-cloud`
- **Region:** `us-east1 (South Carolina)`
- **Zone:** `us-east1-c`
- **Series:** E2
- **Machine type:** **e2-small**

Do not click Create yet.

## B. Boot disk — left menu **OS and storage**

On the **left** of the form, click **OS and storage**.

1. Click **Change** (or **Configure** / **Show extra features**) on the boot disk.
2. Operating system: **Debian**
3. Version: **Debian GNU/Linux 12 (bookworm)**
4. Size: **20**
5. Disk type: **Balanced persistent disk**
6. **Select** / **Confirm**

## C. No website ports — left menu **Networking**

Click **Networking** on the left.

- **Allow HTTP traffic:** unchecked
- **Allow HTTPS traffic:** unchecked
- Network interface → **External IPv4 address:** **Ephemeral** (not None)

## D. Receiver account — left menu **Security**

Click **Security** on the left.

1. **Service account:** `bt-intake-proof-receiver@bt-intake-proof.iam.gserviceaccount.com`  
   If it is not in the list, leave this tab, grant yourself **Service Account User** here, then come back and refresh:  
   https://console.cloud.google.com/iam-admin/serviceaccounts/details/bt-intake-proof-receiver@bt-intake-proof.iam.gserviceaccount.com/permissions?project=bt-intake-proof
2. **Access scopes:** if you see **Set access for each API**, turn on **Cloud Pub/Sub** only.  
   If you only see Default / Full access, choose **Allow full access to all Cloud APIs**. That is OK **only** with the receiver SA (it can still only subscribe to our one topic).
3. **SSH keys** / **Manage access:** the Edit page has two columns. Do **not** paste `btadmin:` into the Key box.

- **Username:** `btadmin`
- **Key:** `ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIC/DKOmrbwVG08WuDE4IREYQoVVmgXy5coIYC3pxPbzu bt-intake-cloud-e9a8`

If you already added a row whose Username is `bt-intake-cloud-e9a8` and whose Key starts with `btadmin:`, delete that row and add the two fields above, then Save.

## E. Create

Click **Create**. Wait until Running.

Reply **vm up** and the **External IP** (details page → **Network interfaces**, or `Cmd+F` for `External IP`).
