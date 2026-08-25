"""Local deterministic demo entry point."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from recon.evaluation.metrics import evaluate_outcomes
from recon.reconciliation.commercial import reconcile_commercial_records
from recon.reconciliation.engine import ReconciliationEngine
from recon.synthetic.generator import GeneratorConfig, generate_dataset


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate and reconcile a synthetic settlement dataset"
    )
    parser.add_argument("--orders", type=int, default=500)
    parser.add_argument("--seed", type=int, default=20260825)
    parser.add_argument("--output", type=Path, default=Path("data/generated/demo"))
    args = parser.parse_args()

    dataset = generate_dataset(GeneratorConfig(seed=args.seed, order_count=args.orders))
    paths = dataset.export(args.output)
    outcomes = ReconciliationEngine().reconcile_all(
        dataset.settlements, dataset.ledger_lines, dataset.bank_transactions
    )
    commercial_exceptions = reconcile_commercial_records(
        dataset.orders, dataset.payments, dataset.refunds
    )
    report = evaluate_outcomes(outcomes, dataset.truth, commercial_exceptions)
    print(
        json.dumps(
            {"files": {key: str(value) for key, value in paths.items()}, "metrics": asdict(report)},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
