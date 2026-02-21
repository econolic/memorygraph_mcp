from __future__ import annotations

from typing import Any

import jwt
from mcp.server.auth.provider import AccessToken, TokenVerifier

_DEFAULT_ALGORITHMS = (
    "RS256",
    "RS384",
    "RS512",
    "ES256",
    "ES384",
    "ES512",
    "PS256",
    "PS384",
    "PS512",
)


class OidcJwksTokenVerifier(TokenVerifier):
    def __init__(
        self,
        *,
        issuer_url: str,
        audience: str,
        jwks_url: str,
        required_scopes: tuple[str, ...] = (),
    ) -> None:
        self._issuer_url = issuer_url.strip().rstrip("/")
        self._audience = audience.strip()
        self._jwks_url = jwks_url.strip()
        self._required_scopes = tuple(scope.strip() for scope in required_scopes if scope.strip())
        self._jwk_client = jwt.PyJWKClient(self._jwks_url) if self._jwks_url else None

    @property
    def enabled(self) -> bool:
        return bool(self._issuer_url and self._jwks_url)

    @property
    def required_scopes(self) -> tuple[str, ...]:
        return self._required_scopes

    def decode_token(self, token: str) -> dict[str, Any]:
        if not self.enabled:
            raise ValueError("oidc_not_configured")
        if self._jwk_client is None:
            raise ValueError("jwks_client_unavailable")

        signing_key = self._jwk_client.get_signing_key_from_jwt(token)
        if self._audience:
            claims = jwt.decode(
                token,
                key=signing_key.key,
                algorithms=self._resolve_algorithms(token),
                issuer=self._issuer_url,
                audience=self._audience,
            )
        else:
            claims = jwt.decode(
                token,
                key=signing_key.key,
                algorithms=self._resolve_algorithms(token),
                issuer=self._issuer_url,
                options={"verify_aud": False},
            )
        scopes = self.extract_scopes(claims)
        if self._required_scopes:
            missing = [scope for scope in self._required_scopes if scope not in scopes]
            if missing:
                raise PermissionError(f"missing_required_scope:{','.join(missing)}")
        return claims

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            claims = self.decode_token(token)
        except Exception:
            return None

        return AccessToken(
            token=token,
            client_id=self._extract_client_id(claims),
            scopes=self.extract_scopes(claims),
            expires_at=self._extract_expires_at(claims),
        )

    @staticmethod
    def extract_scopes(claims: dict[str, Any]) -> list[str]:
        scope_claim = claims.get("scope")
        if isinstance(scope_claim, str):
            scopes = [scope for scope in scope_claim.split(" ") if scope.strip()]
            if scopes:
                return scopes

        scp_claim = claims.get("scp")
        if isinstance(scp_claim, list):
            scopes = [str(scope).strip() for scope in scp_claim if str(scope).strip()]
            if scopes:
                return scopes
        if isinstance(scp_claim, str):
            scopes = [scope for scope in scp_claim.split(" ") if scope.strip()]
            if scopes:
                return scopes

        return []

    @staticmethod
    def _extract_client_id(claims: dict[str, Any]) -> str:
        for key in ("azp", "client_id", "sub"):
            value = str(claims.get(key, "")).strip()
            if value:
                return value
        return "unknown"

    @staticmethod
    def _extract_expires_at(claims: dict[str, Any]) -> int | None:
        value = claims.get("exp")
        if isinstance(value, (int, float)):
            return int(value)
        return None

    @staticmethod
    def _resolve_algorithms(token: str) -> tuple[str, ...]:
        try:
            header = jwt.get_unverified_header(token)
        except Exception:
            return _DEFAULT_ALGORITHMS

        alg = str(header.get("alg", "")).strip()
        if not alg or alg.lower() == "none":
            return _DEFAULT_ALGORITHMS
        return (alg,)
