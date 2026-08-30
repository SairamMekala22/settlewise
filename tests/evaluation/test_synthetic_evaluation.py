from dataclasses import replace
from unittest import TestCase

from recon.evaluation.metrics import evaluate_outcomes
from recon.reconciliation.commercial import reconcile_commercial_records
from recon.reconciliation.engine import ReconciliationEngine
from recon.synthetic.generator import GeneratorConfig, generate_dataset


class SyntheticEvaluationTests(TestCase):
    def test_seeded_adversarial_dataset_has_no_false_reconciliations(self) -> None:
        dataset = generate_dataset(GeneratorConfig(seed=12345, order_count=500))
        outcomes = ReconciliationEngine().reconcile_all(
            dataset.settlements, dataset.ledger_lines, dataset.bank_transactions
        )
        commercial_exceptions = reconcile_commercial_records(
            dataset.orders, dataset.payments, dataset.refunds
        )
        report = evaluate_outcomes(outcomes, dataset.truth, commercial_exceptions)
        self.assertEqual(report.settlement_count, len(dataset.settlements))
        self.assertEqual(report.false_reconciled, 0)
        self.assertEqual(report.outcome_accuracy, 1.0)
        self.assertEqual(report.exception_precision, 1.0)
        self.assertEqual(report.exception_recall, 1.0)
        scorecard = {item.metric: item for item in report.scorecard}
        self.assertEqual(
            set(scorecard),
            {
                "precision_auto",
                "forced_match_rate",
                "recall_auto",
                "link_precision_all_tiers",
                "link_recall_all_tiers",
                "exception_recall",
                "exception_code_accuracy",
                "exception_precision",
                "value_coverage",
            },
        )
        self.assertEqual(scorecard["precision_auto"].value, 1.0)
        self.assertEqual(scorecard["precision_auto"].target, 1.0)
        self.assertEqual(scorecard["forced_match_rate"].value, 0.0)
        self.assertEqual(scorecard["forced_match_rate"].target, 0.0)
        self.assertLess(scorecard["recall_auto"].value, 1.0)
        self.assertEqual(scorecard["link_precision_all_tiers"].value, 1.0)
        self.assertEqual(scorecard["link_recall_all_tiers"].value, 1.0)
        self.assertEqual(scorecard["exception_code_accuracy"].value, 1.0)
        self.assertEqual(scorecard["value_coverage"].value, 1.0)

    def test_generator_is_reproducible(self) -> None:
        config = GeneratorConfig(seed=7, order_count=50)
        left = generate_dataset(config)
        right = generate_dataset(config)
        self.assertEqual(left.settlements, right.settlements)
        self.assertEqual(left.bank_transactions, right.bank_transactions)
        self.assertEqual(left.truth, right.truth)

    def test_scorecard_exposes_forced_false_match_and_missed_value(self) -> None:
        dataset = generate_dataset(GeneratorConfig(seed=12345, order_count=500))
        outcomes = ReconciliationEngine().reconcile_all(
            dataset.settlements, dataset.ledger_lines, dataset.bank_transactions
        )
        forced_index = next(
            index
            for index, outcome in enumerate(outcomes)
            if dataset.truth.expected_bank_by_settlement[outcome.settlement_id] is None
        )
        missed_index = next(
            index
            for index, outcome in enumerate(outcomes)
            if dataset.truth.expected_bank_by_settlement[outcome.settlement_id] is not None
            and outcome.bank_match.bank_transaction_id is not None
        )
        forced = outcomes[forced_index]
        outcomes[forced_index] = replace(
            forced,
            bank_match=replace(
                forced.bank_match,
                bank_transaction_id="bank_FALSE_MATCH",
                accepted=True,
            ),
        )
        missed = outcomes[missed_index]
        outcomes[missed_index] = replace(
            missed,
            bank_match=replace(
                missed.bank_match,
                bank_transaction_id=None,
                accepted=False,
            ),
        )

        report = evaluate_outcomes(
            outcomes,
            dataset.truth,
            reconcile_commercial_records(dataset.orders, dataset.payments, dataset.refunds),
        )
        scorecard = {item.metric: item.value for item in report.scorecard}

        self.assertLess(scorecard["precision_auto"], 1.0)
        self.assertGreater(scorecard["forced_match_rate"], 0.0)
        self.assertLess(scorecard["recall_auto"], 1.0)
        self.assertLess(scorecard["link_precision_all_tiers"], 1.0)
        self.assertLess(scorecard["link_recall_all_tiers"], 1.0)
        self.assertLess(scorecard["value_coverage"], 1.0)
