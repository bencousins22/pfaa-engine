# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| main | Yes |
| < main | No |

## Reporting a Vulnerability

If you discover a security vulnerability, please report it responsibly:

1. **Do not** open a public issue
2. Email the maintainer or use GitHub's [private vulnerability reporting](https://github.com/bencousins22/pfaa-engine/security/advisories/new)
3. Include steps to reproduce, impact assessment, and any suggested fixes

We will respond within 48 hours and aim to release a fix within 7 days for critical issues.

## Security Measures

PFAA includes built-in security features:

- **PreToolUse hook** — blocks commands containing secrets (API keys, tokens, passwords)
- **Sensitive file detection** — warns when reading `.env`, `.pem`, credential files
- **CodeQL scanning** — automated weekly security analysis (Python + TypeScript)
- **pip-audit** — dependency vulnerability scanning in CI
- **Dependabot** — automated dependency update PRs
