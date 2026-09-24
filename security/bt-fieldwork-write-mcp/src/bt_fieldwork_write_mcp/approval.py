"""Independent operator HMAC gate. Model `approved=true` is ignored."""

from __future__ import annotations

import hmac
from hashlib import sha256

from .digest import sha256_hex


def mint_operator_token(operator_key: str, proposal_id: str, digest: str, expires_at: str) -> str:
    if not operator_key:
        raise ValueError("operator_key_missing")
    message = f"{proposal_id}\n{digest}\n{expires_at}".encode("utf-8")
    return hmac.new(operator_key.encode("utf-8"), message, sha256).hexdigest()


def token_fingerprint(token: str) -> str:
    return sha256_hex(token)


def verify_operator_token(
    operator_key: str,
    token: str,
    proposal_id: str,
    digest: str,
    expires_at: str,
) -> bool:
    if not operator_key or not token:
        return False
    expected = mint_operator_token(operator_key, proposal_id, digest, expires_at)
    return hmac.compare_digest(expected, token)
