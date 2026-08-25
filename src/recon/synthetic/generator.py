"""Generate a valid financial world, then inject traceable anomalies."""

from __future__ import annotations

import csv
import json
import random
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from recon.domain.models import (
    BankTransaction,
    LedgerType,
    MerchantOrder,
    Money,
    OutcomeStatus,
    Payment,
    PaymentStatus,
    Refund,
    Settlement,
    SettlementLedgerLine,
    SettlementStatus,
)
from recon.domain.money import percentage_minor


@dataclass(frozen=True, slots=True)
class GeneratorConfig:
    seed: int = 20260825
    order_count: int = 500
    payments_per_settlement: int = 10
    currency: str = "INR"
    fee_rate: str = "0.02"
    tax_rate: str = "0.18"
    inject_anomalies: bool = True


@dataclass(frozen=True, slots=True)
class GroundTruth:
    expected_status_by_settlement: dict[str, str]
    expected_bank_by_settlement: dict[str, str | None]
    anomaly_by_settlement: dict[str, str]
    expected_commercial_exception_codes: list[str]


@dataclass(slots=True)
class GeneratedDataset:
    config: GeneratorConfig
    orders: list[MerchantOrder]
    payments: list[Payment]
    refunds: list[Refund]
    settlements: list[Settlement]
    ledger_lines: list[SettlementLedgerLine]
    bank_transactions: list[BankTransaction]
    truth: GroundTruth

    def export(self, directory: Path, *, include_truth: bool = True) -> dict[str, Path]:
        """Export independent source files and optionally evaluator-only truth."""
        directory.mkdir(parents=True, exist_ok=True)
        paths = {
            "orders": directory / "merchant_orders.csv",
            "payments": directory / "razorpay_payments.csv",
            "refunds": directory / "razorpay_refunds.csv",
            "settlements": directory / "razorpay_settlements.csv",
            "ledger": directory / "razorpay_settlement_recon.csv",
            "bank": directory / "bank_statement.csv",
            "manifest": directory / "manifest.json",
        }
        _write_csv(
            paths["orders"],
            [
                {
                    "order_id": item.order_id,
                    "amount_minor": item.amount.amount_minor,
                    "currency": item.amount.currency,
                    "status": item.status,
                    "created_at": item.created_at.isoformat(),
                    "merchant_reference": item.merchant_reference,
                }
                for item in self.orders
            ],
        )
        _write_csv(
            paths["payments"],
            [
                {
                    "payment_id": item.payment_id,
                    "order_id": item.order_id or "",
                    "amount_minor": item.amount.amount_minor,
                    "currency": item.amount.currency,
                    "status": item.status.value,
                    "captured_at": item.captured_at.isoformat() if item.captured_at else "",
                    "method": item.method,
                    "fee_minor": item.fee_minor,
                    "tax_minor": item.tax_minor,
                }
                for item in self.payments
            ],
        )
        _write_csv(
            paths["refunds"],
            [
                {
                    "refund_id": item.refund_id,
                    "payment_id": item.payment_id,
                    "amount_minor": item.amount.amount_minor,
                    "currency": item.amount.currency,
                    "status": item.status,
                    "created_at": item.created_at.isoformat(),
                }
                for item in self.refunds
            ],
        )
        _write_csv(
            paths["settlements"],
            [
                {
                    "settlement_id": item.settlement_id,
                    "amount_minor": item.amount.amount_minor,
                    "currency": item.amount.currency,
                    "status": item.status.value,
                    "utr": item.utr or "",
                    "created_at": item.created_at.isoformat(),
                    "processed_at": item.processed_at.isoformat() if item.processed_at else "",
                    "source_fees_minor": item.source_fees_minor,
                    "source_tax_minor": item.source_tax_minor,
                }
                for item in self.settlements
            ],
        )
        _write_csv(
            paths["ledger"],
            [
                {
                    "line_id": item.line_id,
                    "settlement_id": item.settlement_id,
                    "entity_id": item.entity_id,
                    "type": item.line_type.value,
                    "currency": item.currency,
                    "credit": item.credit_minor,
                    "debit": item.debit_minor,
                    "fee": item.fee_minor,
                    "tax": item.tax_minor,
                    "settled": str(item.settled).lower(),
                    "on_hold": str(item.on_hold).lower(),
                    "created_at": item.created_at.isoformat(),
                    "settled_at": item.settled_at.isoformat() if item.settled_at else "",
                    "payment_id": item.payment_id or "",
                }
                for item in self.ledger_lines
            ],
        )
        _write_csv(
            paths["bank"],
            [
                {
                    "bank_transaction_id": item.bank_transaction_id,
                    "booked_at": item.booked_at.isoformat(),
                    "amount_minor": item.amount.amount_minor,
                    "currency": item.amount.currency,
                    "direction": item.direction,
                    "utr": item.utr or "",
                    "reference": item.reference or "",
                }
                for item in self.bank_transactions
            ],
        )
        paths["manifest"].write_text(
            json.dumps({"generator_version": "1", "config": asdict(self.config)}, indent=2) + "\n",
            encoding="utf-8",
        )
        if include_truth:
            truth_path = directory / ".ground_truth.json"
            truth_path.write_text(json.dumps(asdict(self.truth), indent=2) + "\n", encoding="utf-8")
            paths["truth"] = truth_path
        return paths


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        empty_headers = {
            "razorpay_refunds.csv": [
                "refund_id",
                "payment_id",
                "amount_minor",
                "currency",
                "status",
                "created_at",
            ],
        }
        headers = empty_headers.get(path.name)
        if headers is None:
            raise ValueError(f"no empty-file contract declared for {path.name}")
        path.write_text(",".join(headers) + "\n", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def generate_dataset(config: GeneratorConfig | None = None) -> GeneratedDataset:
    """Create a realistic, reproducible dataset with explicit mutation truth."""
    config = config or GeneratorConfig()
    rng = random.Random(config.seed)
    fee_rate = Decimal(config.fee_rate)
    tax_rate = Decimal(config.tax_rate)
    origin = datetime(2026, 6, 1, 10, 0, tzinfo=UTC)
    orders: list[MerchantOrder] = []
    payments: list[Payment] = []
    refunds: list[Refund] = []

    for index in range(1, config.order_count + 1):
        created = origin + timedelta(hours=index * 2)
        amount_minor = rng.randrange(50_00, 50_000_00, 100)
        order_id = f"order_SYN{index:06d}"
        captured = index % 19 != 0
        orders.append(
            MerchantOrder(
                order_id,
                Money(amount_minor, config.currency),
                "paid" if captured else "created",
                created,
                f"MERCHANT-{index:06d}",
            )
        )
        payment_id = f"pay_SYN{index:06d}"
        fee = percentage_minor(amount_minor, fee_rate) if captured else 0
        tax = percentage_minor(fee, tax_rate) if captured else 0
        payments.append(
            Payment(
                payment_id,
                order_id,
                Money(amount_minor, config.currency),
                PaymentStatus.CAPTURED if captured else PaymentStatus.FAILED,
                created + timedelta(minutes=2) if captured else None,
                ("upi", "card", "netbanking")[index % 3],
                fee,
                tax,
            )
        )
        if captured and index % 23 == 0:
            refund_amount = amount_minor // (2 if index % 46 else 1)
            refunds.append(
                Refund(
                    f"rfnd_SYN{index:06d}",
                    payment_id,
                    Money(refund_amount, config.currency),
                    "processed",
                    created + timedelta(days=2),
                )
            )

    expected_commercial_codes: list[str] = []
    if config.inject_anomalies and config.order_count >= 160:
        orphan_index = 96
        mismatch_index = 112
        missing_capture_index = 151
        payments[orphan_index] = replace(payments[orphan_index], order_id="order_NOT_IMPORTED")
        expected_commercial_codes.extend(["ORPHAN_PAYMENT", "ORDER_WITHOUT_CAPTURED_PAYMENT"])
        mismatch_payment = payments[mismatch_index]
        payments[mismatch_index] = replace(
            mismatch_payment,
            amount=Money(mismatch_payment.amount.amount_minor + 12_345, config.currency),
        )
        expected_commercial_codes.append("PAYMENT_AMOUNT_MISMATCH")
        orders[missing_capture_index] = replace(orders[missing_capture_index], status="paid")
        expected_commercial_codes.append("ORDER_WITHOUT_CAPTURED_PAYMENT")
        refunds.append(
            Refund(
                "rfnd_ORPHAN",
                "pay_NOT_IMPORTED",
                Money(25_000, config.currency),
                "processed",
                origin + timedelta(days=5),
            )
        )
        expected_commercial_codes.append("ORPHAN_REFUND")

    captured_payments = [item for item in payments if item.status == PaymentStatus.CAPTURED]
    refund_by_payment = {item.payment_id: item for item in refunds}
    settlements: list[Settlement] = []
    ledger_lines: list[SettlementLedgerLine] = []
    bank_transactions: list[BankTransaction] = []
    expected_status: dict[str, str] = {}
    expected_bank: dict[str, str | None] = {}
    anomalies: dict[str, str] = {}

    groups = [
        captured_payments[index : index + config.payments_per_settlement]
        for index in range(0, len(captured_payments), config.payments_per_settlement)
    ]
    for group_index, group in enumerate(groups, 1):
        settlement_id = f"setl_SYN{group_index:04d}"
        processed_at = origin + timedelta(days=group_index, hours=8)
        group_lines: list[SettlementLedgerLine] = []
        for payment in group:
            line = SettlementLedgerLine(
                f"line_PAY_{payment.payment_id}",
                settlement_id,
                payment.payment_id,
                LedgerType.PAYMENT,
                config.currency,
                payment.amount.amount_minor,
                0,
                payment.fee_minor,
                payment.tax_minor,
                True,
                False,
                payment.captured_at or processed_at,
                processed_at,
                payment.payment_id,
            )
            group_lines.append(line)
            refund = refund_by_payment.get(payment.payment_id)
            if refund:
                group_lines.append(
                    SettlementLedgerLine(
                        f"line_REF_{refund.refund_id}",
                        settlement_id,
                        refund.refund_id,
                        LedgerType.REFUND,
                        config.currency,
                        0,
                        refund.amount.amount_minor,
                        0,
                        0,
                        True,
                        False,
                        refund.created_at,
                        processed_at,
                        payment.payment_id,
                    )
                )
        if group_index % 11 == 0:
            adjustment = 10_000 if group_index % 22 else -20_000
            group_lines.append(
                SettlementLedgerLine(
                    f"line_ADJ_{group_index:04d}",
                    settlement_id,
                    f"adj_SYN{group_index:04d}",
                    LedgerType.ADJUSTMENT,
                    config.currency,
                    max(adjustment, 0),
                    max(-adjustment, 0),
                    0,
                    0,
                    True,
                    False,
                    processed_at - timedelta(hours=1),
                    processed_at,
                )
            )
        ledger_lines.extend(group_lines)
        amount_minor = sum(item.net_effect_minor for item in group_lines)
        utr = f"HDFCN{config.seed % 10000:04d}{group_index:08d}"
        settlement = Settlement(
            settlement_id,
            Money(amount_minor, config.currency),
            SettlementStatus.PROCESSED,
            utr,
            processed_at - timedelta(hours=2),
            processed_at,
        )
        bank_id = f"bank_SYN{group_index:04d}"
        bank: BankTransaction | None = BankTransaction(
            bank_id,
            processed_at + timedelta(days=1),
            Money(amount_minor, config.currency),
            "CREDIT",
            utr,
            f"RAZORPAY SETTLEMENT {utr}",
        )
        anomaly = "NONE"
        truth_status = OutcomeStatus.RECONCILED.value
        truth_bank_id: str | None = bank_id

        if config.inject_anomalies:
            if group_index % 17 == 0:
                anomaly = "BANK_CREDIT_MISSING"
                truth_status = OutcomeStatus.UNRECONCILED.value
                truth_bank_id = None
                bank = None
            elif group_index % 19 == 0:
                anomaly = "SETTLEMENT_AMOUNT_MISMATCH"
                settlement = replace(
                    settlement,
                    amount=Money(amount_minor - 2_420_00, config.currency),
                )
                bank = replace(bank, amount=settlement.amount) if bank else None
                truth_status = OutcomeStatus.UNRECONCILED.value
            elif group_index % 13 == 0:
                anomaly = "UTR_MISSING_REVIEW"
                settlement = replace(settlement, utr=None)
                bank = replace(bank, utr=None, reference="RAZORPAY SETTLEMENT") if bank else None
                truth_status = OutcomeStatus.REQUIRES_REVIEW.value
            elif group_index % 23 == 0:
                anomaly = "DUPLICATE_BANK_CREDIT"
                if bank:
                    bank_transactions.append(bank)
                    bank = replace(bank, bank_transaction_id=f"{bank_id}_DUP")
                truth_status = OutcomeStatus.REQUIRES_REVIEW.value
                truth_bank_id = None

        settlements.append(settlement)
        if bank:
            bank_transactions.append(bank)
        expected_status[settlement_id] = truth_status
        expected_bank[settlement_id] = truth_bank_id
        anomalies[settlement_id] = anomaly

    for noise_index in range(1, 16):
        bank_transactions.append(
            BankTransaction(
                f"bank_NOISE{noise_index:03d}",
                origin + timedelta(days=noise_index),
                Money(rng.randrange(10_00, 100_000_00, 100), config.currency),
                "DEBIT" if noise_index % 2 else "CREDIT",
                None,
                f"UNRELATED BANK TRANSACTION {noise_index}",
            )
        )

    return GeneratedDataset(
        config,
        orders,
        payments,
        refunds,
        settlements,
        ledger_lines,
        bank_transactions,
        GroundTruth(expected_status, expected_bank, anomalies, expected_commercial_codes),
    )
