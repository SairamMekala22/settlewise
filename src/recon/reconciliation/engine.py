"""Pure settlement calculation and conservative outcome projection."""

from __future__ import annotations

from collections import defaultdict

from recon.domain.models import (
    BankTransaction,
    ConfidenceTier,
    ExceptionCase,
    ExceptionCode,
    LedgerType,
    OutcomeStatus,
    ReconciliationOutcome,
    Settlement,
    SettlementCalculation,
    SettlementLedgerLine,
    SettlementStatus,
)
from recon.matching.bank import match_settlement_to_bank


class ReconciliationEngine:
    """Financial engine whose outputs depend only on explicit inputs and rules."""

    ruleset_version = "RECON_RULESET_V1"

    def calculate_settlement(
        self, settlement: Settlement, lines: list[SettlementLedgerLine]
    ) -> tuple[SettlementCalculation, tuple[ExceptionCase, ...]]:
        """Calculate the expected settlement from eligible signed ledger lines."""
        related = [line for line in lines if line.settlement_id == settlement.settlement_id]
        included = [line for line in related if line.settled and not line.on_hold]
        excluded = [line for line in related if not line.settled or line.on_hold]
        exceptions: list[ExceptionCase] = []

        if not related:
            exceptions.append(
                ExceptionCase(
                    ExceptionCode.MISSING_SETTLEMENT_LEDGER,
                    "No settlement reconciliation ledger lines were supplied",
                    settlement.amount.amount_minor,
                    settlement.amount.currency,
                    (settlement.settlement_id,),
                    "CRITICAL",
                )
            )

        for line in related:
            if line.currency != settlement.amount.currency:
                exceptions.append(
                    ExceptionCase(
                        ExceptionCode.CURRENCY_MISMATCH,
                        f"Ledger line {line.line_id} has {line.currency}; settlement has "
                        f"{settlement.amount.currency}",
                        abs(line.net_effect_minor),
                        settlement.amount.currency,
                        (settlement.settlement_id, line.line_id),
                        "CRITICAL",
                    )
                )
            if line.on_hold:
                exceptions.append(
                    ExceptionCase(
                        ExceptionCode.HELD_LEDGER_LINE,
                        f"Ledger line {line.line_id} is on hold and excluded from expected net",
                        abs(line.net_effect_minor),
                        line.currency,
                        (line.line_id,),
                        "WARNING",
                    )
                )
            elif not line.settled:
                exceptions.append(
                    ExceptionCase(
                        ExceptionCode.UNSETTLED_LEDGER_LINE,
                        f"Ledger line {line.line_id} is not settled and excluded from expected net",
                        abs(line.net_effect_minor),
                        line.currency,
                        (line.line_id,),
                        "WARNING",
                    )
                )

        typed: dict[LedgerType, list[SettlementLedgerLine]] = defaultdict(list)
        for line in included:
            typed[line.line_type].append(line)

        payment_credits = sum(line.credit_minor for line in typed[LedgerType.PAYMENT])
        refund_debits = sum(line.debit_minor for line in typed[LedgerType.REFUND])
        transfer_net = sum(
            line.credit_minor - line.debit_minor for line in typed[LedgerType.TRANSFER]
        )
        adjustment_net = sum(
            line.credit_minor - line.debit_minor for line in typed[LedgerType.ADJUSTMENT]
        )
        fees = sum(line.fee_minor for line in included)
        tax = sum(line.tax_minor for line in included)
        expected = sum(line.net_effect_minor for line in included)
        delta = settlement.amount.amount_minor - expected

        calculation = SettlementCalculation(
            settlement_id=settlement.settlement_id,
            currency=settlement.amount.currency,
            payment_credits_minor=payment_credits,
            refund_debits_minor=refund_debits,
            transfer_net_minor=transfer_net,
            adjustment_net_minor=adjustment_net,
            fees_minor=fees,
            tax_minor=tax,
            expected_net_minor=expected,
            reported_minor=settlement.amount.amount_minor,
            gateway_delta_minor=delta,
            included_line_ids=tuple(line.line_id for line in included),
            excluded_line_ids=tuple(line.line_id for line in excluded),
        )
        if settlement.status == SettlementStatus.FAILED:
            exceptions.append(
                ExceptionCase(
                    ExceptionCode.SETTLEMENT_FAILED,
                    "Razorpay settlement is marked failed",
                    abs(expected),
                    calculation.currency,
                    (settlement.settlement_id,),
                    "CRITICAL",
                )
            )
        if delta != 0:
            exceptions.append(
                ExceptionCase(
                    ExceptionCode.SETTLEMENT_AMOUNT_MISMATCH,
                    f"Reported settlement differs from ledger expected net by {delta} minor units",
                    abs(delta),
                    calculation.currency,
                    (settlement.settlement_id, *calculation.included_line_ids),
                    "MATERIAL",
                )
            )
        return calculation, tuple(exceptions)

    def reconcile_settlement(
        self,
        settlement: Settlement,
        lines: list[SettlementLedgerLine],
        bank_transactions: list[BankTransaction],
    ) -> ReconciliationOutcome:
        """Reconcile one settlement through gateway ledger and bank layers."""
        calculation, base_exceptions = self.calculate_settlement(settlement, lines)
        bank_match = match_settlement_to_bank(settlement, bank_transactions)
        exceptions = list(base_exceptions)

        if bank_match.confidence == ConfidenceTier.NONE:
            exceptions.append(
                ExceptionCase(
                    ExceptionCode.BANK_CREDIT_MISSING,
                    bank_match.reason,
                    settlement.amount.amount_minor,
                    settlement.amount.currency,
                    (settlement.settlement_id,),
                )
            )
        elif bank_match.confidence == ConfidenceTier.LOW:
            exceptions.append(
                ExceptionCase(
                    ExceptionCode.AMBIGUOUS_BANK_MATCH,
                    bank_match.reason,
                    settlement.amount.amount_minor,
                    settlement.amount.currency,
                    (settlement.settlement_id, *bank_match.candidate_ids),
                )
            )
        elif bank_match.confidence == ConfidenceTier.MEDIUM:
            code = (
                ExceptionCode.BANK_CREDIT_DELAYED
                if bank_match.features and bank_match.features.utr_exact
                else ExceptionCode.UTR_MISSING
            )
            exceptions.append(
                ExceptionCase(
                    code,
                    bank_match.reason,
                    0,
                    settlement.amount.currency,
                    (settlement.settlement_id, bank_match.bank_transaction_id or ""),
                    "WARNING",
                )
            )

        critical_data = any(
            item.code in {ExceptionCode.MISSING_SETTLEMENT_LEDGER, ExceptionCode.CURRENCY_MISMATCH}
            for item in exceptions
        )
        gateway_mismatch = (
            calculation.gateway_delta_minor != 0 or settlement.status == SettlementStatus.FAILED
        )
        if critical_data:
            status = OutcomeStatus.INVALID_DATA
        elif bank_match.confidence in {ConfidenceTier.LOW, ConfidenceTier.MEDIUM}:
            status = OutcomeStatus.REQUIRES_REVIEW
        elif gateway_mismatch or bank_match.confidence == ConfidenceTier.NONE:
            status = OutcomeStatus.UNRECONCILED
        elif exceptions:
            status = OutcomeStatus.RECONCILED_WITH_WARNINGS
        else:
            status = OutcomeStatus.RECONCILED

        return ReconciliationOutcome(
            settlement.settlement_id,
            status,
            bank_match.confidence,
            calculation,
            bank_match,
            tuple(exceptions),
        )

    def reconcile_all(
        self,
        settlements: list[Settlement],
        lines: list[SettlementLedgerLine],
        bank_transactions: list[BankTransaction],
    ) -> list[ReconciliationOutcome]:
        """Reconcile all settlements deterministically in source-independent order."""
        return [
            self.reconcile_settlement(settlement, lines, bank_transactions)
            for settlement in sorted(settlements, key=lambda item: item.settlement_id)
        ]
