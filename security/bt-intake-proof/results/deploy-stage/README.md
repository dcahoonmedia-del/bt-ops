Guarded desk-roundtrip stage. Do not run install_cloud_host.sh for this cutover.

On the VM, as root, after verifying the immutable tarball SHA256:

  sudo bash scripts/guarded_desk_roundtrip_deploy.sh

That preflights, quiesces the worker, writes a unique code/env/unit backup,
then copies. On failure it restores code/env/unit automatically and does not
touch SQLite. Manual rollback uses that unique backup, not an assumed SHA:

  sudo bash scripts/rollback_to_predeploy.sh

Then prepare the unused case and optionally deliver the CASE packet only.
Do not send BT-DESK-ROUNDTRIP-SEND-E9A8.
