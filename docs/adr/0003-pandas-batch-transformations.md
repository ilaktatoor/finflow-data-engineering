# 0003 — Pandas + Pandera for batch transformations

Status: Accepted

## Context
Batches are small (hundreds to ten thousand records). Validation is rich:
per-field parsing, domain checks, cross-field business rules, references to
other entities and earlier batches, and every rejected record must keep its
payload and *all* its reasons.

## Decision
Transform with **Pandas 3** (vectorised operations, nullable `Int64`,
`string` and `boolean` dtypes) and express domain/business rules as **Pandera**
schemas generated from the data contracts. Failure cases from Pandera
(`lazy=True`) are mapped back to row positions and reason codes.

## Alternatives
- *Polars*: faster and stricter typing; less ubiquitous in job descriptions
  and the brief asks for Pandas.
- *Spark*: built for data that does not fit one machine; here it would add a
  JVM, a cluster abstraction and seconds of start-up to process 2,000 rows.
- *Great Expectations*: strong for reporting; heavier to configure and less
  natural for row-level quarantine than Pandera's failure cases.
- *Pure SQL*: shown in the ELT path; harder to keep every rejection reason.

## Consequences
- Rules live once, in `validation/contracts.py`, and are unit-tested per reason.
- Two Pandera behaviours matter and are documented in code: dataframe-level
  checks report one failure per column (de-duplicated), and checks default to
  `ignore_na=True`, which must be disabled for rules that are about nulls.
- Everything runs in memory; at 10,000 transactions peak RSS stays well under
  1 GB.

## Trade-offs
In-memory processing caps the data size; chunked processing is demonstrated
(`finflow benchmark`) but not used in the pipeline, because at this size it is
slower (measured) and not needed.
