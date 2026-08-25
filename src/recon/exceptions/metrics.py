"""Cause-safe exception amount aggregation."""

from recon.domain.models import OutcomeStatus, ReconciliationOutcome


def unresolved_amount_minor(outcomes: list[ReconciliationOutcome], currency: str) -> int:
    """Count each unresolved settlement once rather than summing symptom exceptions."""
    return sum(
        outcome.calculation.reported_minor
        for outcome in outcomes
        if outcome.calculation.currency == currency
        and outcome.status
        in {
            OutcomeStatus.UNRECONCILED,
            OutcomeStatus.PARTIALLY_RECONCILED,
            OutcomeStatus.REQUIRES_REVIEW,
            OutcomeStatus.INVALID_DATA,
        }
    )
