# Grant Service Account Token Creator

Steps 1 and 2 are done. Do **not** download a key.

Open this Permissions page (not the Keys page):

https://console.cloud.google.com/iam-admin/serviceaccounts/details/bt-intake-proof-receiver@bt-intake-proof.iam.gserviceaccount.com/permissions?project=bt-intake-proof

1. Confirm the top says service account `bt-intake-proof-receiver`.
2. Click **Grant Access** or **Add Principal**.
3. In **New principals**, type: `daniel@btpestcontrol.com`
4. Click the **Select a role** box.
5. Type `Token Creator` in the filter. Do not pick Owner, Editor, or Viewer.
6. Choose **Service Account Token Creator**.
   The full name is `roles/iam.serviceAccountTokenCreator`.
7. **Save**.

After Save, the Permissions list should show `daniel@btpestcontrol.com` with **Service Account Token Creator**. That is not the same as **Service Account User**.

If you do not see a Permissions tab, start here and click the receiver email, then **Permissions**:

https://console.cloud.google.com/iam-admin/serviceaccounts?project=bt-intake-proof

Then reply **done**. I will impersonate and pull. Do not send `BT-INTAKE-PROOF-*` emails yet.
