-- Upsert daily exchange rates (a later batch may correct an earlier rate).
INSERT INTO ref_exchange_rate (currency_code, rate_date, rate_micros, batch_id)
SELECT currency_code, CAST(rate_date AS DATE), rate_to_mxn_micros, batch_id
FROM stg_exchange_rates
ON CONFLICT (currency_code, rate_date) DO UPDATE
SET rate_micros = EXCLUDED.rate_micros,
    batch_id = EXCLUDED.batch_id;
