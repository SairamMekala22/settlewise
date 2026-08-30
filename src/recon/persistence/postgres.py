"""PostgreSQL implementation of the application run repository."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import cast

from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from recon.application.service import AIInvestigation, AuditEvent, ReviewDecision, RunSnapshot
from recon.evidence.builder import build_settlement_evidence
from recon.persistence.codec import decode_snapshot, encode_snapshot
from recon.persistence.models import (
    AIInvestigationRecord,
    AuditEventRecord,
    OutcomeRecord,
    ReconciliationRunRecord,
    ReviewDecisionRecord,
    TenantRecord,
)


class PostgresRunRepository:
    """Durably store immutable snapshots and append-only operator activity by tenant."""

    def __init__(
        self,
        database_url: str,
        *,
        tenant_slug: str,
        tenant_name: str = "Demo Merchant",
        engine: Engine | None = None,
    ) -> None:
        if not database_url.startswith(("postgresql://", "postgresql+psycopg://")):
            raise ValueError("PostgresRunRepository requires a PostgreSQL URL")
        self.tenant_slug = tenant_slug
        self.tenant_name = tenant_name
        self.engine = engine or create_engine(database_url, pool_pre_ping=True)
        self._sessions = sessionmaker(self.engine, expire_on_commit=False)

    def _tenant(self, session: Session) -> TenantRecord:
        tenant = session.scalar(select(TenantRecord).where(TenantRecord.slug == self.tenant_slug))
        if tenant is None:
            tenant = TenantRecord(
                slug=self.tenant_slug,
                name=self.tenant_name,
                default_currency="INR",
                timezone="Asia/Kolkata",
                created_at=datetime.now(UTC),
            )
            session.add(tenant)
            session.flush()
        return tenant

    @staticmethod
    def _audit_record(tenant: TenantRecord, event: AuditEvent) -> AuditEventRecord:
        return AuditEventRecord(
            tenant_id=tenant.id,
            event_type=event.event_type,
            subject_id=event.subject_id,
            actor=event.actor,
            details=event.details,
            ai_involved=event.ai_involved,
            created_at=event.timestamp,
        )

    def save_run(self, snapshot: RunSnapshot, audit_event: AuditEvent) -> None:
        """Persist one run, its outcomes, evidence, and audit event in one transaction."""
        payload = encode_snapshot(snapshot)
        config = cast(dict[str, object], payload["dataset"])["config"]
        config_json = json.dumps(config, sort_keys=True, separators=(",", ":"))
        with self._sessions.begin() as session:
            tenant = self._tenant(session)
            existing = session.scalar(
                select(ReconciliationRunRecord).where(
                    ReconciliationRunRecord.tenant_id == tenant.id,
                    ReconciliationRunRecord.external_run_id == snapshot.run_id,
                )
            )
            if existing is not None:
                return
            run = ReconciliationRunRecord(
                tenant_id=tenant.id,
                external_run_id=snapshot.run_id,
                status="COMPLETED",
                ruleset_version=snapshot.ruleset_version,
                config_hash=hashlib.sha256(config_json.encode()).hexdigest(),
                import_manifest={
                    "generator_version": "1",
                    "seed": snapshot.dataset.config.seed,
                    "order_count": len(snapshot.dataset.orders),
                },
                snapshot_payload=payload,
                started_at=snapshot.created_at,
                completed_at=snapshot.created_at,
            )
            session.add(run)
            session.flush()
            session.add_all(
                [
                    OutcomeRecord(
                        tenant_id=tenant.id,
                        run_id=run.id,
                        settlement_id=outcome.settlement_id,
                        status=outcome.status.value,
                        confidence=outcome.confidence.value,
                        expected_minor=outcome.calculation.expected_net_minor,
                        reported_minor=outcome.calculation.reported_minor,
                        currency=outcome.calculation.currency,
                        evidence=build_settlement_evidence(outcome),
                    )
                    for outcome in snapshot.outcomes
                ]
            )
            session.add(self._audit_record(tenant, audit_event))

    def get_run(self, run_id: str) -> RunSnapshot | None:
        with self._sessions() as session:
            row = session.scalar(
                select(ReconciliationRunRecord)
                .join(TenantRecord, ReconciliationRunRecord.tenant_id == TenantRecord.id)
                .where(
                    TenantRecord.slug == self.tenant_slug,
                    ReconciliationRunRecord.external_run_id == run_id,
                )
            )
            return None if row is None else decode_snapshot(row.snapshot_payload)

    def list_runs(self) -> list[RunSnapshot]:
        with self._sessions() as session:
            rows = session.scalars(
                select(ReconciliationRunRecord)
                .join(TenantRecord, ReconciliationRunRecord.tenant_id == TenantRecord.id)
                .where(TenantRecord.slug == self.tenant_slug)
                .order_by(ReconciliationRunRecord.started_at.desc())
            ).all()
            return [decode_snapshot(row.snapshot_payload) for row in rows]

    def save_review(self, run_id: str, review: ReviewDecision, audit_event: AuditEvent) -> None:
        with self._sessions.begin() as session:
            tenant = self._tenant(session)
            run = session.scalar(
                select(ReconciliationRunRecord).where(
                    ReconciliationRunRecord.tenant_id == tenant.id,
                    ReconciliationRunRecord.external_run_id == run_id,
                )
            )
            if run is None:
                raise LookupError(f"unknown run: {run_id}")
            session.add(
                ReviewDecisionRecord(
                    tenant_id=tenant.id,
                    run_id=run.id,
                    settlement_id=review.settlement_id,
                    decision=review.decision,
                    reason=review.reason,
                    actor=review.actor,
                    created_at=review.created_at,
                )
            )
            session.add(self._audit_record(tenant, audit_event))

    def audit_events(self, subject_id: str | None = None) -> list[AuditEvent]:
        with self._sessions() as session:
            query = (
                select(AuditEventRecord)
                .join(TenantRecord, AuditEventRecord.tenant_id == TenantRecord.id)
                .where(TenantRecord.slug == self.tenant_slug)
                .order_by(AuditEventRecord.created_at)
            )
            if subject_id is not None:
                query = query.where(AuditEventRecord.subject_id == subject_id)
            rows = session.scalars(query).all()
            return [
                AuditEvent(
                    event_id=str(row.id),
                    timestamp=row.created_at.astimezone(UTC),
                    event_type=row.event_type,
                    subject_id=row.subject_id,
                    actor=row.actor,
                    details=row.details,
                    ai_involved=row.ai_involved,
                )
                for row in rows
            ]

    def save_ai_investigation(
        self, investigation: AIInvestigation, audit_event: AuditEvent
    ) -> None:
        """Append one AI advisory and audit record within its tenant and run."""
        with self._sessions.begin() as session:
            tenant = self._tenant(session)
            run = session.scalar(
                select(ReconciliationRunRecord).where(
                    ReconciliationRunRecord.tenant_id == tenant.id,
                    ReconciliationRunRecord.external_run_id == investigation.run_id,
                )
            )
            if run is None:
                raise LookupError(f"unknown run: {investigation.run_id}")
            session.add(
                AIInvestigationRecord(
                    tenant_id=tenant.id,
                    run_id=run.id,
                    external_investigation_id=investigation.investigation_id,
                    settlement_id=investigation.settlement_id,
                    provider=investigation.provider,
                    model=investigation.model,
                    prompt_template_version=investigation.prompt_template_version,
                    evidence_ids=list(investigation.evidence_ids),
                    input_hash=investigation.input_hash,
                    response=investigation.response,
                    response_hash=investigation.response_hash,
                    actor=investigation.actor,
                    tool_calls=list(investigation.tool_calls),
                    fallback_reason=investigation.fallback_reason,
                    attempted_provider=investigation.attempted_provider,
                    attempted_model=investigation.attempted_model,
                    created_at=investigation.created_at,
                )
            )
            session.add(self._audit_record(tenant, audit_event))
