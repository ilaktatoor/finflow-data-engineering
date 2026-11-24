# 0010 — Deliberately small datasets

Status: Accepted (supersedes the initial 10k/100k/1M profiles)

## Context
The first brief asked for profiles up to one million transactions. The
project's purpose is to demonstrate concepts repeatedly on a personal laptop.

## Decision
Profiles: small 2,000 (default), medium 5,000, large 10,000 transactions,
capped in code. About 5% of records are intentionally invalid. Incremental
days carry 50–100 transactions.

## Consequences
- The full demo runs in about 7 seconds; all generated artifacts take under
  30 MB (measured).
- Every concept (SCD2, watermarks, late data, window functions, partition
  pruning, idempotency) is still exercised.
- Performance measurements are honest but small: several optimisations show
  little or no benefit at this size, and the docs say so.

## Trade-offs
Nothing here demonstrates behaviour under memory pressure, skew or
distributed execution. Claims about scale would be unverified, so none are made.
