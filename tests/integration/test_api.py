import json
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from apps.api.main import app
from recon.synthetic.generator import GeneratorConfig, generate_dataset

client = TestClient(app)


def test_demo_run_exposes_evidence_ai_and_review() -> None:
    created = client.post(
        "/api/v1/reconciliation-runs/demo", json={"seed": 1001, "order_count": 100}
    )
    assert created.status_code == 201
    run_id = created.json()["run_id"]

    analytics = client.get(f"/api/v1/reconciliation-runs/{run_id}/analytics")
    assert analytics.status_code == 200
    assert analytics.json()["evaluation"]["false_reconciled"] == 0
    scorecard = analytics.json()["evaluation"]["scorecard"]
    assert [item["metric"] for item in scorecard] == [
        "precision_auto",
        "forced_match_rate",
        "recall_auto",
        "link_precision_all_tiers",
        "link_recall_all_tiers",
        "exception_recall",
        "exception_code_accuracy",
        "exception_precision",
        "value_coverage",
    ]
    assert all(0.0 <= item["value"] <= 1.0 for item in scorecard)
    assert "expected_bank_by_settlement" not in str(analytics.json())

    outcomes = client.get(f"/api/v1/reconciliation-runs/{run_id}/outcomes").json()
    settlement_id = outcomes[0]["settlement_id"]
    detail = client.get(f"/api/v1/reconciliation-runs/{run_id}/settlements/{settlement_id}")
    assert detail.status_code == 200
    assert detail.json()["calculation"]["expected_net_minor"] > 0

    answer = client.post(
        "/api/v1/ai/queries",
        json={
            "run_id": run_id,
            "settlement_id": settlement_id,
            "question": "Why did this settlement receive this status?",
        },
    )
    assert answer.status_code == 200
    assert settlement_id in answer.json()["evidence_ids"]
    assert answer.json()["provider"] == "deterministic-evidence"
    assert answer.json()["model"] == "local-rules"
    ai_audit = client.get("/api/v1/audit-events", params={"subject_id": settlement_id})
    assert ai_audit.json()[-1]["event_type"] == "AI_INVESTIGATION_RECORDED"
    assert ai_audit.json()[-1]["details"]["prompt_template_version"]
    assert ai_audit.json()[-1]["details"]["tool_calls"] == ["get_settlement_evidence"]
    assert "question" not in ai_audit.json()[-1]["details"]

    questions = client.get("/api/v1/ai/questions")
    assert questions.status_code == 200
    assert len(questions.json()["questions"]) == 3

    review = client.post(
        f"/api/v1/reconciliation-runs/{run_id}/settlements/{settlement_id}/reviews",
        json={"decision": "CONFIRMED", "reason": "Verified against source evidence"},
    )
    assert review.status_code == 201
    audit = client.get("/api/v1/audit-events", params={"subject_id": settlement_id})
    assert audit.json()[-1]["event_type"] == "REVIEW_DECISION_RECORDED"


def test_six_file_import_reconciles_without_exposing_ground_truth() -> None:
    dataset = generate_dataset(GeneratorConfig(seed=1002, order_count=60))
    with TemporaryDirectory() as directory:
        paths = dataset.export(Path(directory), include_truth=False)
        files = {
            "orders": (paths["orders"].name, paths["orders"].read_bytes(), "text/csv"),
            "payments": (paths["payments"].name, paths["payments"].read_bytes(), "text/csv"),
            "refunds": (paths["refunds"].name, paths["refunds"].read_bytes(), "text/csv"),
            "settlements": (
                paths["settlements"].name,
                paths["settlements"].read_bytes(),
                "text/csv",
            ),
            "ledger": (paths["ledger"].name, paths["ledger"].read_bytes(), "text/csv"),
            "bank": (paths["bank"].name, paths["bank"].read_bytes(), "text/csv"),
        }
        manifest = json.dumps(
            {"generator_version": "1", "config": dataset.config.__dict__}
            if hasattr(dataset.config, "__dict__")
            else {
                "generator_version": "1",
                "config": {
                    "seed": dataset.config.seed,
                    "order_count": dataset.config.order_count,
                    "payments_per_settlement": dataset.config.payments_per_settlement,
                    "currency": dataset.config.currency,
                    "fee_rate": dataset.config.fee_rate,
                    "tax_rate": dataset.config.tax_rate,
                    "inject_anomalies": dataset.config.inject_anomalies,
                },
            }
        )
        response = client.post(
            "/api/v1/imports/reconcile", files=files, data={"manifest": manifest}
        )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["imports"]["orders"]["accepted"] == 60
    analytics = client.get(f"/api/v1/reconciliation-runs/{payload['run_id']}/analytics").json()
    assert analytics["evaluation"] is None
