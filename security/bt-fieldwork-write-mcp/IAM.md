# Least-privilege ONE-secret IAM (DRAFT ONLY — apply nothing)

Secret **name** (never the value): `BT-fieldworks-key`  
Exact future resource: `projects/bt-intake-proof/secrets/BT-fieldworks-key/versions/latest`  
Project: `bt-intake-proof`

Receiver SA (do **not** grant this):  
`bt-intake-proof-receiver@bt-intake-proof.iam.gserviceaccount.com`

## Proposed isolated identity (do not create yet)

```
bt-fieldwork-write-mcp@bt-intake-proof.iam.gserviceaccount.com
```

Bind that SA to the write-MCP VM/service only. Do not reuse the receiver SA. Do not add other secrets, buckets, or Gmail scopes.

## Single binding to apply later (not now)

```
gcloud secrets add-iam-policy-binding BT-fieldworks-key \
  --project=bt-intake-proof \
  --member=serviceAccount:bt-fieldwork-write-mcp@bt-intake-proof.iam.gserviceaccount.com \
  --role=roles/secretmanager.secretAccessor
```

That is the only intended secret IAM change. No project-wide Secret Manager admin. No change to the receiver SA. No IAM apply from this checkout.

Runtime must `gcloud secrets versions access latest --secret=BT-fieldworks-key` (or equivalent) onto tmpfs, read into process memory, and never write the value to disk logs or MCP responses.
