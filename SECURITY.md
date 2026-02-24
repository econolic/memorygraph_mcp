# Security Policy

## Supported Versions

- `main`: supported for security fixes on a best-effort basis
- Latest tagged release (`v0.x`): supported
- Older releases: not guaranteed

This project is an open-source **self-hosted** MCP server. Security posture depends heavily on operator configuration.

## Reporting a Vulnerability

Do not open a public GitHub issue for suspected security vulnerabilities.

Use a private disclosure channel:

- Email the maintainer/owner listed in repository settings (preferred), or
- Open a private security advisory via GitHub Security Advisories (if enabled)

Include:

- affected version / commit SHA
- deployment mode (`stdio`, HTTP local, self-hosted behind proxy, etc.)
- reproduction steps / proof of concept
- impact assessment (ACL leakage, auth bypass, data loss, DoS, etc.)
- logs or traces (redacted)

## Scope

Examples of in-scope issues:

- auth bypass (`strict`, `strict_oauth`, header precedence)
- ACL leakage (cross-workspace / cross-subject reads or deletes)
- resource access control bypass (`kb://doc/*`, `kb://chunk/*`, `kb://entity/*`, `kb://memory/*`)
- unsafe defaults leading to exposure in self-hosted profile
- secret handling issues (JWT/OIDC config, credential disclosure in logs)
- injection vulnerabilities in storage queries (Cypher, SQL, vector filters)

Examples typically out of scope (unless combined with a project defect):

- insecure operator deployment (public internet exposure without TLS/reverse proxy/rate limiting)
- default passwords left unchanged in local/dev examples
- vulnerabilities in third-party infrastructure not caused by this project

## Disclosure Expectations

- Please allow reasonable time for triage and patching before public disclosure.
- Reported issues will be acknowledged and triaged as quickly as possible on a best-effort basis.

