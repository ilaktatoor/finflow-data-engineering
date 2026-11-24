-- Business question: How does an upsert apply a late status correction without
--   duplicating the transaction?
-- Explanation: INSERT ... ON CONFLICT (key) DO UPDATE inserts new keys and
--   updates existing ones atomically. The WHERE on the update side makes the
--   operation order-safe: an older batch can never overwrite a newer state.
--   The runner executes examples inside a transaction that is rolled back,
--   so this demonstration does not change the warehouse.
-- Expected result: one row for T_DEMO with status COMPLETED (the PENDING
--   insert, then the newer correction; the stale re-send is ignored).
-- Performance: a unique-index probe per row. For bulk upserts, stage rows in a
--   table and upsert with INSERT ... SELECT, as sql/warehouse/20_*.sql does.
CREATE TEMPORARY TABLE demo_upsert (
    transaction_id VARCHAR PRIMARY KEY,
    status VARCHAR NOT NULL,
    batch_id VARCHAR NOT NULL
);
INSERT INTO demo_upsert VALUES ('T_DEMO', 'PENDING', 'b000');
INSERT INTO demo_upsert VALUES ('T_DEMO', 'COMPLETED', 'b002')
ON CONFLICT (transaction_id) DO UPDATE SET status = EXCLUDED.status, batch_id = EXCLUDED.batch_id
WHERE EXCLUDED.batch_id >= demo_upsert.batch_id;
INSERT INTO demo_upsert VALUES ('T_DEMO', 'PENDING', 'b001')
ON CONFLICT (transaction_id) DO UPDATE SET status = EXCLUDED.status, batch_id = EXCLUDED.batch_id
WHERE EXCLUDED.batch_id >= demo_upsert.batch_id;
SELECT * FROM demo_upsert;
