-- Business question: Which raw records has the ELT not transformed yet?
-- Explanation: the ELT keeps a high-water mark (elt_watermark.last_load_seq).
--   Incremental processing reads only rows above it, instead of rescanning
--   the whole staging table. See sql/staging/10_elt_check_new_transactions.sql
--   for the production version of this filter.
-- Expected result: 0 rows right after `finflow elt`; after loading a new batch
--   with load_raw only, the new batch's rows.
-- Performance: load_seq is the primary key, so this is an index range scan in
--   PostgreSQL and a zone-map-pruned scan in DuckDB.
SELECT r.batch_id, COUNT(*) AS pending_rows, MIN(r.load_seq) AS from_seq, MAX(r.load_seq) AS to_seq
FROM stg_raw_transactions r
WHERE r.load_seq > (SELECT COALESCE(MAX(last_load_seq), 0) FROM elt_watermark WHERE entity = 'transactions')
GROUP BY r.batch_id
ORDER BY r.batch_id;
