"""Strict adapters for the documented V1 synthetic/import CSV contracts."""

from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from recon.domain.models import (
    BankTransaction,
    LedgerType,
    MerchantOrder,
    Money,
    Payment,
    PaymentStatus,
    Refund,
    Settlement,
    SettlementLedgerLine,
    SettlementStatus,
)
from recon.synthetic.generator import GeneratedDataset, GeneratorConfig, GroundTruth


@dataclass(frozen=True, slots=True)
class ImportIssue:
    source: str
    row_number: int
    code: str
    message: str
    payload_hash: str


@dataclass(slots=True)
class ImportResult:
    records: list[object]
    issues: list[ImportIssue]
    duplicate_count: int
    file_hash: str


def _parse_datetime(value: str, *, required: bool = True) -> datetime | None:
    if not value.strip() and not required:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include an explicit timezone")
    return parsed


def _parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized not in {"true", "false"}:
        raise ValueError("boolean must be true or false")
    return normalized == "true"


def _fingerprint(payload: dict[str, str]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _read[T](path: Path, parser: Callable[[dict[str, str]], T]) -> ImportResult:
    raw = path.read_bytes()
    result = ImportResult([], [], 0, hashlib.sha256(raw).hexdigest())
    seen: set[str] = set()
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"{path.name} has no header")
        for row_number, row in enumerate(reader, 2):
            payload = {str(key): value or "" for key, value in row.items() if key is not None}
            fingerprint = _fingerprint(payload)
            if fingerprint in seen:
                result.duplicate_count += 1
                continue
            seen.add(fingerprint)
            try:
                result.records.append(parser(payload))
            except (KeyError, ValueError, TypeError) as exc:
                result.issues.append(
                    ImportIssue(path.name, row_number, "MALFORMED_RECORD", str(exc), fingerprint)
                )
    return result


def _order(row: dict[str, str]) -> MerchantOrder:
    return MerchantOrder(
        row["order_id"],
        Money(int(row["amount_minor"]), row["currency"]),
        row["status"],
        _parse_datetime(row["created_at"]),  # type: ignore[arg-type]
        row["merchant_reference"],
    )


def _payment(row: dict[str, str]) -> Payment:
    return Payment(
        row["payment_id"],
        row["order_id"] or None,
        Money(int(row["amount_minor"]), row["currency"]),
        PaymentStatus(row["status"]),
        _parse_datetime(row["captured_at"], required=False),
        row["method"],
        int(row["fee_minor"]),
        int(row["tax_minor"]),
    )


def _refund(row: dict[str, str]) -> Refund:
    return Refund(
        row["refund_id"],
        row["payment_id"],
        Money(int(row["amount_minor"]), row["currency"]),
        row["status"],
        _parse_datetime(row["created_at"]),  # type: ignore[arg-type]
    )


def _settlement(row: dict[str, str]) -> Settlement:
    return Settlement(
        row["settlement_id"],
        Money(int(row["amount_minor"]), row["currency"]),
        SettlementStatus(row["status"]),
        row["utr"] or None,
        _parse_datetime(row["created_at"]),  # type: ignore[arg-type]
        _parse_datetime(row["processed_at"], required=False),
        int(row["source_fees_minor"]),
        int(row["source_tax_minor"]),
    )


def _ledger(row: dict[str, str]) -> SettlementLedgerLine:
    return SettlementLedgerLine(
        row["line_id"],
        row["settlement_id"],
        row["entity_id"],
        LedgerType(row["type"]),
        row["currency"],
        int(row["credit"]),
        int(row["debit"]),
        int(row["fee"]),
        int(row["tax"]),
        _parse_bool(row["settled"]),
        _parse_bool(row["on_hold"]),
        _parse_datetime(row["created_at"]),  # type: ignore[arg-type]
        _parse_datetime(row["settled_at"], required=False),
        row["payment_id"] or None,
    )


def _bank(row: dict[str, str]) -> BankTransaction:
    return BankTransaction(
        row["bank_transaction_id"],
        _parse_datetime(row["booked_at"]),  # type: ignore[arg-type]
        Money(int(row["amount_minor"]), row["currency"]),
        row["direction"],
        row["utr"] or None,
        row["reference"] or None,
    )


def load_exported_dataset(
    directory: Path, *, with_truth: bool = False
) -> tuple[GeneratedDataset, dict[str, ImportResult]]:
    """Load a complete V1 dataset and return row-level import diagnostics."""
    results = {
        "orders": _read(directory / "merchant_orders.csv", _order),
        "payments": _read(directory / "razorpay_payments.csv", _payment),
        "refunds": _read(directory / "razorpay_refunds.csv", _refund),
        "settlements": _read(directory / "razorpay_settlements.csv", _settlement),
        "ledger": _read(directory / "razorpay_settlement_recon.csv", _ledger),
        "bank": _read(directory / "bank_statement.csv", _bank),
    }
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    config = GeneratorConfig(**manifest["config"])
    if with_truth:
        raw_truth = json.loads((directory / ".ground_truth.json").read_text(encoding="utf-8"))
        truth = GroundTruth(**raw_truth)
    else:
        truth = GroundTruth({}, {}, {}, [])
    dataset = GeneratedDataset(
        config,
        list(results["orders"].records),  # type: ignore[arg-type]
        list(results["payments"].records),  # type: ignore[arg-type]
        list(results["refunds"].records),  # type: ignore[arg-type]
        list(results["settlements"].records),  # type: ignore[arg-type]
        list(results["ledger"].records),  # type: ignore[arg-type]
        list(results["bank"].records),  # type: ignore[arg-type]
        truth,
    )
    return dataset, results
