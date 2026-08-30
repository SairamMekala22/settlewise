"""Transaction-oriented application service with a replaceable persistence boundary."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from threading import RLock
from uuid import uuid4

from recon.application.repository import RunRepository
from recon.domain.models import ExceptionCase, OutcomeStatus, ReconciliationOutcome
from recon.evaluation.metrics import EvaluationReport, evaluate_outcomes
from recon.evidence.builder import build_settlement_evidence
from recon.exceptions.metrics import unresolved_amount_minor
from recon.reconciliation.commercial import reconcile_commercial_records
from recon.reconciliation.engine import ReconciliationEngine
from recon.synthetic.generator import GeneratedDataset, GeneratorConfig, generate_dataset


@dataclass(frozen=True, slots=True)
class AuditEvent:
    event_id: str
    timestamp: datetime
    event_type: str
    subject_id: str
    actor: str
    details: dict[str, object]
    ai_involved: bool = False


@dataclass(frozen=True, slots=True)
class ReviewDecision:
    decision_id: str
    settlement_id: str
    decision: str
    reason: str
    actor: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class AIInvestigation:
    """Append-only metadata for one advisory, evidence-bounded investigation."""

    investigation_id: str
    run_id: str
    settlement_id: str
    provider: str
    model: str
    prompt_template_version: str
    evidence_ids: tuple[str, ...]
    input_hash: str
    response: str
    response_hash: str
    actor: str
    created_at: datetime
    tool_calls: tuple[str, ...] = ()
    fallback_reason: str | None = None
    attempted_provider: str | None = None
    attempted_model: str | None = None


@dataclass(slots=True)
class RunSnapshot:
    run_id: str
    created_at: datetime
    ruleset_version: str
    dataset: GeneratedDataset
    outcomes: list[ReconciliationOutcome]
    commercial_exceptions: tuple[ExceptionCase, ...]
    evaluation: EvaluationReport | None


class ReconciliationApplication:
    """Application facade; storage can be replaced by PostgreSQL repositories."""

    def __init__(self, repository: RunRepository | None = None) -> None:
        self._runs: dict[str, RunSnapshot] = {}
        self._audits: list[AuditEvent] = []
        self._reviews: list[ReviewDecision] = []
        self._investigations: list[AIInvestigation] = []
        self._lock = RLock()
        self._repository = repository

    def create_demo_run(self, *, seed: int = 20260825, order_count: int = 500) -> RunSnapshot:
        """Generate, reconcile, evaluate, and atomically publish one demo snapshot."""
        dataset = generate_dataset(GeneratorConfig(seed=seed, order_count=order_count))
        return self.create_run(dataset, actor="synthetic-generator")

    def create_run(self, dataset: GeneratedDataset, *, actor: str = "operator") -> RunSnapshot:
        """Reconcile an imported dataset; evaluate only when private truth is present."""
        engine = ReconciliationEngine()
        outcomes = engine.reconcile_all(
            dataset.settlements, dataset.ledger_lines, dataset.bank_transactions
        )
        commercial_exceptions = reconcile_commercial_records(
            dataset.orders, dataset.payments, dataset.refunds
        )
        evaluation = (
            evaluate_outcomes(outcomes, dataset.truth, commercial_exceptions)
            if dataset.truth.expected_status_by_settlement
            else None
        )
        snapshot = RunSnapshot(
            f"run_{uuid4().hex}",
            datetime.now(UTC),
            engine.ruleset_version,
            dataset,
            outcomes,
            commercial_exceptions,
            evaluation,
        )
        completion_event = AuditEvent(
            f"audit_{uuid4().hex}",
            datetime.now(UTC),
            "RUN_COMPLETED",
            snapshot.run_id,
            actor,
            {
                "seed": dataset.config.seed,
                "order_count": len(dataset.orders),
                "settlement_count": len(outcomes),
                "ruleset_version": engine.ruleset_version,
            },
        )
        if self._repository is not None:
            self._repository.save_run(snapshot, completion_event)
        with self._lock:
            self._runs[snapshot.run_id] = snapshot
            self._audits.append(completion_event)
        return snapshot

    def list_runs(self) -> list[RunSnapshot]:
        if self._repository is not None:
            return self._repository.list_runs()
        return sorted(self._runs.values(), key=lambda item: item.created_at, reverse=True)

    def get_run(self, run_id: str) -> RunSnapshot:
        try:
            return self._runs[run_id]
        except KeyError as exc:
            if self._repository is not None:
                snapshot = self._repository.get_run(run_id)
                if snapshot is not None:
                    with self._lock:
                        self._runs[run_id] = snapshot
                    return snapshot
            raise LookupError(f"unknown run: {run_id}") from exc

    def outcomes(
        self, run_id: str, *, status: OutcomeStatus | None = None
    ) -> list[ReconciliationOutcome]:
        items = self.get_run(run_id).outcomes
        return [item for item in items if status is None or item.status == status]

    def outcome(self, run_id: str, settlement_id: str) -> ReconciliationOutcome:
        for item in self.get_run(run_id).outcomes:
            if item.settlement_id == settlement_id:
                return item
        raise LookupError(f"unknown settlement in run: {settlement_id}")

    def evidence(self, run_id: str, settlement_id: str) -> dict[str, object]:
        return build_settlement_evidence(self.outcome(run_id, settlement_id))

    def analytics(self, run_id: str) -> dict[str, object]:
        snapshot = self.get_run(run_id)
        outcomes = snapshot.outcomes
        currency = snapshot.dataset.config.currency
        total = sum(item.calculation.reported_minor for item in outcomes)
        reconciled = sum(
            item.calculation.reported_minor
            for item in outcomes
            if item.status in {OutcomeStatus.RECONCILED, OutcomeStatus.RECONCILED_WITH_WARNINGS}
        )
        exception_count = sum(len(item.exceptions) for item in outcomes) + len(
            snapshot.commercial_exceptions
        )
        return {
            "run_id": run_id,
            "currency": currency,
            "total_processed_minor": total,
            "reconciled_minor": reconciled,
            "unresolved_minor": unresolved_amount_minor(outcomes, currency),
            "reconciliation_rate": reconciled / total if total else 0.0,
            "settlement_count": len(outcomes),
            "automatically_reconciled": sum(
                item.status == OutcomeStatus.RECONCILED for item in outcomes
            ),
            "review_count": sum(item.status == OutcomeStatus.REQUIRES_REVIEW for item in outcomes),
            "unreconciled_count": sum(
                item.status in {OutcomeStatus.UNRECONCILED, OutcomeStatus.INVALID_DATA}
                for item in outcomes
            ),
            "exception_count": exception_count,
            "evaluation": asdict(snapshot.evaluation) if snapshot.evaluation else None,
            "ruleset_version": snapshot.ruleset_version,
        }

    def review(
        self, run_id: str, settlement_id: str, *, decision: str, reason: str, actor: str
    ) -> ReviewDecision:
        self.outcome(run_id, settlement_id)
        if decision not in {"CONFIRMED", "DISMISSED", "ESCALATED"}:
            raise ValueError("unsupported review decision")
        if not reason.strip():
            raise ValueError("review reason is required")
        review = ReviewDecision(
            f"review_{uuid4().hex}",
            settlement_id,
            decision,
            reason.strip(),
            actor,
            datetime.now(UTC),
        )
        audit_event = AuditEvent(
            f"audit_{uuid4().hex}",
            review.created_at,
            "REVIEW_DECISION_RECORDED",
            settlement_id,
            actor,
            {"run_id": run_id, "decision": decision, "reason": reason.strip()},
        )
        if self._repository is not None:
            self._repository.save_review(run_id, review, audit_event)
        with self._lock:
            self._reviews.append(review)
            self._audits.append(audit_event)
        return review

    def audit_events(self, *, subject_id: str | None = None) -> list[AuditEvent]:
        if self._repository is not None:
            return self._repository.audit_events(subject_id)
        return [
            item for item in self._audits if subject_id is None or item.subject_id == subject_id
        ]

    def record_ai_investigation(
        self,
        run_id: str,
        settlement_id: str,
        *,
        question: str,
        evidence: dict[str, object],
        provider: str,
        model: str,
        prompt_template_version: str,
        evidence_ids: tuple[str, ...],
        response: str,
        actor: str,
        fallback_reason: str | None,
        attempted_provider: str | None,
        attempted_model: str | None,
        tool_calls: tuple[str, ...],
    ) -> AIInvestigation:
        """Record advisory output and provenance without retaining the raw question prompt."""
        self.outcome(run_id, settlement_id)
        canonical_input = json.dumps(
            {"question": question, "evidence": evidence},
            sort_keys=True,
            separators=(",", ":"),
        )
        created_at = datetime.now(UTC)
        investigation = AIInvestigation(
            investigation_id=f"investigation_{uuid4().hex}",
            run_id=run_id,
            settlement_id=settlement_id,
            provider=provider,
            model=model,
            prompt_template_version=prompt_template_version,
            evidence_ids=evidence_ids,
            input_hash=hashlib.sha256(canonical_input.encode()).hexdigest(),
            response=response,
            response_hash=hashlib.sha256(response.encode()).hexdigest(),
            actor=actor,
            created_at=created_at,
            tool_calls=tool_calls,
            fallback_reason=fallback_reason,
            attempted_provider=attempted_provider,
            attempted_model=attempted_model,
        )
        ai_involved = provider != "deterministic-evidence" or attempted_provider is not None
        audit_event = AuditEvent(
            event_id=f"audit_{uuid4().hex}",
            timestamp=created_at,
            event_type="AI_INVESTIGATION_RECORDED",
            subject_id=settlement_id,
            actor=actor,
            details={
                "investigation_id": investigation.investigation_id,
                "run_id": run_id,
                "provider": provider,
                "model": model,
                "prompt_template_version": prompt_template_version,
                "evidence_ids": list(evidence_ids),
                "input_hash": investigation.input_hash,
                "response_hash": investigation.response_hash,
                "tool_calls": list(tool_calls),
                "fallback_reason": fallback_reason,
                "attempted_provider": attempted_provider,
                "attempted_model": attempted_model,
            },
            ai_involved=ai_involved,
        )
        if self._repository is not None:
            self._repository.save_ai_investigation(investigation, audit_event)
        with self._lock:
            self._investigations.append(investigation)
            self._audits.append(audit_event)
        return investigation
