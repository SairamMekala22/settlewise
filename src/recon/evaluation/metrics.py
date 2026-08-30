"""Compute outcome and automatic-match quality without fabricated values."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from recon.domain.models import ExceptionCase, OutcomeStatus, ReconciliationOutcome
from recon.synthetic.generator import GroundTruth


@dataclass(frozen=True, slots=True)
class EvaluationMetric:
    """One aggregate, truth-backed score safe to expose without truth records."""

    metric: str
    value: float
    detail: str
    target: float | None = None


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
    scorecard: tuple[EvaluationMetric, ...] = ()


_ANOMALY_EXCEPTION_CODE = {
    "BANK_CREDIT_MISSING": "BANK_CREDIT_MISSING",
    "SETTLEMENT_AMOUNT_MISMATCH": "SETTLEMENT_AMOUNT_MISMATCH",
    "UTR_MISSING_REVIEW": "UTR_MISSING",
    "DUPLICATE_BANK_CREDIT": "AMBIGUOUS_BANK_MATCH",
}


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
    auto_link_true_positives = 0
    auto_link_false_positives = 0
    forced_auto_matches = 0
    all_link_true_positives = 0
    all_link_false_positives = 0
    expected_links = 0
    no_partner_settlements = 0
    eligible_value_minor = 0
    covered_value_minor = 0
    for outcome in outcomes:
        expected = truth.expected_status_by_settlement[outcome.settlement_id]
        expected_bank_id = truth.expected_bank_by_settlement[outcome.settlement_id]
        predicted_bank_id = outcome.bank_match.bank_transaction_id
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
        if expected_bank_id is None:
            no_partner_settlements += 1
            forced_auto_matches += int(outcome.bank_match.accepted)
        else:
            expected_links += 1
            eligible_value_minor += outcome.calculation.reported_minor
        if outcome.bank_match.accepted:
            if predicted_bank_id == expected_bank_id and expected_bank_id is not None:
                auto_link_true_positives += 1
            else:
                auto_link_false_positives += 1
        if predicted_bank_id is not None:
            if predicted_bank_id == expected_bank_id:
                all_link_true_positives += 1
                covered_value_minor += outcome.calculation.reported_minor
            else:
                all_link_false_positives += 1
    count = len(outcomes)
    expected_commercial_counts = Counter(truth.expected_commercial_exception_codes)
    actual_commercial_counts = Counter(item.code.value for item in commercial_exceptions)
    expected_settlement_counts = Counter(
        _ANOMALY_EXCEPTION_CODE[anomaly]
        for anomaly in truth.anomaly_by_settlement.values()
        if anomaly in _ANOMALY_EXCEPTION_CODE
    )
    actual_settlement_counts = Counter(
        exception.code.value for outcome in outcomes for exception in outcome.exceptions
    )
    expected_exception_counts = expected_commercial_counts + expected_settlement_counts
    actual_exception_counts = actual_commercial_counts + actual_settlement_counts
    true_positive_exceptions = sum(
        min(count, actual_exception_counts.get(code, 0))
        for code, count in expected_exception_counts.items()
    )
    expected_exception_total = sum(expected_exception_counts.values())
    actual_exception_total = sum(actual_exception_counts.values())
    auto_link_total = auto_link_true_positives + auto_link_false_positives
    all_link_total = all_link_true_positives + all_link_false_positives
    auto_link_precision = (
        auto_link_true_positives / auto_link_total if auto_link_total else 1.0
    )
    forced_match_rate = (
        forced_auto_matches / no_partner_settlements if no_partner_settlements else 0.0
    )
    auto_link_recall = auto_link_true_positives / expected_links if expected_links else 1.0
    all_link_precision = (
        all_link_true_positives / all_link_total if all_link_total else 1.0
    )
    all_link_recall = all_link_true_positives / expected_links if expected_links else 1.0
    missed_links = expected_links - all_link_true_positives
    missed_exceptions = expected_exception_total - true_positive_exceptions
    false_positive_exceptions = actual_exception_total - true_positive_exceptions
    exception_precision = (
        true_positive_exceptions / actual_exception_total if actual_exception_total else 1.0
    )
    exception_recall = (
        true_positive_exceptions / expected_exception_total if expected_exception_total else 1.0
    )
    comparable_exception_count = min(expected_exception_total, actual_exception_total)
    exception_code_accuracy = (
        true_positive_exceptions / comparable_exception_count
        if comparable_exception_count
        else float(expected_exception_total == actual_exception_total)
    )
    value_coverage = covered_value_minor / eligible_value_minor if eligible_value_minor else 1.0
    scorecard = (
        EvaluationMetric(
            "precision_auto",
            auto_link_precision,
            f"{auto_link_true_positives} TP, {auto_link_false_positives} FP",
            1.0,
        ),
        EvaluationMetric(
            "forced_match_rate",
            forced_match_rate,
            f"{forced_auto_matches} of {no_partner_settlements} cases with no unique partner",
            0.0,
        ),
        EvaluationMetric(
            "recall_auto",
            auto_link_recall,
            f"{auto_link_true_positives} of {expected_links} correct partners auto-accepted",
        ),
        EvaluationMetric(
            "link_precision_all_tiers",
            all_link_precision,
            f"{all_link_true_positives} TP, {all_link_false_positives} FP",
        ),
        EvaluationMetric(
            "link_recall_all_tiers",
            all_link_recall,
            f"{missed_links} misses across {expected_links} linkable settlements",
        ),
        EvaluationMetric(
            "exception_recall",
            exception_recall,
            f"{missed_exceptions} misses across {expected_exception_total} expected exceptions",
        ),
        EvaluationMetric(
            "exception_code_accuracy",
            exception_code_accuracy,
            f"{true_positive_exceptions} correctly coded aggregate detections",
        ),
        EvaluationMetric(
            "exception_precision",
            exception_precision,
            f"{actual_exception_total} flagged, {false_positive_exceptions} unsupported",
        ),
        EvaluationMetric(
            "value_coverage",
            value_coverage,
            f"{covered_value_minor:,} of {eligible_value_minor:,} eligible minor units linked",
        ),
    )
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
        exception_precision=exception_precision,
        exception_recall=exception_recall,
        expected_commercial_exceptions=sum(expected_commercial_counts.values()),
        detected_commercial_exceptions=sum(actual_commercial_counts.values()),
        scorecard=scorecard,
    )
