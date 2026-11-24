# 15 · Interview preparation

## A two-minute project pitch (adapt it to your own words)
"FinFlow is a personal reference implementation of a batch data platform for a
fictional bank, built with AI assistance and verified by me. Synthetic data
from three source types — files, a REST API and an operational Postgres —
lands in an immutable Bronze layer, is validated with Pandas and Pandera into
Parquet, and loads into a star schema with an SCD2 customer dimension. Loads
are transactional and idempotent, watermarks only advance with committed data,
invalid records are quarantined with their payload, and a quality gate stops
bad batches. The same SQL runs on DuckDB for a laptop profile and on
PostgreSQL with MinIO and Airflow for the full one. An independent SQL-only
ELT path reconciles with the ETL to the cent."

Be ready to say what you would change for production (see
`docs/architecture/security.md` and `docs/roadmap.md`) and what you would not
claim (scale: the data is deliberately small).

## Questions this project lets you answer with evidence

| Question | Point to |
|---|---|
| How do you make pipelines idempotent? | `docs/architecture/incremental-processing.md`; `test_forced_rerun_is_idempotent` |
| What happens on failure mid-load? | `pipeline.load` transaction; `make demo-failure` |
| How do you handle bad data? | quarantine + gate; `make demo-quality-gate` |
| Explain SCD2 | `12_load_customers_scd2.sql`; point-in-time join in `20_load_fact_transactions.sql` |
| How do you represent money? | ADR 0007; `common/money.py` |
| ETL or ELT? | `docs/architecture/elt-design.md` |
| Late-arriving data? | `is_late_arriving`, corrections, backfill |
| Watermarks? | `sources/operational.py`; watermark inside the load transaction |
| How do you test pipelines? | `docs/testing.md` |
| Performance tuning? | `docs/performance.md` — including where optimisations did *not* help |

## Practice set
Each earlier module ends with interview questions; answers are in
`solutions/`. Additional cross-cutting questions:

1. Design a pipeline for card transactions arriving every minute. What changes from FinFlow?
2. A dashboard shows a 3% drop in yesterday's volume. How do you investigate?
3. A source system starts sending amounts in cents instead of decimals. How would FinFlow notice?
4. Two teams disagree about "total processed value". How do you resolve it?
5. How would you backfill a year of data after fixing a transformation bug?

## Live-coding warm-ups (from this repository)
- Latest record per key with `ROW_NUMBER` (`12_deduplication.sql`).
- Running total and 7-day average (`11_*.sql`).
- Vectorise a row-by-row Pandas function (`bench_vectorized_vs_loop`).
- Parse decimal strings into integer cents without floats (`money.py`).

Solutions: [solutions/15.md](solutions/15.md)
