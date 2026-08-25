from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from recon.ingestion.csv_adapter import load_exported_dataset
from recon.synthetic.generator import GeneratorConfig, generate_dataset


class CsvContractTests(TestCase):
    def test_generated_sources_round_trip_without_semantic_drift(self) -> None:
        original = generate_dataset(GeneratorConfig(seed=91, order_count=80))
        with TemporaryDirectory() as directory:
            original.export(Path(directory))
            imported, results = load_exported_dataset(Path(directory), with_truth=True)
        self.assertEqual(imported.orders, original.orders)
        self.assertEqual(imported.payments, original.payments)
        self.assertEqual(imported.refunds, original.refunds)
        self.assertEqual(imported.settlements, original.settlements)
        self.assertEqual(imported.ledger_lines, original.ledger_lines)
        self.assertEqual(imported.bank_transactions, original.bank_transactions)
        self.assertEqual(imported.truth, original.truth)
        self.assertTrue(all(not item.issues for item in results.values()))

    def test_duplicate_rows_do_not_amplify_financial_facts(self) -> None:
        dataset = generate_dataset(GeneratorConfig(seed=92, order_count=20))
        with TemporaryDirectory() as directory:
            path = Path(directory)
            files = dataset.export(path)
            order_lines = files["orders"].read_text(encoding="utf-8").splitlines()
            files["orders"].write_text(
                "\n".join([*order_lines, order_lines[1]]) + "\n", encoding="utf-8"
            )
            imported, results = load_exported_dataset(path, with_truth=True)
        self.assertEqual(len(imported.orders), len(dataset.orders))
        self.assertEqual(results["orders"].duplicate_count, 1)
