# Fix the SSH key columns (needed after a reboot)

The receiver is running and Docker is fixed. I can finish the live mail tests over the current `contactus` SSH session.

The Edit → SSH keys screenshot still has the persistent key in the wrong columns. After a VM restart that session will die unless this is fixed.

**Delete** the row whose Username is `bt-intake-cloud-e9a8`.

**Add** this instead (two separate fields):

- **Username:** `btadmin`
- **Key:** `ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIC/DKOmrbwVG08WuDE4IREYQoVVmgXy5coIYC3pxPbzu bt-intake-cloud-e9a8`

Do not put `btadmin:` in the Key box. Save.

You can shut the Mac. I am sending the cloud test mail from Gmail, not from your laptop.
