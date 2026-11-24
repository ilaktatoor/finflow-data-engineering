-- Business question: What would the repayment schedule of loan L00001 look like
--   under constant-principal amortization (equal principal every month,
--   interest on the remaining balance)?
-- Explanation: a recursive CTE starts from the disbursed principal (anchor
--   member) and applies one month per iteration (recursive member) until the
--   term ends. Everything is integer minor units; the monthly rate is
--   annual_rate_micros / 12 / 1,000,000, applied with integer division.
-- Expected result: term_months rows (12, 24 or 36). Interest falls every month
--   and the closing balance reaches exactly 0 because the last installment
--   absorbs the rounding remainder.
-- Performance: recursion depth = term (<= 36 iterations). Recursive CTEs suit
--   iterative calculations and hierarchies; they are not a way to scan tables.
WITH RECURSIVE loan AS (
    SELECT loan_id, principal_minor, annual_rate_micros, term_months,
           principal_minor / term_months AS principal_step
    FROM dim_loan
    WHERE loan_id = 'L00001'
),
schedule (installment, opening_minor, interest_minor, principal_minor, closing_minor) AS (
    SELECT
        1,
        l.principal_minor,
        l.principal_minor * l.annual_rate_micros / 12000000,
        l.principal_step,
        l.principal_minor - l.principal_step
    FROM loan l
    UNION ALL
    SELECT
        s.installment + 1,
        s.closing_minor,
        s.closing_minor * l.annual_rate_micros / 12000000,
        CASE WHEN s.installment + 1 = l.term_months THEN s.closing_minor ELSE l.principal_step END,
        CASE WHEN s.installment + 1 = l.term_months THEN 0 ELSE s.closing_minor - l.principal_step END
    FROM schedule s
    CROSS JOIN loan l
    WHERE s.installment < l.term_months
)
SELECT
    installment,
    opening_minor,
    interest_minor,
    principal_minor,
    interest_minor + principal_minor AS payment_minor,
    closing_minor
FROM schedule
ORDER BY installment;
