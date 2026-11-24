"""Deterministic synthetic data for a fictional bank.

Everything is derived from ``(seed, profile)``: running the generator twice
produces byte-identical files. The output imitates exports of independent
operational systems and lands in ``data/landing/<batch_id>/``:

* ``b000-historical`` — reference data plus ``history_days`` of transactions.
* ``bNNN-YYYY-MM-DD`` — one incremental day: new transactions, late-arriving
  transactions, status corrections, customer changes (SCD2), exchange rates and
  loan payments.

A configurable share of transaction records is corrupted on purpose. Every
corruption is counted in ``_generation_report.json`` so tests can assert the
pipeline's exact behaviour instead of approximations.
"""

from __future__ import annotations

import csv
import io
import json
import math
import random
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from faker import Faker

from finflow.common.config import GenerationConfig, ProfileSize

Record = dict[str, Any]

FOREIGN_CURRENCIES = ("USD", "EUR", "CAD")
BASE_RATES = {"USD": Decimal("17.20"), "EUR": Decimal("18.60"), "CAD": Decimal("12.60")}
SEGMENTS = ("RETAIL", "PREMIUM", "SMB")
ACCOUNT_TYPES = ("CHECKING", "SAVINGS")
MERCHANT_CATEGORIES = (
    "GROCERIES",
    "RESTAURANTS",
    "TRAVEL",
    "ELECTRONICS",
    "FUEL",
    "HEALTH",
    "ENTERTAINMENT",
    "UTILITIES",
)
STATUSES = ("COMPLETED", "FAILED", "PENDING", "REVERSED")
STATUS_WEIGHTS = (0.90, 0.06, 0.02, 0.02)
# (median amount in major units, lognormal sigma, channels)
TYPE_PROFILE: dict[str, tuple[float, float, tuple[str, ...]]] = {
    "PURCHASE": (450.0, 0.9, ("CARD_POS", "ONLINE")),
    "TRANSFER": (3000.0, 1.0, ("MOBILE", "ONLINE", "BRANCH")),
    "WITHDRAWAL": (1500.0, 0.6, ("ATM",)),
    "DEPOSIT": (8000.0, 0.8, ("BRANCH", "ATM", "MOBILE")),
    "FEE": (35.0, 0.3, ("SYSTEM",)),
}
NON_CARD_TYPES = ("TRANSFER", "WITHDRAWAL", "DEPOSIT", "FEE")

# The order defines how injected errors are spread evenly across types.
ERROR_TYPES = (
    "duplicate",
    "missing_required",
    "invalid_currency",
    "invalid_timestamp",
    "malformed_amount",
    "unknown_customer",
    "unknown_account",
    "invalid_status",
    "owner_mismatch",
    "schema_mismatch",
)

HISTORICAL_BATCH_ID = "b000-historical"


def iso(ts: datetime) -> str:
    return ts.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def money(cents: int) -> str:
    return f"{cents // 100}.{cents % 100:02d}"


@dataclass
class Batch:
    """One landing batch: what a set of operational systems exported for a window."""

    batch_id: str
    sequence: int
    batch_type: str
    business_date: date
    window_start: datetime
    window_end: datetime
    entities: dict[str, list[Record]] = field(default_factory=dict)
    report: dict[str, Any] = field(default_factory=dict)

    def manifest(self, profile: str, seed: int) -> dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "sequence": self.sequence,
            "batch_type": self.batch_type,
            "business_date": self.business_date.isoformat(),
            "window_start": iso(self.window_start),
            "window_end": iso(self.window_end),
            "profile": profile,
            "seed": seed,
            "entities": sorted(self.entities),
        }


@dataclass
class Universe:
    """Clean reference data plus the clean historical transactions."""

    customers: list[Record]
    accounts: list[Record]
    cards: list[Record]
    merchants: list[Record]
    loans: list[Record]
    loan_payments: list[Record]
    transactions: list[Record]


