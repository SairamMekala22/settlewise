from datetime import UTC, datetime, timedelta
from unittest import TestCase

from recon.domain.models import (
    BankTransaction,
    ConfidenceTier,
    LedgerType,
    Money,
    OutcomeStatus,
    Settlement,
    SettlementLedgerLine,
    SettlementStatus,
)
from recon.reconciliation.engine import ReconciliationEngine

NOW = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)


def settlement(amount: int = 852_800, utr: str | None = "AXISCN1153863727") -> Settlement:
    return Settlement("setl_1", Money(amount, "INR"), SettlementStatus.PROCESSED, utr, NOW, NOW)


def lines() -> list[SettlementLedgerLine]:
    values = [400_000, 300_000, 300_000]
    result = [
        SettlementLedgerLine(
            f"line_{index}",
            "setl_1",
            f"pay_{index}",
            LedgerType.PAYMENT,
            "INR",
            value,
            0,
            (16_000, 12_000, 12_000)[index - 1],
            (2_880, 2_160, 2_160)[index - 1],
            True,
            False,
            NOW,
            NOW,
            f"pay_{index}",
        )
        for index, value in enumerate(values, 1)
    ]
    result.append(
        SettlementLedgerLine(
            "line_refund",
            "setl_1",
            "rfnd_1",
            LedgerType.REFUND,
            "INR",
            0,
            100_000,
            0,
            0,
            True,
            False,
            NOW,
            NOW,
            "pay_1",
        )
    )
    return result


class ReconciliationScenarios(TestCase):
    def test_many_to_one_settlement_reconciles_with_exact_bank_credit(self) -> None:
        item = settlement()
        bank = BankTransaction(
            "bank_1", NOW + timedelta(days=1), item.amount, "CREDIT", item.utr, "RZP"
        )
        outcome = ReconciliationEngine().reconcile_settlement(item, lines(), [bank])
        self.assertEqual(outcome.calculation.payment_credits_minor, 1_000_000)
        self.assertEqual(outcome.calculation.refund_debits_minor, 100_000)
        self.assertEqual(outcome.calculation.fees_minor, 40_000)
        self.assertEqual(outcome.calculation.tax_minor, 7_200)
        self.assertEqual(outcome.calculation.expected_net_minor, 852_800)
        self.assertEqual(outcome.status, OutcomeStatus.RECONCILED)
        self.assertEqual(outcome.confidence, ConfidenceTier.HIGH)

    def test_missing_utr_exact_amount_requires_review(self) -> None:
        item = settlement(utr=None)
        bank = BankTransaction(
            "bank_1", NOW + timedelta(days=1), item.amount, "CREDIT", None, "RAZORPAY"
        )
        outcome = ReconciliationEngine().reconcile_settlement(item, lines(), [bank])
        self.assertEqual(outcome.status, OutcomeStatus.REQUIRES_REVIEW)
        self.assertEqual(outcome.confidence, ConfidenceTier.MEDIUM)
        self.assertFalse(outcome.bank_match.accepted)

    def test_duplicate_exact_bank_credit_is_never_auto_matched(self) -> None:
        item = settlement()
        banks = [
            BankTransaction(
                f"bank_{index}", NOW + timedelta(days=1), item.amount, "CREDIT", item.utr, "RZP"
            )
            for index in (1, 2)
        ]
        outcome = ReconciliationEngine().reconcile_settlement(item, lines(), banks)
        self.assertEqual(outcome.status, OutcomeStatus.REQUIRES_REVIEW)
        self.assertFalse(outcome.bank_match.accepted)

    def test_gateway_mismatch_cannot_be_hidden_by_matching_bank_credit(self) -> None:
        item = settlement(amount=850_000)
        bank = BankTransaction(
            "bank_1", NOW + timedelta(days=1), item.amount, "CREDIT", item.utr, "RZP"
        )
        outcome = ReconciliationEngine().reconcile_settlement(item, lines(), [bank])
        self.assertEqual(outcome.status, OutcomeStatus.UNRECONCILED)
        self.assertEqual(outcome.calculation.gateway_delta_minor, -2_800)
