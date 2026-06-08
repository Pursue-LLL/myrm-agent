# Security Policy

## Supported Versions

Security fixes are applied to the latest release on the default branch of [myrm-agent](https://github.com/Pursue-LLL/myrm-agent).

| Component | Scope |
|-----------|--------|
| `myrm-agent-server` | FastAPI backend, channels, API surface |
| `myrm-agent-frontend` | Next.js Web UI |
| `myrm-agent-desktop` | Tauri desktop shell |

`myrm-agent-harness` and `myrm-control-plane` are separate private repositories; report issues in those components through your MyrmAgent enterprise contact if applicable.

## Reporting a Vulnerability

**Please do not open public GitHub issues for security vulnerabilities.**

Use [GitHub Private Vulnerability Reporting](https://github.com/Pursue-LLL/myrm-agent/security/advisories/new) on the repository, or email **security@myrmagent.ai** if you cannot use GitHub.

Include:

- Affected component and version or commit hash
- Steps to reproduce
- Impact assessment (confidentiality, integrity, availability)
- Proof of concept if available

We aim to acknowledge reports within **72 hours** and provide a remediation timeline when confirmed.

## Scope Notes

- Single-tenant deployments: each user runs an isolated server instance (local, desktop sidecar, or CP-assigned sandbox).
- Default auth middleware applies to most `/api/v1/*` routes; internal CP endpoints use separate token headers.
- Sandbox code execution is intentional product behavior; reports should focus on escapes, cross-tenant access, or authentication bypass — not expected agent tool capabilities in configured workspaces.

## Safe Harbor

We support good-faith security research that follows this policy and avoids privacy violations, service degradation, or data destruction.
