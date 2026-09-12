# One console fix left: SSH key columns, then RESET the VM

NEW, REPLY, recovery, watch renew, and isolated Codex all passed on the cloud VM. The Mac can stay off.

The Edit → SSH keys screenshot still has the persistent key in the wrong columns. After RESET I will lose SSH unless this is fixed.

**Delete** the row whose Username is `bt-intake-cloud-e9a8`.

**Add** this instead (two separate fields):

- **Username:** `btadmin`
- **Key:** `ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIC/DKOmrbwVG08WuDE4IREYQoVVmgXy5coIYC3pxPbzu bt-intake-cloud-e9a8`

Do not put `btadmin:` in the Key box. Save.

Then on the VM details page click **RESET** (or Stop + Start). Reply **vm reset**.
