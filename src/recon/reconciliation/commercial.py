"""Commercial completeness checks across merchant orders, payments, and refunds."""

from __future__ import annotations

from collections import defaultdict

from recon.domain.models import (
    ExceptionCase,
    ExceptionCode,
    MerchantOrder,
    Payment,
    PaymentStatus,
    Refund,
)


def reconcile_commercial_records(
    orders: list[MerchantOrder], payments: list[Payment], refunds: list[Refund]
) -> tuple[ExceptionCase, ...]:
    """Validate exact entity links, captured totals, and processed refund bounds."""
    exceptions: list[ExceptionCase] = []
    order_by_id = {item.order_id: item for item in orders}
    payment_by_id = {item.payment_id: item for item in payments}
    captured_by_order: dict[str, list[Payment]] = defaultdict(list)

    for payment in payments:
        if payment.order_id is None or payment.order_id not in order_by_id:
            exceptions.append(
                ExceptionCase(
                    ExceptionCode.ORPHAN_PAYMENT,
                    f"Payment {payment.payment_id} does not reference an imported order",
                    payment.amount.amount_minor,
                    payment.amount.currency,
                    (payment.payment_id, payment.order_id or "missing-order-id"),
                )
            )
        elif payment.status == PaymentStatus.CAPTURED:
            captured_by_order[payment.order_id].append(payment)

    for order in orders:
        captured = captured_by_order.get(order.order_id, [])
        captured_total = sum(item.amount.amount_minor for item in captured)
        if order.status.lower() == "paid" and not captured:
            exceptions.append(
                ExceptionCase(
                    ExceptionCode.ORDER_WITHOUT_CAPTURED_PAYMENT,
                    f"Paid merchant order {order.order_id} has no captured payment",
                    order.amount.amount_minor,
                    order.amount.currency,
                    (order.order_id,),
                    "CRITICAL",
                )
            )
        elif captured and captured_total != order.amount.amount_minor:
            exceptions.append(
                ExceptionCase(
                    ExceptionCode.PAYMENT_AMOUNT_MISMATCH,
                    f"Captured payment total differs from order {order.order_id} by "
                    f"{captured_total - order.amount.amount_minor} minor units",
                    abs(captured_total - order.amount.amount_minor),
                    order.amount.currency,
                    (order.order_id, *(item.payment_id for item in captured)),
                )
            )

    processed_refunds: dict[str, int] = defaultdict(int)
    for refund in refunds:
        refund_payment = payment_by_id.get(refund.payment_id)
        if refund_payment is None:
            exceptions.append(
                ExceptionCase(
                    ExceptionCode.ORPHAN_REFUND,
                    f"Refund {refund.refund_id} does not reference an imported payment",
                    refund.amount.amount_minor,
                    refund.amount.currency,
                    (refund.refund_id, refund.payment_id),
                )
            )
            continue
        if refund.status.lower() == "processed":
            processed_refunds[refund.payment_id] += refund.amount.amount_minor

    for payment_id, refunded_minor in processed_refunds.items():
        payment = payment_by_id[payment_id]
        if refunded_minor > payment.amount.amount_minor:
            exceptions.append(
                ExceptionCase(
                    ExceptionCode.REFUND_TOTAL_EXCEEDS_PAYMENT,
                    f"Processed refunds exceed payment {payment_id} by "
                    f"{refunded_minor - payment.amount.amount_minor} minor units",
                    refunded_minor - payment.amount.amount_minor,
                    payment.amount.currency,
                    (payment_id,),
                    "CRITICAL",
                )
            )
    return tuple(exceptions)
