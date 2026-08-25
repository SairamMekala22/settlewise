from datetime import UTC, datetime

from recon.domain.models import (
    ExceptionCode,
    MerchantOrder,
    Money,
    Payment,
    PaymentStatus,
    Refund,
)
from recon.reconciliation.commercial import reconcile_commercial_records


def test_commercial_rules_detect_orphans_mismatches_and_excess_refunds() -> None:
    now = datetime(2026, 8, 1, tzinfo=UTC)
    orders = [
        MerchantOrder("order_1", Money(100_00, "INR"), "paid", now, "M-1"),
        MerchantOrder("order_2", Money(200_00, "INR"), "paid", now, "M-2"),
    ]
    payments = [
        Payment(
            "pay_1",
            "order_1",
            Money(90_00, "INR"),
            PaymentStatus.CAPTURED,
            now,
            "upi",
        ),
        Payment(
            "pay_orphan",
            "order_missing",
            Money(50_00, "INR"),
            PaymentStatus.CAPTURED,
            now,
            "card",
        ),
    ]
    refunds = [
        Refund("rfnd_1", "pay_1", Money(95_00, "INR"), "processed", now),
        Refund("rfnd_orphan", "pay_missing", Money(10_00, "INR"), "processed", now),
    ]
    codes = [item.code for item in reconcile_commercial_records(orders, payments, refunds)]
    assert codes.count(ExceptionCode.PAYMENT_AMOUNT_MISMATCH) == 1
    assert codes.count(ExceptionCode.ORDER_WITHOUT_CAPTURED_PAYMENT) == 1
    assert codes.count(ExceptionCode.ORPHAN_PAYMENT) == 1
    assert codes.count(ExceptionCode.ORPHAN_REFUND) == 1
    assert codes.count(ExceptionCode.REFUND_TOTAL_EXCEEDS_PAYMENT) == 1
