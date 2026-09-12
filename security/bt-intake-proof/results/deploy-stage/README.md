Staged only. Origin Sent corroboration is incomplete without the daniel@
readonly token. Do not deploy until that gate is live.

On the VM, as root, before install:
  sudo bash scripts/record_predeploy_revision.sh
  sudo bash scripts/install_cloud_host.sh

Rollback uses the recorded pre-deploy revision, not an assumed SHA:
  sudo bash scripts/rollback_to_predeploy.sh
