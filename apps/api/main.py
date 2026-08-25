"""HTTP boundary for the settlement reconciliation modular monolith."""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from recon.ai.controller import EvidenceController
from recon.application.service import ReconciliationApplication
from recon.domain.models import OutcomeStatus
from recon.ingestion.csv_adapter import load_exported_dataset
from recon.persistence.postgres import PostgresRunRepository

app = FastAPI(
    title="Settlement Reconciliation Agent API",
    version="0.1.0",
    description="Deterministic settlement reconciliation with evidence-grounded explanations.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Actor"],
)


def _build_application() -> tuple[ReconciliationApplication, str]:
    database_url = os.environ.get("DATABASE_URL")
    if database_url and os.environ.get("RECON_PERSISTENCE", "postgres") != "memory":
        repository = PostgresRunRepository(
            database_url,
            tenant_slug=os.environ.get("RECON_TENANT_ID", "demo-merchant"),
        )
        return ReconciliationApplication(repository), "postgresql"
    return ReconciliationApplication(), "memory"


application, persistence_mode = _build_application()
controller = EvidenceController()


class DemoRunRequest(BaseModel):
    seed: int = 20260825
    order_count: int = Field(default=500, ge=50, le=10_000)


class ReviewRequest(BaseModel):
    decision: str
    reason: str = Field(min_length=3, max_length=1_000)
    actor: str = Field(default="demo-reviewer", min_length=2, max_length=120)


class AIQueryRequest(BaseModel):
    run_id: str
    settlement_id: str
    question: str = Field(min_length=3, max_length=1_000)


def _not_found(exc: LookupError) -> HTTPException:
    return HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": str(exc)})


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "ruleset": "RECON_RULESET_V1",
        "persistence": persistence_mode,
    }


@app.post("/api/v1/reconciliation-runs/demo", status_code=201)
def create_demo_run(request: DemoRunRequest) -> dict[str, object]:
    snapshot = application.create_demo_run(seed=request.seed, order_count=request.order_count)
    return {
        "run_id": snapshot.run_id,
        "created_at": snapshot.created_at,
        "ruleset_version": snapshot.ruleset_version,
    }


@app.post("/api/v1/imports/reconcile", status_code=201)
async def import_and_reconcile(
    orders: Annotated[UploadFile, File()],
    payments: Annotated[UploadFile, File()],
    refunds: Annotated[UploadFile, File()],
    settlements: Annotated[UploadFile, File()],
    ledger: Annotated[UploadFile, File()],
    bank: Annotated[UploadFile, File()],
    manifest: Annotated[str, Form()],
) -> dict[str, object]:
    """Import the six V1 contracts, quarantine malformed rows, and reconcile accepted facts."""
    uploads = {
        "merchant_orders.csv": orders,
        "razorpay_payments.csv": payments,
        "razorpay_refunds.csv": refunds,
        "razorpay_settlements.csv": settlements,
        "razorpay_settlement_recon.csv": ledger,
        "bank_statement.csv": bank,
    }
    total_bytes = 0
    with TemporaryDirectory(prefix="recon-import-") as directory:
        root = Path(directory)
        for safe_name, upload in uploads.items():
            content = await upload.read()
            total_bytes += len(content)
            if total_bytes > 20 * 1024 * 1024:
                raise HTTPException(status_code=413, detail={"code": "UPLOAD_TOO_LARGE"})
            (root / safe_name).write_bytes(content)
        try:
            parsed_manifest = json.loads(manifest)
            if not isinstance(parsed_manifest, dict):
                raise ValueError("manifest must be an object")
            (root / "manifest.json").write_text(json.dumps(parsed_manifest), encoding="utf-8")
            dataset, diagnostics = load_exported_dataset(root)
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            raise HTTPException(
                status_code=422,
                detail={"code": "INVALID_IMPORT", "message": str(exc)},
            ) from exc
    snapshot = application.create_run(dataset, actor="file-import")
    return {
        "run_id": snapshot.run_id,
        "imports": {
            name: {
                "accepted": len(result.records),
                "quarantined": len(result.issues),
                "duplicates": result.duplicate_count,
                "file_hash": result.file_hash,
            }
            for name, result in diagnostics.items()
        },
    }


@app.get("/api/v1/reconciliation-runs")
def list_runs() -> list[dict[str, object]]:
    return [
        {
            "run_id": item.run_id,
            "created_at": item.created_at,
            "ruleset_version": item.ruleset_version,
            "settlement_count": len(item.outcomes),
        }
        for item in application.list_runs()
    ]


@app.get("/api/v1/reconciliation-runs/{run_id}/analytics")
def analytics(run_id: str) -> dict[str, object]:
    try:
        return application.analytics(run_id)
    except LookupError as exc:
        raise _not_found(exc) from exc


@app.get("/api/v1/reconciliation-runs/{run_id}/outcomes")
def outcomes(
    run_id: str,
    status: Annotated[OutcomeStatus | None, Query()] = None,
) -> list[dict[str, object]]:
    try:
        return jsonable_encoder(application.outcomes(run_id, status=status))
    except LookupError as exc:
        raise _not_found(exc) from exc


@app.get("/api/v1/reconciliation-runs/{run_id}/settlements/{settlement_id}")
def settlement_detail(run_id: str, settlement_id: str) -> dict[str, object]:
    try:
        return application.evidence(run_id, settlement_id)
    except LookupError as exc:
        raise _not_found(exc) from exc


@app.get("/api/v1/reconciliation-runs/{run_id}/exceptions")
def exceptions(run_id: str) -> list[dict[str, object]]:
    try:
        result: list[dict[str, object]] = []
        snapshot = application.get_run(run_id)
        for outcome in snapshot.outcomes:
            result.extend(
                {"settlement_id": outcome.settlement_id, **jsonable_encoder(item)}
                for item in outcome.exceptions
            )
        result.extend(
            {
                "settlement_id": None,
                "subject_id": item.evidence_ids[0] if item.evidence_ids else None,
                **jsonable_encoder(item),
            }
            for item in snapshot.commercial_exceptions
        )
        return result
    except LookupError as exc:
        raise _not_found(exc) from exc


@app.post(
    "/api/v1/reconciliation-runs/{run_id}/settlements/{settlement_id}/reviews", status_code=201
)
def review(run_id: str, settlement_id: str, request: ReviewRequest) -> dict[str, object]:
    try:
        return asdict(
            application.review(
                run_id,
                settlement_id,
                decision=request.decision,
                reason=request.reason,
                actor=request.actor,
            )
        )
    except LookupError as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail={"code": "INVALID_REVIEW", "message": str(exc)}
        ) from exc


@app.get("/api/v1/audit-events")
def audit_events(subject_id: str | None = None) -> list[dict[str, object]]:
    return jsonable_encoder(application.audit_events(subject_id=subject_id))


@app.post("/api/v1/ai/queries")
def ai_query(request: AIQueryRequest) -> dict[str, object]:
    try:
        evidence = application.evidence(request.run_id, request.settlement_id)
        answer = controller.answer(request.question, evidence)
        return asdict(answer)
    except LookupError as exc:
        raise _not_found(exc) from exc
