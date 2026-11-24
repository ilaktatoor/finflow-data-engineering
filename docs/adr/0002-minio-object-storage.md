# 0002 — MinIO for the lake, accessed through `pyarrow.fs`

Status: Accepted

## Context
The lake (Bronze, Silver, quarantine, reports) needs object storage with an S3
API so the design transfers to cloud storage, while the lightweight profile
must work with a plain directory.

## Decision
- **MinIO** provides the S3 API in the data and full profiles.
- All lake I/O goes through `finflow.common.storage.LakeStorage`, a thin layer
  over `pyarrow.fs`: `LocalFileSystem` (lightweight) or `S3FileSystem` with
  `endpoint_override` (MinIO). No `boto3` or `minio` client dependency.
- **Image provenance**: MinIO stopped publishing community container images
  in 2025, and `minio/minio` on Docker Hub and `quay.io/minio/minio` showed no
  current tags when this was built (2026-11-24). Compose uses
  `pgsty/minio:RELEASE.2026-08-04T00-00-00Z`, a community build of upstream
  MinIO maintained by the Pigsty project.

## Alternatives
- *LocalStack / other S3 emulators*: heavier, emulate far more than needed.
- *SeaweedFS, Garage, RustFS*: viable S3-compatible stores, but the brief names MinIO.
- *Build MinIO from source in a Dockerfile*: fully controlled provenance, but a
  Go toolchain build on every fresh clone.
- *Plain filesystem everywhere*: would not exercise S3 semantics (no atomic
  rename, eventual listing, credentials).

## Consequences
- One storage class, two backends, no branching in pipeline code.
- DuckDB reads the lake directly in lightweight mode; in data mode the files
  reach DuckDB through PyArrow datasets on the S3 filesystem.
- The third-party image is a supply-chain dependency. It is pinned by tag;
  pinning by digest, or building from source, is listed in the roadmap.

## Trade-offs
`pyarrow.fs` exposes fewer S3 features than a dedicated client (no object
versioning or lifecycle rules). The write-once rule is enforced in code
(manifest check) rather than by bucket object locking.
