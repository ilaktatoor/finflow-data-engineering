"""Source data contracts and their Pandera schemas.

A contract describes what each operational system promises to send: the fields,
which are required, how to parse them, the allowed domain values and which
other entities they reference. ``docs/data-contracts/source-contracts.md`` is
the human-readable version of this module; keep them in sync.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd
import pandera.pandas as pa

CURRENCIES = ("MXN", "USD", "EUR", "CAD")
TRANSACTION_TYPES = ("PURCHASE", "TRANSFER", "WITHDRAWAL", "DEPOSIT", "FEE")
TRANSACTION_STATUSES = ("COMPLETED", "FAILED", "PENDING", "REVERSED")
CHANNELS = ("CARD_POS", "ONLINE", "ATM", "BRANCH", "MOBILE", "SYSTEM")


@dataclass(frozen=True)
class EntityContract:
    name: str
    natural_key: str
    required: tuple[str, ...]
    optional: tuple[str, ...] = ()
    timestamps: tuple[str, ...] = ()
    dates: tuple[str, ...] = ()
    amounts: tuple[str, ...] = ()  # parsed to integer minor units -> "<col>_minor"
    rates: tuple[str, ...] = ()  # parsed to integer micros -> "<col>_micros"
    integers: tuple[str, ...] = ()
    uppercase: tuple[str, ...] = ()
    allowed: dict[str, tuple[str, ...]] = field(default_factory=dict)
    patterns: dict[str, str] = field(default_factory=dict)
    # column -> referenced entity (always by that entity's natural key)
    references: dict[str, str] = field(default_factory=dict)
    # Column holding "last changed" time; drives watermarks and freshness.
    watermark: str = "updated_at"
    # File source system in lightweight mode / source system in data mode.
    file_system: str = "files"
    data_system: str = "files"

    @property
    def columns(self) -> tuple[str, ...]:
        return self.required + self.optional


CONTRACTS: dict[str, EntityContract] = {
    "exchange_rates": EntityContract(
        name="exchange_rates",
        natural_key="rate_key",
        required=("rate_date", "currency_code", "rate_to_mxn"),
        dates=("rate_date",),
        rates=("rate_to_mxn",),
        uppercase=("currency_code",),
        allowed={"currency_code": CURRENCIES[1:]},
        watermark="rate_date",
        file_system="treasury_files",
        data_system="rates_api",
    ),
    "merchants": EntityContract(
        name="merchants",
        natural_key="merchant_id",
        required=("merchant_id", "merchant_name", "category", "updated_at"),
        optional=("city",),
        timestamps=("updated_at",),
        uppercase=("category",),
        patterns={"merchant_id": r"M\d{4}"},
        file_system="merchant_files",
        data_system="merchant_api",
    ),
    "customers": EntityContract(
        name="customers",
        natural_key="customer_id",
        required=("customer_id", "first_name", "last_name", "segment", "created_at", "updated_at"),
        optional=("email", "city", "state"),
        timestamps=("created_at", "updated_at"),
        uppercase=("segment",),
        allowed={"segment": ("RETAIL", "PREMIUM", "SMB")},
        patterns={"customer_id": r"C\d{5}"},
        file_system="core_banking_files",
        data_system="core_banking_db",
    ),
    "accounts": EntityContract(
        name="accounts",
        natural_key="account_id",
        required=(
            "account_id",
            "customer_id",
            "account_type",
            "currency_code",
            "status",
            "opened_at",
            "updated_at",
        ),
        timestamps=("opened_at", "updated_at"),
        uppercase=("account_type", "currency_code", "status"),
        allowed={
            "account_type": ("CHECKING", "SAVINGS"),
            "currency_code": CURRENCIES,
            "status": ("ACTIVE", "CLOSED", "FROZEN"),
        },
        patterns={"account_id": r"A\d{6}"},
        references={"customer_id": "customers"},
        file_system="core_banking_files",
        data_system="core_banking_db",
    ),
    "cards": EntityContract(
        name="cards",
        natural_key="card_id",
        required=("card_id", "account_id", "network", "credit_limit", "status", "issued_at", "updated_at"),
        optional=("card_last4",),
        timestamps=("issued_at", "updated_at"),
        amounts=("credit_limit",),
        uppercase=("network", "status"),
        allowed={"network": ("VISA", "MASTERCARD"), "status": ("ACTIVE", "BLOCKED", "CANCELLED")},
        patterns={"card_id": r"K\d{6}", "card_last4": r"\d{4}"},
        references={"account_id": "accounts"},
        file_system="card_files",
        data_system="card_files",
    ),
    "loans": EntityContract(
        name="loans",
        natural_key="loan_id",
        required=(
            "loan_id",
            "customer_id",
            "account_id",
            "principal",
            "annual_rate",
            "term_months",
            "currency_code",
            "status",
            "disbursed_at",
            "updated_at",
        ),
        timestamps=("disbursed_at", "updated_at"),
        amounts=("principal",),
        rates=("annual_rate",),
        integers=("term_months",),
        uppercase=("currency_code", "status"),
        allowed={"currency_code": CURRENCIES, "status": ("ACTIVE", "PAID_OFF", "DEFAULT")},
        references={"customer_id": "customers", "account_id": "accounts"},
        file_system="lending_files",
        data_system="lending_db",
    ),
    "loan_payments": EntityContract(
        name="loan_payments",
        natural_key="payment_id",
        required=(
            "payment_id",
            "loan_id",
            "installment_number",
            "due_date",
            "amount",
            "principal_component",
            "interest_component",
            "status",
            "updated_at",
        ),
        optional=("paid_at",),
        timestamps=("paid_at", "updated_at"),
        dates=("due_date",),
        amounts=("amount", "principal_component", "interest_component"),
        integers=("installment_number",),
        uppercase=("status",),
        allowed={"status": ("ON_TIME", "LATE", "MISSED")},
        references={"loan_id": "loans"},
        file_system="lending_files",
        data_system="lending_db",
    ),
    "transactions": EntityContract(
        name="transactions",
        natural_key="transaction_id",
        required=(
            "transaction_id",
            "account_id",
            "customer_id",
            "transaction_type",
            "amount",
            "currency_code",
            "status",
            "channel",
            "event_ts",
        ),
        optional=("card_id", "merchant_id", "counterparty_account_id"),
        timestamps=("event_ts",),
        amounts=("amount",),
        uppercase=("transaction_type", "currency_code", "status", "channel"),
        allowed={
            "transaction_type": TRANSACTION_TYPES,
            "currency_code": CURRENCIES,
            "status": TRANSACTION_STATUSES,
            "channel": CHANNELS,
        },
        patterns={"transaction_id": r"T[0-9A-Z]{9,12}"},
        references={
            "account_id": "accounts",
            "customer_id": "customers",
            "merchant_id": "merchants",
            "card_id": "cards",
        },
        watermark="event_ts",
        file_system="transaction_files",
        data_system="transaction_files",
    ),
}

# Dimensions before facts, so referential checks can see this batch's new keys.
PROCESSING_ORDER = (
    "exchange_rates",
    "merchants",
    "customers",
    "accounts",
    "cards",
    "loans",
    "loan_payments",
    "transactions",
)


def _typed_column(contract: EntityContract, column: str) -> str:
    if column in contract.amounts:
        return f"{column}_minor"
    if column in contract.rates:
        return f"{column}_micros"
    return column


def _business_checks(name: str) -> list[pa.Check]:
    """Cross-field business rules. The check name becomes the rejection reason."""
    if name == "transactions":
        return [
            pa.Check(
                lambda df: (df["transaction_type"] != "TRANSFER") | df["counterparty_account_id"].notna(),
                name="transfer_requires_counterparty",
                ignore_na=False,
            ),
            pa.Check(
                lambda df: (df["transaction_type"] != "PURCHASE") | df["merchant_id"].notna(),
                name="purchase_requires_merchant",
                ignore_na=False,
            ),
        ]
    if name == "loan_payments":
        return [
            pa.Check(
                lambda df: (
                    df["principal_component_minor"] + df["interest_component_minor"] == df["amount_minor"]
                ),
                name="payment_components_reconcile",
                ignore_na=False,
            ),
            pa.Check(
                lambda df: (df["status"] == "MISSED") | df["paid_at"].notna(),
                name="paid_installment_requires_paid_at",
                ignore_na=False,
            ),
        ]
    return []


def pandera_schema(contract: EntityContract) -> pa.DataFrameSchema:
    """Domain and business rules, applied after parsing to typed columns.

    Nullability of *required* fields is checked here too; parse failures are
    reported separately (``invalid_format:<col>``) because a null produced by a
    failed parse means something different from a field the producer omitted.
    """
    columns: dict[str, pa.Column] = {}
    for column in contract.columns:
        checks: list[pa.Check] = []
        if column in contract.allowed:
            checks.append(pa.Check.isin(contract.allowed[column]))
        if column in contract.patterns:
            checks.append(pa.Check.str_matches(f"^{contract.patterns[column]}$"))
        if column in contract.amounts:
            # Transactions must move money; components and limits may be zero.
            checks.append(pa.Check.gt(0) if contract.name == "transactions" else pa.Check.ge(0))
        if column in contract.rates:
            checks.append(pa.Check.gt(0))
        if column in contract.integers:
            checks.append(pa.Check.gt(0))
        columns[_typed_column(contract, column)] = pa.Column(
            nullable=column not in contract.required, checks=checks
        )
    return pa.DataFrameSchema(columns, checks=_business_checks(contract.name), strict=False, coerce=False)


def empty_typed_frame(contract: EntityContract) -> pd.DataFrame:
    return pd.DataFrame(columns=[_typed_column(contract, c) for c in contract.columns])
