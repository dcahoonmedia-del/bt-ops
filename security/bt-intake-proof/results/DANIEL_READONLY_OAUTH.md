# Daniel readonly OAuth bootstrap (staged, not run)

Standalone helper: `scripts/daniel_readonly_oauth.py`  
Does not deploy the new worker. Does not change `oauth_consent.py` or contactus tokens.  
Consent was not started. No token was written.

Complete uses **getpass on a TTY** and fails closed if echo cannot be disabled. Do not `cat` the redirect URL.

## Artifact integrity

`daniel_readonly_oauth.py` SHA-256:

`e65713f2e678f3386b78ae504f83f91455dfa50ba6099e68b60ed17b0143cd86`

Browser-SSH transfer card: `results/daniel-readonly-oauth-stage/TRANSFER`  
Also `results/daniel-readonly-oauth-stage/SHA256SUMS`.

## Codex transfer and run (host `bt-intake-cloud`)

Existing secrets stay: `gmail_oauth_client.json`, `contactus_gmail_readonly_token.json`, `contactus_gmail_send_token.json`.

1. Transfer **only** `daniel_readonly_oauth.py` (see `TRANSFER`). Verify SHA-256 before running.
2. As root, install the helper beside the current tree (do not rsync the new worker):

```
install -m 755 daniel_readonly_oauth.py /opt/bt-intake-proof/scripts/daniel_readonly_oauth.py
```

3. Start (prints paths only; does not print the authorization URL or secrets):

```
sudo -u btintake -H python3 /opt/bt-intake-proof/scripts/daniel_readonly_oauth.py start
```

4. Codex reads `/var/lib/bt-intake-proof/daniel-readonly-auth-url.txt` (mode 0600) and opens that Google screen for Daniel. Daniel signs in as `daniel@btpestcontrol.com` and Allows **Gmail read-only** only. Decline send/modify/delete. The Mac browser then fails on the saved loopback origin. That is expected: **no listener**.
5. Codex (not Daniel) completes on a real TTY. Input is hidden. If echo cannot be turned off, the helper exits without exchanging:

```
sudo -u btintake -H python3 /opt/bt-intake-proof/scripts/daniel_readonly_oauth.py complete
```

Paste the full loopback URL at the hidden prompt (not argv, not chat, not `cat`).

6. Success writes `/opt/bt-intake-proof/secrets/daniel_gmail_readonly_token.json` mode `0600`, owner `btintake` if the helper can chown. Setup files are wiped. If owner is not `btintake`:

```
sudo chown btintake:btintake /opt/bt-intake-proof/secrets/daniel_gmail_readonly_token.json
sudo chmod 600 /opt/bt-intake-proof/secrets/daniel_gmail_readonly_token.json
```

7. Confirm contactus files are unchanged. Do not restart `bt-intake-receiver`. Do not deploy PR #15. Abort leftover setup with `python3 ... abort`.

Daniel's only action: complete the Google consent screen as daniel@. Do not ask him for codes, client JSON, or token evidence.
