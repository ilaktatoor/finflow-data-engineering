"""Bronze -> Silver: parse, validate, deduplicate, conform and enrich one entity.

Every input record ends in exactly one of three places, so the batch always
reconciles: ``input = accepted + rejected + duplicates``.

Validation runs in stages and a record keeps every reason it collects:

1. schema    — required fields present in the payload        -> ``schema_mismatch``
2. parsing   — timestamps, dates, amounts, rates, integers   -> ``invalid_format:<col>``
3. Pandera   — required values, domains, business rules       -> ``missing:<col>``, ``<col>:<check>``
4. uniqueness — natural key seen earlier in the batch          -> disposition ``duplicate``
5. references — foreign keys and ownership consistency        -> ``unknown_ref:<col>``, ``owner_mismatch``
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd
import pandera.pandas as pa

from finflow.common.config import RiskConfig
from finflow.common.money import convert_minor, parse_amount_minor, parse_rate_micros
from finflow.transformations.risk import flag_transactions
from finflow.validation.contracts import EntityContract, pandera_schema

SCD2_ATTRIBUTES = ("first_name", "last_name", "email", "city", "state", "segment")
MICROS = 1_000_000


@dataclass
class TransformContext:
    batch_id: str
    source_system: str
    ingested_at: datetime  # naive UTC
    window_start: datetime  # naive UTC
    window_end: datetime  # naive UTC
    risk: RiskConfig
    known_keys: dict[str, set[str]] = field(default_factory=dict)
    account_owner: dict[str, str] = field(default_factory=dict)
    # currency_code, rate_date, rate_to_mxn_micros
    rates: pd.DataFrame = field(default_factory=pd.DataFrame)


@dataclass
class EntityResult:
    entity: str
    accepted: pd.DataFrame
    quarantine: pd.DataFrame
    input_count: int
    rule_failures: Counter[str]
    freshness_lag_hours: float | None = None

    @property
    def accepted_count(self) -> int:
        return len(self.accepted)

    @property
    def rejected_count(self) -> int:
        return int((self.quarantine["disposition"] == "rejected").sum()) if len(self.quarantine) else 0

    @property
    def duplicate_count(self) -> int:
        return int((self.quarantine["disposition"] == "duplicate").sum()) if len(self.quarantine) else 0

    @property
    def reject_rate(self) -> float:
        return self.rejected_count / self.input_count if self.input_count else 0.0

    def reconciles(self) -> bool:
        return self.input_count == self.accepted_count + self.rejected_count + self.duplicate_count


def _to_naive_utc(values: pd.Series, fmt: str) -> pd.Series:
    parsed = pd.to_datetime(values, utc=True, errors="coerce", format=fmt)
    return parsed.dt.tz_localize(None).astype("datetime64[us]")


def _add_reason(reasons: list[list[str]], mask: pd.Series, reason: str) -> None:
    for position in np.flatnonzero(mask.to_numpy(dtype=bool, na_value=False)):
        reasons[position].append(reason)


def _pandera_reasons(
    df: pd.DataFrame, schema: pa.DataFrameSchema, parse_failed: dict[str, pd.Series]
) -> list[tuple[int, str]]:
    """Run Pandera lazily and turn its failure cases into (row position, reason)."""
    if df.empty:
        return []
    try:
        schema.validate(df, lazy=True)
        return []
    except pa.errors.SchemaErrors as exc:
        cases = exc.failure_cases
    found: dict[tuple[int, str], None] = {}  # ordered set
    for row in cases.itertuples(index=False):
        if row.index is None or pd.isna(row.index):
            continue
        position = int(row.index)
        column = str(row.column)
        check = str(row.check)
        if row.schema_context == "DataFrameSchema":
            # Dataframe-level (cross-field) checks are reported once per column; keep one.
            found[(position, f"business:{check}")] = None
        elif check == "not_nullable":
            # A null caused by a failed parse is already reported as invalid_format.
            failed = parse_failed.get(column)
            if failed is None or not bool(failed.iloc[position]):
                found[(position, f"missing:{column.removesuffix('_minor').removesuffix('_micros')}")] = None
        else:
            name = check.split("(")[0]
            found[(position, f"{column.removesuffix('_minor').removesuffix('_micros')}:{name}")] = None
    return list(found)


def transform_entity(
    contract: EntityContract, records: list[dict[str, Any]], ctx: TransformContext
) -> EntityResult:
    n = len(records)
    reasons: list[list[str]] = [[] for _ in range(n)]
    columns = list(contract.columns)

    # 1. Schema: fields the producer promised must at least be present as keys.
    required = set(contract.required)
    schema_ok = pd.Series([required <= r.keys() for r in records], dtype=bool)
    _add_reason(reasons, ~schema_ok, "schema_mismatch")

    raw = pd.DataFrame.from_records(records, columns=columns) if n else pd.DataFrame(columns=columns)
    raw = raw.astype("string")
    for column in columns:
        stripped = raw[column].str.strip()
        raw[column] = stripped.where(stripped != "")

    # 2. Parse into typed columns. A non-null raw value that fails to parse is invalid.
    typed = pd.DataFrame(index=raw.index)
    parse_failed: dict[str, pd.Series] = {}
    for column in columns:
        values = raw[column]
        if column in contract.uppercase:
            typed[column] = values.str.upper()
        elif column in contract.timestamps:
            typed[column] = _to_naive_utc(values, "ISO8601")
        elif column in contract.dates:
            typed[column] = _to_naive_utc(values, "%Y-%m-%d")
        elif column in contract.amounts:
            typed[f"{column}_minor"] = parse_amount_minor(values)
        elif column in contract.rates:
            typed[f"{column}_micros"] = parse_rate_micros(values)
        elif column in contract.integers:
            typed[column] = pd.to_numeric(values.where(values.str.fullmatch(r"\d+")), errors="coerce").astype(
                "Int64"
            )
        else:
            typed[column] = values
        typed_name = (
            f"{column}_minor"
            if column in contract.amounts
            else f"{column}_micros"
            if column in contract.rates
            else column
        )
        failed = values.notna() & typed[typed_name].isna()
        parse_failed[typed_name] = failed
        _add_reason(reasons, failed & schema_ok, f"invalid_format:{column}")

    # 3. Pandera domain and business rules (rows with a broken schema are skipped:
    #    their missing fields would only produce noise).
    schema = pandera_schema(contract)
    candidates = typed[schema_ok.to_numpy()]
    for position, reason in _pandera_reasons(candidates, schema, parse_failed):
        reasons[position].append(reason)

    # Entity-specific derived columns needed by later stages.
    if contract.name == "exchange_rates":
        typed["rate_key"] = typed["currency_code"] + "|" + typed["rate_date"].dt.strftime("%Y-%m-%d")

    valid = pd.Series([not r for r in reasons], dtype=bool)

    # 4. Uniqueness among otherwise-valid records: first occurrence wins.
    key = typed[contract.natural_key]
    duplicate = valid & key.where(valid).duplicated(keep="first")

    # 5. Referential integrity and consistency for valid, non-duplicate records.
    candidates_mask = valid & ~duplicate
    for column, referenced in contract.references.items():
        known = ctx.known_keys.get(referenced, set())
        unknown = candidates_mask & typed[column].notna() & ~typed[column].isin(known)
        _add_reason(reasons, unknown, f"unknown_ref:{column}")
    if {"account_id", "customer_id"} <= set(contract.references):
        owner = typed["account_id"].map(ctx.account_owner)
        mismatch = candidates_mask & owner.notna() & (owner != typed["customer_id"])
        _add_reason(reasons, mismatch, "owner_mismatch")
    if contract.name == "transactions":
        typed = _attach_rates(typed, ctx.rates)
        missing_rate = candidates_mask & typed["currency_code"].ne("MXN") & typed["rate_micros"].isna()
        missing_rate &= typed["event_ts"].notna()
        _add_reason(reasons, missing_rate, "missing_exchange_rate")

    rejected = pd.Series([bool(r) for r in reasons], dtype=bool) & ~duplicate
    accepted_mask = ~rejected & ~duplicate

    accepted = _finalize(contract, typed[accepted_mask.to_numpy()].copy(), ctx)
    quarantine = _quarantine(contract, records, typed, reasons, rejected, duplicate, ctx)

    failures: Counter[str] = Counter(reason for r in reasons for reason in r)
    failures["duplicate"] = int(duplicate.sum())

    lag = None
    if contract.name in ("transactions", "exchange_rates") and len(accepted):
        newest = accepted[contract.watermark].max()
        lag = round((ctx.window_end - newest).total_seconds() / 3600, 2)

    return EntityResult(contract.name, accepted, quarantine, n, failures, lag)


def _attach_rates(typed: pd.DataFrame, rates: pd.DataFrame) -> pd.DataFrame:
    typed = typed.copy()
    typed["txn_date"] = typed["event_ts"].dt.normalize()
    if rates.empty:
        lookup = pd.DataFrame(columns=["currency_code", "txn_date", "rate_micros"])
    else:
        lookup = rates.rename(columns={"rate_date": "txn_date", "rate_to_mxn_micros": "rate_micros"})[
            ["currency_code", "txn_date", "rate_micros"]
        ]
        lookup["txn_date"] = lookup["txn_date"].astype("datetime64[us]")
    merged = typed.merge(lookup, on=["currency_code", "txn_date"], how="left")
    merged.index = typed.index
    merged["rate_micros"] = merged["rate_micros"].astype("Int64")
    merged.loc[merged["currency_code"] == "MXN", "rate_micros"] = MICROS
    return merged


def _finalize(contract: EntityContract, df: pd.DataFrame, ctx: TransformContext) -> pd.DataFrame:
    """Enrich accepted records and attach lineage metadata."""
    if contract.name == "transactions":
        df["amount_mxn_minor"] = convert_minor(df["amount_minor"], df["rate_micros"])
        df["is_late_arriving"] = (df["event_ts"] < ctx.window_start).astype("boolean")
        df = flag_transactions(df, ctx.risk)
    if contract.name == "customers":
        hashed = pd.util.hash_pandas_object(df[list(SCD2_ATTRIBUTES)].fillna(""), index=False)
        df["attributes_hash"] = hashed.astype("uint64").astype("string")
    df["batch_id"] = pd.Series(ctx.batch_id, index=df.index, dtype="string")
    df["source_system"] = pd.Series(ctx.source_system, index=df.index, dtype="string")
    df["ingested_at"] = pd.Timestamp(ctx.ingested_at).as_unit("us")
    return df.reset_index(drop=True)


def _quarantine(
    contract: EntityContract,
    records: list[dict[str, Any]],
    typed: pd.DataFrame,
    reasons: list[list[str]],
    rejected: pd.Series,
    duplicate: pd.Series,
    ctx: TransformContext,
) -> pd.DataFrame:
    """Rejected and duplicate records, with the original payload preserved."""
    mask = (rejected | duplicate).to_numpy()
    positions = np.flatnonzero(mask)
    return pd.DataFrame(
        {
            "batch_id": pd.Series([ctx.batch_id] * len(positions), dtype="string"),
            "entity": pd.Series([contract.name] * len(positions), dtype="string"),
            "record_position": pd.Series(positions, dtype="Int64"),
            "natural_key": typed[contract.natural_key].iloc[positions].astype("string").reset_index(drop=True)
            if contract.natural_key in typed
            else pd.Series([None] * len(positions), dtype="string"),
            "disposition": pd.Series(
                ["duplicate" if duplicate.iloc[p] else "rejected" for p in positions], dtype="string"
            ),
            "reasons": pd.Series(
                ["duplicate" if duplicate.iloc[p] else "|".join(reasons[p]) for p in positions],
                dtype="string",
            ),
            "raw_record": pd.Series(
                [json.dumps(records[p], ensure_ascii=False, sort_keys=True) for p in positions],
                dtype="string",
            ),
        }
    )
