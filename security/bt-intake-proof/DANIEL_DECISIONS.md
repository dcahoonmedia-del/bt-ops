# Stopped for Daniel — enable IAM API

Cloud login is stored. No JSON key was created. Service account `bt-intake-proof-receiver` was not created because the IAM API is disabled on `bt-intake-proof`.

Enable only these two APIs, then reply **done**:

1. IAM API  
   https://console.cloud.google.com/apis/library/iam.googleapis.com?project=bt-intake-proof
2. IAM Credentials API (needed to impersonate, not to download a key)  
   https://console.cloud.google.com/apis/library/iamcredentials.googleapis.com?project=bt-intake-proof

If Google asks to link billing, stop and tell me.

Do not send `BT-INTAKE-PROOF-*` emails yet.
