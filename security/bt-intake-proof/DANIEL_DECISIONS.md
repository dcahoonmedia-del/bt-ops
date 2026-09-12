# Fix the SSH key columns before the reboot test

CLOUD-NEW passed on the VM. The Mac can stay off. I am sending the remaining marked test mail from Gmail.

The Edit → SSH keys screenshot still has the persistent key in the wrong columns. After a VM restart I will lose SSH unless this is fixed.

**Delete** the row whose Username is `bt-intake-cloud-e9a8`.

**Add** this instead (two separate fields):

- **Username:** `btadmin`
- **Key:** `ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIC/DKOmrbwVG08WuDE4IREYQoVVmgXy5coIYC3pxPbzu bt-intake-cloud-e9a8`

Do not put `btadmin:` in the Key box. Save. Reply **key saved**.
