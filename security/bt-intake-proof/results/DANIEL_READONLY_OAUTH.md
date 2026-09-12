# Daniel readonly OAuth bootstrap (staged, not run)

Standalone helper: `scripts/daniel_readonly_oauth.py`  
Does not deploy the new worker. Does not change `oauth_consent.py` or contactus tokens.  
Consent was not started. No token was written.

## Artifact integrity

`daniel_readonly_oauth.py` SHA-256:

`f5c805b46287923dc410859007478539ee7764d79f176b531809a7f656fd28c3`

Also see `results/daniel-readonly-oauth-stage/SHA256SUMS`.

## Codex transfer and run (host `bt-intake-cloud`)

Existing secrets stay: `gmail_oauth_client.json`, `contactus_gmail_readonly_token.json`, `contactus_gmail_send_token.json`.

1. Copy **only** `daniel_readonly_oauth.py` to the VM (SSH-in-browser). Verify SHA-256 matches `SHA256SUMS` before running.
2. As root, install the helper beside the current tree (do not rsync the new worker):

```
install -m 755 daniel_readonly_oauth.py /opt/bt-intake-proof/scripts/daniel_readonly_oauth.py
```

3. Start (prints paths only; does not print the authorization URL or secrets):

```
sudo -u btintake -H python3 /opt/bt-intake-proof/scripts/daniel_readonly_oauth.py start
```

4. Codex reads `/var/lib/bt-intake-proof/daniel-readonly-auth-url.txt` (mode 0600) and opens that Google screen for Daniel. Daniel signs in as `daniel@btpestcontrol.com` and Allows **Gmail read-only** only. Decline send/modify/delete. The Mac browser then fails on `http://127.0.0.1` / `http://localhost`. That is expected: **no listener**.
5. Codex (not Daniel) writes the full address-bar loopback URL into a 0600 file. Do not put the URL on the command line, in chat, or in shell history:

```
sudo -u btintake -H bash -c 'umask 077; cat > /var/lib/bt-intake-proof/daniel-oauth-redirect.url'
# paste one URL line, then Ctrl-D
sudo -u btintake -H python3 /opt/bt-intake-proof/scripts/daniel_readonly_oauth.py complete --redirect-file /var/lib/bt-intake-proof/daniel-oauth-redirect.url
```

6. Success writes `/opt/bt-intake-proof/secrets/daniel_gmail_readonly_token.json` mode `0600`, owner `btintake` if the helper can chown. Setup and redirect files are wiped. If owner is not `btintake`:

```
sudo chown btintake:btintake /opt/bt-intake-proof/secrets/daniel_gmail_readonly_token.json
sudo chmod 600 /opt/bt-intake-proof/secrets/daniel_gmail_readonly_token.json
```

7. Confirm contactus files are unchanged. Do not restart `bt-intake-receiver`. Do not deploy PR #15. Abort leftover setup with `python3 ... abort`.

Daniel's only action: complete the Google consent screen as daniel@. Do not ask him for codes, client JSON, or token evidence.
