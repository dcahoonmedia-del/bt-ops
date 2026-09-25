"""Process config. Writes stay disabled unless explicitly enabled."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


SECRET_RESOURCE = "projects/bt-intake-proof/secrets/BT-fieldworks-key/versions/latest"
SECRET_NAME = "BT-fieldworks-key"
DEFAULT_SCOPES = ("fieldwork.write",)
API_BASE = "https://api3.fieldworkhq.com/v3.1"


def _flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name, "1" if default else "0").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _csv(name: str) -> tuple[str, ...]:
    raw = os.environ.get(name, "")
    return tuple(item.strip() for item in raw.split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    writes_enabled: bool
    mapping_verified: bool
    store_path: Path
    api_base: str
    oauth_issuer: str
    oauth_audience: str
    oauth_resource: str
    oauth_jwks_url: str
    hs256_secret: str
    required_scopes: tuple[str, ...]
    permitted_users: tuple[str, ...]
    operator_key: str
    api_role: str
    proposal_ttl_seconds: int
    approval_ttl_seconds: int
    auth_mode: str = "jwt"
    auth0_config_url: str = ""
    auth0_client_id: str = ""
    auth0_client_secret: str = ""
    auth0_audience: str = ""
    auth0_base_url: str = ""
    auth0_allowed_callbacks: tuple[str, ...] = ()
    auth0_jwt_signing_key: str = ""
    auth0_storage_key: str = ""
    auth0_storage_path: str = ""
    auth0_subject_map: tuple[str, ...] = ()
    auth0_offline_access: bool = True

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            writes_enabled=_flag("FIELDWORK_WRITES_ENABLED", False),
            mapping_verified=_flag("FIELDWORK_MAPPING_VERIFIED", False),
            store_path=Path(os.environ.get("FW_WRITE_STORE") or "/var/lib/bt-fieldwork-write-mcp/write.sqlite"),
            api_base=os.environ.get("FIELDWORK_API_BASE") or API_BASE,
            oauth_issuer=os.environ.get("FW_WRITE_OAUTH_ISSUER", "").strip(),
            oauth_audience=os.environ.get("FW_WRITE_OAUTH_AUDIENCE", "").strip(),
            oauth_resource=os.environ.get("FW_WRITE_OAUTH_RESOURCE", "").strip(),
            oauth_jwks_url=os.environ.get("FW_WRITE_OAUTH_JWKS_URL", "").strip(),
            hs256_secret=os.environ.get("FW_WRITE_OAUTH_HS256", "").strip(),
            required_scopes=_csv("FW_WRITE_REQUIRED_SCOPES") or DEFAULT_SCOPES,
            permitted_users=tuple(item.lower() for item in _csv("FW_WRITE_PERMITTED_USERS")),
            operator_key=os.environ.get("FW_WRITE_OPERATOR_KEY", "").strip(),
            api_role=(os.environ.get("FIELDWORK_API_ROLE") or "readonly").strip().lower(),
            proposal_ttl_seconds=int(os.environ.get("FW_WRITE_PROPOSAL_TTL", "1800")),
            approval_ttl_seconds=int(os.environ.get("FW_WRITE_APPROVAL_TTL", "900")),
            auth_mode=(os.environ.get("FW_WRITE_AUTH_MODE") or "jwt").strip().lower(),
            auth0_config_url=os.environ.get("FW_WRITE_AUTH0_CONFIG_URL", "").strip(),
            auth0_client_id=os.environ.get("FW_WRITE_AUTH0_CLIENT_ID", "").strip(),
            auth0_client_secret=os.environ.get("FW_WRITE_AUTH0_CLIENT_SECRET", "").strip(),
            auth0_audience=os.environ.get("FW_WRITE_AUTH0_AUDIENCE", "").strip(),
            auth0_base_url=os.environ.get("FW_WRITE_AUTH0_BASE_URL", "").strip(),
            auth0_allowed_callbacks=_csv("FW_WRITE_AUTH0_ALLOWED_CALLBACKS"),
            auth0_jwt_signing_key=os.environ.get("FW_WRITE_AUTH0_JWT_SIGNING_KEY", "").strip(),
            auth0_storage_key=os.environ.get("FW_WRITE_AUTH0_STORAGE_KEY", "").strip(),
            auth0_storage_path=os.environ.get("FW_WRITE_AUTH0_STORAGE_PATH", "").strip(),
            auth0_subject_map=_csv("FW_WRITE_AUTH0_SUBJECT_MAP"),
            auth0_offline_access=_flag("FW_WRITE_AUTH0_OFFLINE_ACCESS", True),
        )

    def oauth_ready(self) -> bool:
        return bool(self.oauth_issuer and self.oauth_audience and self.oauth_resource and (self.oauth_jwks_url or self.hs256_secret))
