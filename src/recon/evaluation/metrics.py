"""Compute outcome and automatic-match quality without fabricated values."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from recon.domain.models import ExceptionCase, OutcomeStatus, ReconciliationOutcome
from recon.synthetic.generator import GroundTruth


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    settlement_count: int
    correct_outcomes: int
    outcome_accuracy: float
    automatically_reconciled: int
    false_reconciled: int
    auto_reconcile_precision: float
    review_cases: int
    unresolved_cases: int
    confusion: dict[str, dict[str, int]]
    exception_precision: float
    exception_recall: float
    expected_commercial_exceptions: int
    detected_commercial_exceptions: int


def evaluate_outcomes(
    outcomes: list[ReconciliationOutcome],
    truth: GroundTruth,
    commercial_exceptions: tuple[ExceptionCase, ...] = (),
) -> EvaluationReport:
    """Compare deterministic decisions with evaluator-only expected outcomes."""
    confusion: dict[str, dict[str, int]] = {}
    correct = 0
    auto = 0
    false_auto = 0
    reviews = 0
    unresolved = 0
    for outcome in outcomes:
        expected = truth.expected_status_by_settlement[outcome.settlement_id]
        actual = outcome.status.value
        confusion.setdefault(expected, {})[actual] = (
            confusion.setdefault(expected, {}).get(actual, 0) + 1
        )
        correct += int(expected == actual)
        if outcome.status == OutcomeStatus.RECONCILED:
            auto += 1
            false_auto += int(expected != OutcomeStatus.RECONCILED.value)
        if outcome.status == OutcomeStatus.REQUIRES_REVIEW:
            reviews += 1
        if outcome.status in {OutcomeStatus.UNRECONCILED, OutcomeStatus.INVALID_DATA}:
            unresolved += 1
    count = len(outcomes)
    expected_exception_counts = Counter(truth.expected_commercial_exception_codes)
    actual_exception_counts = Counter(item.code.value for item in commercial_exceptions)
    true_positive_exceptions = sum(
        min(count, actual_exception_counts.get(code, 0))
        for code, count in expected_exception_counts.items()
    )
    expected_exception_total = sum(expected_exception_counts.values())
    actual_exception_total = sum(actual_exception_counts.values())
    return EvaluationReport(
        settlement_count=count,
        correct_outcomes=correct,
        outcome_accuracy=correct / count if count else 0.0,
        automatically_reconciled=auto,
        false_reconciled=false_auto,
        auto_reconcile_precision=(auto - false_auto) / auto if auto else 1.0,
        review_cases=reviews,
        unresolved_cases=unresolved,
        confusion=confusion,
        exception_precision=(
            true_positive_exceptions / actual_exception_total if actual_exception_total else 1.0
        ),
        exception_recall=(
            true_positive_exceptions / expected_exception_total if expected_exception_total else 1.0
        ),
        expected_commercial_exceptions=expected_exception_total,
        detected_commercial_exceptions=actual_exception_total,
    )
