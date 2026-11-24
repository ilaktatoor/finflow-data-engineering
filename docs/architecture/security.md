# Security

FinFlow is a **local demonstration**. It is designed to be safe to publish and
safe to run on a laptop, not to be deployed. This page lists what is in place
and, just as important, what is not.

## In place

- **Synthetic data only.** Names and cities come from Faker; emails use the
  reserved `example.test` domain; cards store only 4 random digits, never a
  card number. No real bank, person or dataset is involved.
- **No secrets in the repository.** Credentials live in `.env` (git-ignored);
  `.env.example` holds placeholders named `change-me-local-only-*`.
  Compose refuses to start without them (`${VAR:?}`).
- **Localhost only.** Every published port binds to `127.0.0.1`.
- **Least privilege for BI.** Metabase connects as `analytics_reader`, a role
  with `SELECT` only (`infrastructure/postgres/warehouse-init.sh`).
- **Network split.** Source systems and the analytical side are separate
  Docker networks; only Airflow (the pipeline host) joins both.
- **Containers.** No privileged containers; the app image runs as a non-root
  user and the source API container is read-only with the landing data
  mounted read-only.
- **SQL.** User-facing values are bound parameters. Identifiers interpolated
  into SQL come from fixed allowlists in code (marked `noqa: S608`).
- **Integrity.** Bronze objects carry SHA-256 checksums verified on replay;
  tampering raises `BronzeConflictError`.
- **Secret scanning.** `gitleaks` runs in pre-commit and CI; the
  pre-commit `detect-private-key` and large-file hooks guard the rest.

## Not in place (known limitations)

- No TLS anywhere; MinIO, PostgreSQL, the API, Airflow and Metabase speak plain HTTP/TCP.
- Development passwords are static, shared via `.env`, and never rotated.
- Airflow uses the simple auth manager with one admin user.
- The FastAPI simulator has no authentication or rate limiting.
- MinIO root credentials are used by the pipeline (no per-service policies).
- No encryption at rest, no audit logging, no row-level security.
- The MinIO image is a community build (see ADR 0002), pinned by tag, not digest.

Each of these is acceptable only because nothing leaves `127.0.0.1` and the
data is fake. [cloud-mapping](../learning/14-cloud-architecture-concepts.md)
discusses how a managed platform would address them (IAM, Secret Manager, …).
