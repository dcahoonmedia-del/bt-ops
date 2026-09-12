# Stopped for Daniel — one more Cloud localhost URL

The Cloud authorization code was exchanged, then Google userinfo rejected the Cloud-only token and I did not persist it. That code cannot be reused. No service account, JSON key, or Pub/Sub pull was performed.

Open the same Cloud URL again as **daniel@btpestcontrol.com** (not contactus@) and send the new localhost address-bar URL.

https://accounts.google.com/o/oauth2/v2/auth?client_id=1028131400538-5r57fq95el2uhmmtp2m38m3lgab7loa8.apps.googleusercontent.com&redirect_uri=http%3A%2F%2Flocalhost&response_type=code&scope=https%3A%2F%2Fwww.googleapis.com%2Fauth%2Fcloud-platform&access_type=offline&prompt=consent&include_granted_scopes=false&login_hint=daniel%40btpestcontrol.com

Do not send `BT-INTAKE-PROOF-*` emails yet.
