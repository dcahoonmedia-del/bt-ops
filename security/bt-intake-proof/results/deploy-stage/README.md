Guarded desk-roundtrip stage. Do not run install_cloud_host.sh for this cutover.

On the VM, as root, after verifying the immutable tarball SHA256:

  sudo bash scripts/guarded_desk_roundtrip_deploy.sh

That records the actual live tree first, excludes secrets, merges env, and
health-checks. Rollback uses the recorded pre-deploy revision, not an assumed SHA:

  sudo bash scripts/rollback_to_predeploy.sh

Then prepare the unused case and optionally deliver the CASE packet only.
Do not send BT-DESK-ROUNDTRIP-SEND-E9A8.