class SyntheticGenerator:
    def __init__(self, config: GenerationConfig, profile: str = "small") -> None:
        if profile not in config.profiles:
            raise ValueError(f"Unknown profile '{profile}'. Options: {sorted(config.profiles)}")
        self.config = config
        self.profile = profile
        self.size: ProfileSize = config.profiles[profile]
        self.start = datetime.combine(config.start_date, time.min, UTC)
        self.history_end = self.start + timedelta(days=config.history_days)

    # ------------------------------------------------------------------ helpers
    def _rng(self, *scope: object) -> random.Random:
        # String seeds are hashed deterministically by `random`, unlike hash().
        return random.Random(f"{self.config.seed}|{self.profile}|" + "|".join(map(str, scope)))

    def _faker(self, *scope: object) -> Faker:
        fake = Faker("es_MX")
        fake.seed_instance(f"{self.config.seed}|{self.profile}|" + "|".join(map(str, scope)))
        return fake

    def _amount_cents(self, rng: random.Random, txn_type: str) -> int:
        median, sigma, _ = TYPE_PROFILE[txn_type]
        value = rng.lognormvariate(math.log(median), sigma)
        if txn_type == "WITHDRAWAL":
            value = max(100.0, round(value / 100) * 100)
        return max(100, int(value * 100))

    def rate_for(self, day: date, currency: str) -> Decimal:
        rng = self._rng("rate", day.isoformat(), currency)
        drift = Decimal(str(round(math.sin(day.toordinal() / 7) * 0.015, 6)))
        noise = Decimal(str(round(rng.uniform(-0.004, 0.004), 6)))
        return (BASE_RATES[currency] * (1 + drift + noise)).quantize(Decimal("0.000001"))

    def _rates(self, days: list[date]) -> list[Record]:
        return [
            {"rate_date": d.isoformat(), "currency_code": c, "rate_to_mxn": str(self.rate_for(d, c))}
            for d in days
            for c in FOREIGN_CURRENCIES
        ]

    # ----------------------------------------------------------------- universe
    def build_universe(self) -> Universe:
        rng = self._rng("universe")
        fake = self._faker("universe")
        size = self.size

        customers: list[Record] = []
        for i in range(1, size.customers + 1):
            created = self.start - timedelta(days=rng.randint(60, 5 * 365), seconds=rng.randint(0, 86_399))
            customers.append(
                {
                    "customer_id": f"C{i:05d}",
                    "first_name": fake.first_name(),
                    "last_name": fake.last_name(),
                    "email": f"customer{i:05d}@example.test",
                    "city": fake.city(),
                    "state": fake.state(),
                    "segment": rng.choices(SEGMENTS, weights=(0.75, 0.15, 0.10))[0],
                    "created_at": iso(created),
                    "updated_at": iso(created),
                }
            )

        accounts: list[Record] = []
        for i in range(1, size.accounts + 1):
            # Every customer gets one account first; the rest are spread randomly.
            owner = customers[i - 1] if i <= len(customers) else rng.choice(customers)
            opened = datetime.fromisoformat(owner["created_at"]) + timedelta(days=rng.randint(0, 30))
            accounts.append(
                {
                    "account_id": f"A{i:06d}",
                    "customer_id": owner["customer_id"],
                    "account_type": rng.choices(ACCOUNT_TYPES, weights=(0.7, 0.3))[0],
                    "currency_code": "USD" if rng.random() < 0.1 else "MXN",
                    "status": "ACTIVE",
                    "opened_at": iso(opened),
                    "updated_at": iso(opened),
                }
            )

        cards: list[Record] = []
        for i, account in enumerate(rng.sample(accounts, k=min(size.cards, len(accounts))), start=1):
            issued = datetime.fromisoformat(account["opened_at"]) + timedelta(days=rng.randint(1, 20))
            cards.append(
                {
                    "card_id": f"K{i:06d}",
                    "account_id": account["account_id"],
                    "network": rng.choice(("VISA", "MASTERCARD")),
                    "card_last4": f"{rng.randint(0, 9999):04d}",  # never a full card number
                    "credit_limit": money(rng.choice((10_000, 25_000, 50_000, 100_000)) * 100),
                    "status": "ACTIVE",
                    "issued_at": iso(issued),
                    "updated_at": iso(issued),
                }
            )

        merchants: list[Record] = []
        for i in range(1, size.merchants + 1):
            merchants.append(
                {
                    "merchant_id": f"M{i:04d}",
                    "merchant_name": f"{fake.company()} {i}",
                    "category": MERCHANT_CATEGORIES[(i - 1) % len(MERCHANT_CATEGORIES)],
                    "city": fake.city(),
                    "updated_at": iso(self.start - timedelta(days=rng.randint(30, 400))),
                }
            )

        loans, loan_payments = self._loans(rng, customers, accounts)
        transactions = self._transactions(
            self._rng("historical-transactions"),
            accounts,
            cards,
            merchants,
            count=size.transactions,
            window_start=self.start,
            window_end=self.history_end,
            id_prefix="T000",
        )
        return Universe(customers, accounts, cards, merchants, loans, loan_payments, transactions)

    def _loans(
        self, rng: random.Random, customers: list[Record], accounts: list[Record]
    ) -> tuple[list[Record], list[Record]]:
        mxn_accounts = [a for a in accounts if a["currency_code"] == "MXN"]
        payments_per_loan = max(1, self.size.loan_payments // max(1, self.size.loans))
        loans: list[Record] = []
        payments: list[Record] = []
        for i in range(1, self.size.loans + 1):
            account = rng.choice(mxn_accounts)
            principal_cents = rng.randint(20_000, 500_000) * 100
            annual_rate = Decimal(rng.randint(1200, 4500)) / Decimal(10_000)
            term = rng.choice((12, 24, 36))
            # Disbursed so that the last historical installment is due inside the window.
            disbursed = self.start - timedelta(days=30 * payments_per_loan + rng.randint(0, 25))
            loan_id = f"L{i:05d}"
            loans.append(
                {
                    "loan_id": loan_id,
                    "customer_id": account["customer_id"],
                    "account_id": account["account_id"],
                    "principal": money(principal_cents),
                    "annual_rate": f"{annual_rate:.4f}",
                    "term_months": str(term),
                    "currency_code": "MXN",
                    "status": "ACTIVE",
                    "disbursed_at": iso(disbursed),
                    "updated_at": iso(disbursed),
                }
            )
            for n in range(1, payments_per_loan + 1):
                payments.append(self._payment(loan_id, n, principal_cents, annual_rate, term, disbursed, rng))
        return loans, payments

    def _payment(
        self,
        loan_id: str,
        installment: int,
        principal_cents: int,
        annual_rate: Decimal,
        term: int,
        disbursed: datetime,
        rng: random.Random,
    ) -> Record:
        monthly = annual_rate / 12
        # Standard annuity installment, computed in Decimal and rounded to cents.
        factor = (1 + monthly) ** term
        installment_cents = int((principal_cents * monthly * factor / (factor - 1)).quantize(Decimal("1")))
        interest_cents = int((principal_cents * monthly).quantize(Decimal("1")))
        principal_part = installment_cents - interest_cents
        due = disbursed + timedelta(days=30 * installment)
        status = rng.choices(("ON_TIME", "LATE", "MISSED"), weights=(0.80, 0.15, 0.05))[0]
        if status == "MISSED":
            paid_at, amount, principal_part, interest_cents = None, 0, 0, 0
        else:
            delay = 0 if status == "ON_TIME" else rng.randint(3, 20)
            paid_at = due + timedelta(days=delay, hours=rng.randint(8, 18))
            amount = installment_cents
        updated = paid_at or due
        return {
            "payment_id": f"P{loan_id[1:]}{installment:03d}",
            "loan_id": loan_id,
            "installment_number": str(installment),
            "due_date": due.date().isoformat(),
            "paid_at": iso(paid_at) if paid_at else "",
            "amount": money(amount),
            "principal_component": money(principal_part),
            "interest_component": money(interest_cents),
            "status": status,
            "updated_at": iso(updated),
        }

    def _transactions(
        self,
        rng: random.Random,
        accounts: list[Record],
        cards: list[Record],
        merchants: list[Record],
        *,
        count: int,
        window_start: datetime,
        window_end: datetime,
        id_prefix: str,
    ) -> list[Record]:
        card_by_account = {c["account_id"]: c["card_id"] for c in cards}
        span = int((window_end - window_start).total_seconds()) - 1
        records: list[Record] = []
        bursts = max(1, count // 400)  # bursts feed the simulated velocity rule
        for i in range(1, count + 1):
            account = rng.choice(accounts)
            card_id = card_by_account.get(account["account_id"])
            if card_id and rng.random() < 0.65:
                txn_type = "PURCHASE"
            else:
                txn_type = rng.choices(NON_CARD_TYPES, weights=(0.45, 0.2, 0.25, 0.1))[0]
            ts = window_start + timedelta(seconds=rng.randint(0, span))
            # A few accounts make several transactions within minutes.
            if i <= bursts * 4 and i > 1 and (i - 1) % 4 != 0:
                previous = records[-1]
                account = next(a for a in accounts if a["account_id"] == previous["account_id"])
                card_id = previous["card_id"] or card_by_account.get(account["account_id"])
                txn_type = previous["transaction_type"]
                ts = datetime.fromisoformat(previous["event_ts"]) + timedelta(seconds=rng.randint(30, 150))
            # Amounts are drawn in pesos, then expressed in the transaction currency.
            currency = account["currency_code"]
            cents = self._amount_cents(rng, txn_type)
            if txn_type == "PURCHASE" and currency == "MXN" and rng.random() < 0.10:
                currency = rng.choice(FOREIGN_CURRENCIES)  # a purchase abroad
            if txn_type == "PURCHASE" and rng.random() < 0.01:
                cents = rng.randint(60_000, 150_000) * 100  # feeds the high-amount rule
            if currency != "MXN":
                cents = max(100, int(cents / float(BASE_RATES[currency])))
            counterparty = rng.choice(accounts)["account_id"] if txn_type == "TRANSFER" else None
            records.append(
                {
                    "transaction_id": f"{id_prefix}{i:06d}",
                    "account_id": account["account_id"],
                    "customer_id": account["customer_id"],
                    "card_id": card_id if txn_type == "PURCHASE" else None,
                    "merchant_id": rng.choice(merchants)["merchant_id"] if txn_type == "PURCHASE" else None,
                    "counterparty_account_id": counterparty,
                    "transaction_type": txn_type,
                    "amount": money(cents),
                    "currency_code": currency,
                    "status": rng.choices(STATUSES, weights=STATUS_WEIGHTS)[0],
                    "channel": rng.choice(TYPE_PROFILE[txn_type][2]),
                    "event_ts": iso(min(ts, window_end - timedelta(seconds=1))),
                }
            )
        return records

    # ------------------------------------------------------------------ errors
    def inject_errors(
        self, records: list[Record], rng: random.Random, protected: set[str] | None = None
    ) -> tuple[list[Record], dict[str, int]]:
        """Corrupt ``error_rate`` of the records, spreading evenly over ERROR_TYPES.

        Returns the new record list and how many records of each type were injected.
        ``protected`` transaction ids are never corrupted (e.g. status corrections).
        """
        protected = protected or set()
        total = round(len(records) * self.config.error_rate)
        counts = dict.fromkeys(ERROR_TYPES, 0)
        if total == 0:
            return records, counts
        candidates = [i for i, r in enumerate(records) if r["transaction_id"] not in protected]
        targets = rng.sample(candidates, k=min(total, len(candidates)))
        out = [dict(r) for r in records]
        duplicates: list[Record] = []
        other_customers = sorted({r["customer_id"] for r in records})
        for n, idx in enumerate(targets):
            kind = ERROR_TYPES[n % len(ERROR_TYPES)]
            record = out[idx]
            counts[kind] += 1
            if kind == "duplicate":
                duplicates.append(dict(record))  # an exact re-send of a valid record
            elif kind == "missing_required":
                record["account_id"] = None
            elif kind == "invalid_currency":
                record["currency_code"] = rng.choice(("XYZ", "PESO", "usd$"))
            elif kind == "invalid_timestamp":
                record["event_ts"] = rng.choice(("2026-13-45T25:61:00Z", "not-a-date", "31/01/2026 10:00"))
            elif kind == "malformed_amount":
                record["amount"] = rng.choice(("12,34.5x", "-", "1.2.3", "$100"))
            elif kind == "unknown_customer":
                record["customer_id"] = "C99999"
            elif kind == "unknown_account":
                record["account_id"] = "A999999"
            elif kind == "invalid_status":
                record["status"] = rng.choice(("DONE", "UNKNOWN", "completed!"))
            elif kind == "owner_mismatch":
                record["customer_id"] = next(c for c in other_customers if c != record["customer_id"])
            elif kind == "schema_mismatch":
                record["txn_amount"] = record.pop("amount")  # renamed field from a buggy producer
        # Targets are distinct, so a duplicated record is never corrupted itself.
        positions = sorted(rng.sample(range(len(out) + len(duplicates)), k=len(duplicates)))
        for pos, dup in zip(positions, duplicates, strict=True):
            out.insert(pos, dup)
        return out, counts

    # ----------------------------------------------------------------- batches
    def historical_batch(self) -> Batch:
        universe = self.build_universe()
        transactions, injected = self.inject_errors(universe.transactions, self._rng("errors", 0))
        days = [self.config.start_date + timedelta(days=d) for d in range(self.config.history_days)]
        batch = Batch(
            batch_id=HISTORICAL_BATCH_ID,
            sequence=0,
            batch_type="historical",
            business_date=days[-1],
            window_start=self.start,
            window_end=self.history_end,
            entities={
                "customers": universe.customers,
                "accounts": universe.accounts,
                "cards": universe.cards,
                "merchants": universe.merchants,
                "exchange_rates": self._rates(days),
                "loans": universe.loans,
                "loan_payments": universe.loan_payments,
                "transactions": transactions,
            },
        )
        batch.report = self._report(batch, injected, late=0, corrections=0)
        return batch

    def customer_changes(self, sequence: int, customers: list[Record]) -> list[Record]:
        """Deterministic attribute changes for one incremental day (SCD2 input)."""
        rng = self._rng("customer-changes", sequence)
        fake = self._faker("customer-changes", sequence)
        day = self.config.start_date + timedelta(days=self.config.history_days + sequence - 1)
        changes = []
        for customer in rng.sample(customers, k=min(3, len(customers))):
            changed = dict(customer)
            if rng.random() < 0.5:
                changed["segment"] = rng.choice([s for s in SEGMENTS if s != customer["segment"]])
            else:
                changed["city"], changed["state"] = fake.city(), fake.state()
            changed["updated_at"] = iso(datetime.combine(day, time(9, 0), UTC))
            changes.append(changed)
        return changes

    def incremental_batch(self, sequence: int) -> Batch:
        """Build incremental day ``sequence`` (1 = the day after the history window)."""
        if sequence < 1:
            raise ValueError("Incremental batches start at sequence 1.")
        universe = self.build_universe()
        # Replay earlier customer changes so this batch builds on the latest state.
        customers = {c["customer_id"]: c for c in universe.customers}
        for previous in range(1, sequence):
            for change in self.customer_changes(previous, list(customers.values())):
                customers[change["customer_id"]] = change
        changes = self.customer_changes(sequence, list(customers.values()))

        day = self.config.start_date + timedelta(days=self.config.history_days + sequence - 1)
        window_start = datetime.combine(day, time.min, UTC)
        window_end = window_start + timedelta(days=1)
        rng = self._rng("incremental", sequence)
        count = rng.randint(
            self.config.incremental_min_transactions, self.config.incremental_max_transactions
        )
        prefix = f"T{sequence:03d}"
        new = self._transactions(
            rng,
            universe.accounts,
            universe.cards,
            universe.merchants,
            count=count,
            window_start=window_start,
            window_end=window_end,
            id_prefix=prefix,
        )
        # Late-arriving: events from the previous week that only reach us today.
        late_count = rng.randint(3, 5)
        late = self._transactions(
            rng,
            universe.accounts,
            universe.cards,
            universe.merchants,
            count=late_count,
            window_start=window_start - timedelta(days=7),
            window_end=window_start - timedelta(hours=1),
            id_prefix=f"{prefix}L",
        )
        # Status corrections: historical PENDING transactions that have now settled.
        pending = [t for t in universe.transactions if t["status"] == "PENDING"]
        corrections = [dict(t, status="COMPLETED") for t in rng.sample(pending, k=min(2, len(pending)))]
        protected = {t["transaction_id"] for t in corrections}
        transactions, injected = self.inject_errors(
            new + late + corrections, self._rng("errors", sequence), protected
        )

        payments_per_loan = max(1, self.size.loan_payments // max(1, self.size.loans))
        installment = payments_per_loan + sequence
        loan_payments = []
        for loan in rng.sample(universe.loans, k=min(5, len(universe.loans))):
            principal_cents = int(Decimal(loan["principal"]) * 100)
            disbursed = datetime.fromisoformat(loan["disbursed_at"])
            payment = self._payment(
                loan["loan_id"],
                installment,
                principal_cents,
                Decimal(loan["annual_rate"]),
                int(loan["term_months"]),
                disbursed,
                rng,
            )
            # The installment is reported on the business day it was received.
            payment["due_date"] = day.isoformat()
            payment["paid_at"] = (
                iso(datetime.combine(day, time(12, 0), UTC)) if payment["status"] != "MISSED" else ""
            )
            payment["status"] = "MISSED" if payment["status"] == "MISSED" else "ON_TIME"
            payment["updated_at"] = iso(datetime.combine(day, time(12, 0), UTC))
            loan_payments.append(payment)

        batch = Batch(
            batch_id=f"b{sequence:03d}-{day.isoformat()}",
            sequence=sequence,
            batch_type="incremental",
            business_date=day,
            window_start=window_start,
            window_end=window_end,
            entities={
                "customers": changes,
                "exchange_rates": self._rates([day]),
                "loan_payments": loan_payments,
                "transactions": transactions,
            },
        )
        batch.report = self._report(batch, injected, late=late_count, corrections=len(corrections))
        return batch

    def _report(
        self, batch: Batch, injected: dict[str, int], *, late: int, corrections: int
    ) -> dict[str, Any]:
        rejected = sum(v for k, v in injected.items() if k != "duplicate")
        return {
            "batch_id": batch.batch_id,
            "record_counts": {name: len(rows) for name, rows in batch.entities.items()},
            "injected_errors": injected,
            "expected": {
                "transactions_rejected": rejected,
                "transactions_duplicates": injected["duplicate"],
                "transactions_accepted": len(batch.entities["transactions"])
                - rejected
                - injected["duplicate"],
                "late_arriving": late,
                "status_corrections": corrections,
            },
        }


# ---------------------------------------------------------------- file output
FILE_FORMATS = {
    "customers": "csv",
    "accounts": "csv",
    "cards": "csv",
    "loans": "csv",
    "loan_payments": "csv",
    "exchange_rates": "csv",
    "merchants": "json",
    "transactions": "jsonl",
}


def serialize(entity: str, records: list[Record]) -> bytes:
    """Serialize records exactly as the simulated source system would export them."""
    fmt = FILE_FORMATS[entity]
    if fmt == "csv":
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=list(records[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)
        return buffer.getvalue().encode("utf-8")
    if fmt == "json":
        return json.dumps(records, indent=1, ensure_ascii=False).encode("utf-8")
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records).encode("utf-8")


def write_batch(batch: Batch, landing_dir: Path, profile: str, seed: int) -> Path:
    target = landing_dir / batch.batch_id
    target.mkdir(parents=True, exist_ok=True)
    for entity, records in batch.entities.items():
        if records:
            (target / f"{entity}.{FILE_FORMATS[entity]}").write_bytes(serialize(entity, records))
    (target / "_batch.json").write_text(json.dumps(batch.manifest(profile, seed), indent=2) + "\n")
    (target / "_generation_report.json").write_text(json.dumps(batch.report, indent=2) + "\n")
    return target


def next_incremental_sequence(landing_dir: Path) -> int:
    existing = [json.loads(p.read_text())["sequence"] for p in landing_dir.glob("*/_batch.json")]
    if 0 not in existing:
        raise FileNotFoundError("Generate the historical batch first (finflow generate).")
    return max(existing) + 1
