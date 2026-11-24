# 0008 — Data rejection and quarantine

Status: Accepted

## Context
Invalid records must never disappear, but must not reach the warehouse, and a
batch full of them should stop the pipeline.

## Decision
- Every input record ends in exactly one of: accepted (Silver), rejected, or
  duplicate. `input = accepted + rejected + duplicates` is checked per entity.
- Rejected and duplicate records go to `rejected/<entity>/batch_id=<id>.parquet` with
  the original payload (`raw_record`), the natural key, the disposition and
  **all** failed rules.
- Record-level failures do not fail the batch; the **reject rate** does
  (critical > 10%, warning > 2%). A gated batch writes its quarantine and
  quality report but nothing to Silver or the warehouse.
- Duplicates are recorded but not counted as rejections.

## Alternatives
- *Fail the batch on the first bad record*: one typo blocks a day of data.
- *Drop bad records with a log line*: silent data loss.
- *Load everything with an `is_valid` flag*: pushes the problem to every consumer.

## Consequences
- Quality is measurable per rule and per batch (`fact_data_quality`).
- A rejected record can be fixed at the source and the batch replayed.

## Trade-offs
The quarantine stores raw payloads, including any personal data they contain;
with real data it would need the same access controls as the source.
