from decimal import Decimal
from unittest import TestCase

from recon.domain.models import Money
from recon.domain.money import major_to_money, percentage_minor


class MoneyTests(TestCase):
    def test_requires_same_currency_for_arithmetic(self) -> None:
        with self.assertRaisesRegex(ValueError, "currency mismatch"):
            _ = Money(100, "INR") + Money(100, "USD")

    def test_rounds_rates_half_up_to_minor_unit(self) -> None:
        self.assertEqual(percentage_minor(105, Decimal("0.10")), 11)
        self.assertEqual(major_to_money("10.005", "INR"), Money(1001, "INR"))

    def test_rejects_invalid_currency(self) -> None:
        with self.assertRaises(ValueError):
            Money(100, "rupee")
