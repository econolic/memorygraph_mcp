#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import jwt


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _secret_bytes(raw_secret: str) -> bytes:
    value = raw_secret.strip().encode("utf-8")
    if len(value) < 32:
        raise ValueError("shared secret must be at least 32 chars")
    return value


def _kid(secret: bytes) -> str:
    return hashlib.sha256(secret).hexdigest()[:16]


def _issuer_from_host_port(host: str, port: int) -> str:
    if host in {"0.0.0.0", "::"}:
        host = "127.0.0.1"
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    return f"http://{host}:{port}"


def _jwks(secret: bytes) -> dict[str, object]:
    return {
        "keys": [
            {
                "kty": "oct",
                "use": "sig",
                "alg": "HS256",
                "kid": _kid(secret),
                "k": _b64url(secret),
            }
        ]
    }


def _mint(
    *,
    secret: bytes,
    issuer: str,
    audience: str,
    subject: str,
    workspace_id: str,
    scope: str,
    roles: list[str],
    ttl_seconds: int,
) -> str:
    now = datetime.now(tz=timezone.utc)
    payload = {
        "iss": issuer,
        "aud": audience,
        "sub": subject,
        "workspace_id": workspace_id,
        "roles": roles,
        "scope": scope,
        "iat": int(now.timestamp()),
        "nbf": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ttl_seconds)).timestamp()),
    }
    return str(jwt.encode(payload, key=secret, algorithm="HS256", headers={"kid": _kid(secret)}))


def _serve(*, host: str, port: int, issuer: str, secret: bytes) -> None:
    jwks_doc = _jwks(secret)
    openid_cfg = {
        "issuer": issuer,
        "jwks_uri": f"{issuer}/.well-known/jwks.json",
        "token_endpoint": f"{issuer}/token",
        "authorization_endpoint": f"{issuer}/authorize",
        "response_types_supported": ["token"],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": ["HS256"],
    }

    class Handler(BaseHTTPRequestHandler):
        def _json(self, code: int, payload: dict[str, object]) -> None:
            body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path == "/.well-known/openid-configuration":
                self._json(200, openid_cfg)
                return
            if path == "/.well-known/jwks.json":
                self._json(200, jwks_doc)
                return
            if path == "/healthz":
                self._json(200, {"status": "ok"})
                return
            self._json(404, {"error": "not_found"})

        def log_message(self, format: str, *args: object) -> None:  # noqa: A003
            return

    server = ThreadingHTTPServer((host, port), Handler)
    print(json.dumps({"issuer": issuer, "jwks_uri": openid_cfg["jwks_uri"]}, ensure_ascii=True))
    server.serve_forever()


def main() -> int:
    parser = argparse.ArgumentParser(description="Local OIDC test issuer + JWT mint helper")
    sub = parser.add_subparsers(dest="cmd", required=True)

    serve = sub.add_parser("serve", help="Run local OIDC issuer with JWKS")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=9010)
    serve.add_argument("--issuer", default="")
    serve.add_argument(
        "--shared-secret",
        default="strict-oauth-smoke-secret-please-change-32chars",
    )

    mint = sub.add_parser("mint", help="Mint bearer token for strict_oauth smoke")
    mint.add_argument("--issuer", required=True)
    mint.add_argument("--audience", default="hybrid-kb-mcp")
    mint.add_argument("--subject", default="u1")
    mint.add_argument("--workspace-id", default="w1")
    mint.add_argument("--scope", default="mcp.read mcp.write")
    mint.add_argument("--roles", default="reader")
    mint.add_argument("--ttl-seconds", type=int, default=900)
    mint.add_argument(
        "--shared-secret",
        default="strict-oauth-smoke-secret-please-change-32chars",
    )

    args = parser.parse_args()
    secret = _secret_bytes(args.shared_secret)

    if args.cmd == "serve":
        issuer = args.issuer.strip() or _issuer_from_host_port(args.host, args.port)
        _serve(host=args.host, port=args.port, issuer=issuer, secret=secret)
        return 0

    roles = [r.strip() for r in args.roles.split(",") if r.strip()]
    token = _mint(
        secret=secret,
        issuer=args.issuer.strip(),
        audience=args.audience.strip(),
        subject=args.subject.strip(),
        workspace_id=args.workspace_id.strip(),
        scope=args.scope.strip(),
        roles=roles,
        ttl_seconds=max(60, args.ttl_seconds),
    )
    print(token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
