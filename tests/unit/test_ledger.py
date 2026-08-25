from datetime import UTC, datetime
from unittest import TestCase

from recon.domain.models import LedgerType, SettlementLedgerLine


class LedgerTests(TestCase):
    def test_signed_effect_is_applied_once(self) -> None:
        line = SettlementLedgerLine(
            "line_1",
            "setl_1",
            "pay_1",
            LedgerType.PAYMENT,
            "INR",
            1_000_00,
            0,
            2_000,
            360,
            True,
            False,
            datetime.now(UTC),
            datetime.now(UTC),
            "pay_1",
        )
        self.assertEqual(line.net_effect_minor, 97_640)

    def test_rejects_a_line_that_is_both_credit_and_debit(self) -> None:
        with self.assertRaises(ValueError):
            SettlementLedgerLine(
                "line_1",
                "setl_1",
                "adj_1",
                LedgerType.ADJUSTMENT,
                "INR",
                100,
                100,
                0,
                0,
                True,
                False,
                datetime.now(UTC),
                datetime.now(UTC),
            )
