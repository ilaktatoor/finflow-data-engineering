# Security policy

FinFlow is a personal learning project that runs on `127.0.0.1` with
synthetic data. It is **not production-ready** and must not be exposed to a
network or used with real financial or personal data.

The measures in place and the known limitations are documented in
[docs/architecture/security.md](docs/architecture/security.md).

## Reporting a problem

If you find a security issue (for example a committed secret, or a default
that exposes a service beyond localhost), please open a GitHub issue without
sensitive details, or use GitHub's private vulnerability reporting if it is
enabled on the repository. There is no bounty and no SLA; this is a hobby project.

## Before publishing a fork

- Never commit `.env`; only `.env.example` with placeholders.
- Run `uv run pre-commit run --all-files` (includes gitleaks).
- Do not commit generated data (`data/` is ignored except `data/samples/`).
