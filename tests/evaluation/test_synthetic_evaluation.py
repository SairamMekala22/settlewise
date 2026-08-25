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

    def test_generator_is_reproducible(self) -> None:
        config = GeneratorConfig(seed=7, order_count=50)
        left = generate_dataset(config)
        right = generate_dataset(config)
        self.assertEqual(left.settlements, right.settlements)
        self.assertEqual(left.bank_transactions, right.bank_transactions)
        self.assertEqual(left.truth, right.truth)
