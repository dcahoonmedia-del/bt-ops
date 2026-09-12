# Phase B — create the one e2-small VM

Compute Engine API is on. This Cloud login still cannot create VMs (`compute.instances.list` denied). I did **not** grant extra project roles and did **not** create a JSON key.

Create **one** VM in the console. Stay in project **bt-intake-proof**.

Open:

https://console.cloud.google.com/compute/instancesAdd?project=bt-intake-proof

If Google says billing is not linked, stop here and open:

https://console.cloud.google.com/billing/linkedaccount?project=bt-intake-proof

Link **the billing account you just created**. Do not create another. Then return to the create-VM page.

## VM settings

- **Name:** `bt-intake-cloud`
- **Region:** `us-east1 (South Carolina)`
- **Zone:** `us-east1-b` (any `us-east1-*` zone is fine if `-b` is greyed out)
- **Machine family:** General-purpose, **e2**
- **Machine type:** **e2-small** (2 vCPU, 2 GB). Do not pick e2-medium or larger.
- **Boot disk:** Debian 12, **20 GB**, Balanced persistent disk. Do not add extra disks.
- **Firewall:** leave **Allow HTTP** and **Allow HTTPS** unchecked.
- **Service account:** `bt-intake-proof-receiver@bt-intake-proof.iam.gserviceaccount.com`  
  If it is missing from the list, open the [receiver SA Permissions page](https://console.cloud.google.com/iam-admin/serviceaccounts/details/bt-intake-proof-receiver@bt-intake-proof.iam.gserviceaccount.com/permissions?project=bt-intake-proof), **Grant Access** to yourself (`daniel@btpestcontrol.com` or the owner account), role **Service Account User** only, save, then refresh the VM form.
- **Access scopes:** Set access for each API → enable **Cloud Pub/Sub** only. Leave others disabled.
- **Advanced → Security / Manage access → SSH keys** (or the SSH keys section): add exactly this line:

```
btadmin:ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIC/DKOmrbwVG08WuDE4IREYQoVVmgXy5coIYC3pxPbzu bt-intake-cloud-e9a8
```

Create the VM. Do not add HTTP load balancing, Cloud Run, extra firewall rules, or a second machine.

## After it is running

On the VM details page, copy **External IP**. Reply:

`vm up`  
`EXTERNAL_IP=x.x.x.x`

I will SSH in, install the proven receiver, and will not open an application port.
