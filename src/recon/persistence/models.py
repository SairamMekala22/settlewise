"""SQLAlchemy mappings for durable imports, runs, evidence, reviews, and audit.

The domain engine does not import these mappings. PostgreSQL-specific JSONB is used for
lineage/evidence; typed searchable columns retain money, currency, status, and identifiers.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TenantRecord(Base):
    __tablename__ = "tenants"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(120), unique=True)
    name: Mapped[str] = mapped_column(String(240))
    default_currency: Mapped[str] = mapped_column(String(3), default="INR")
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Kolkata")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ImportSessionRecord(Base):
    __tablename__ = "import_sessions"
    __table_args__ = (UniqueConstraint("tenant_id", "source_type", "file_hash"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), index=True)
    source_type: Mapped[str] = mapped_column(String(48))
    file_name: Mapped[str] = mapped_column(String(255))
    file_hash: Mapped[str] = mapped_column(String(64))
    parser_version: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), index=True)
    counts: Mapped[dict[str, object]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ImportRowRecord(Base):
    __tablename__ = "import_rows"
    __table_args__ = (UniqueConstraint("import_session_id", "row_number"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), index=True)
    import_session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("import_sessions.id"), index=True
    )
    row_number: Mapped[int] = mapped_column()
    payload_hash: Mapped[str] = mapped_column(String(64), index=True)
    raw_payload: Mapped[dict[str, object]] = mapped_column(JSONB)
    normalized_payload: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    validation_issues: Mapped[list[dict[str, object]]] = mapped_column(JSONB, default=list)
    disposition: Mapped[str] = mapped_column(String(24))


class SettlementFactRecord(Base):
    __tablename__ = "settlements"
    __table_args__ = (UniqueConstraint("tenant_id", "source_system", "settlement_id"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), index=True)
    source_system: Mapped[str] = mapped_column(String(32), default="razorpay")
    settlement_id: Mapped[str] = mapped_column(String(64), index=True)
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(String(24), index=True)
    utr: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    import_row_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("import_rows.id"))


class LedgerLineRecord(Base):
    __tablename__ = "settlement_ledger_lines"
    __table_args__ = (UniqueConstraint("tenant_id", "source_system", "line_id"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), index=True)
    source_system: Mapped[str] = mapped_column(String(32), default="razorpay")
    line_id: Mapped[str] = mapped_column(String(96))
    settlement_id: Mapped[str] = mapped_column(String(64), index=True)
    entity_id: Mapped[str] = mapped_column(String(96), index=True)
    line_type: Mapped[str] = mapped_column(String(24), index=True)
    credit_minor: Mapped[int] = mapped_column(BigInteger)
    debit_minor: Mapped[int] = mapped_column(BigInteger)
    fee_minor: Mapped[int] = mapped_column(BigInteger)
    tax_minor: Mapped[int] = mapped_column(BigInteger)
    net_effect_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    settled: Mapped[bool] = mapped_column(Boolean)
    on_hold: Mapped[bool] = mapped_column(Boolean)
    import_row_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("import_rows.id"))


class BankTransactionRecord(Base):
    __tablename__ = "bank_transactions"
    __table_args__ = (UniqueConstraint("tenant_id", "source_system", "bank_transaction_id"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), index=True)
    source_system: Mapped[str] = mapped_column(String(64))
    bank_transaction_id: Mapped[str] = mapped_column(String(96))
    booked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    direction: Mapped[str] = mapped_column(String(8))
    utr: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    masked_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    import_row_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("import_rows.id"))


class ReconciliationRunRecord(Base):
    __tablename__ = "reconciliation_runs"
    __table_args__ = (UniqueConstraint("tenant_id", "external_run_id"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), index=True)
    external_run_id: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(24), index=True)
    ruleset_version: Mapped[str] = mapped_column(String(48))
    config_hash: Mapped[str] = mapped_column(String(64))
    import_manifest: Mapped[dict[str, object]] = mapped_column(JSONB)
    snapshot_payload: Mapped[dict[str, object]] = mapped_column(JSONB)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OutcomeRecord(Base):
    __tablename__ = "reconciliation_outcomes"
    __table_args__ = (UniqueConstraint("run_id", "settlement_id"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), index=True)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("reconciliation_runs.id"), index=True)
    settlement_id: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    confidence: Mapped[str] = mapped_column(String(12), index=True)
    expected_minor: Mapped[int] = mapped_column(BigInteger)
    reported_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    evidence: Mapped[dict[str, object]] = mapped_column(JSONB)


class ReviewDecisionRecord(Base):
    __tablename__ = "review_decisions"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), index=True)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("reconciliation_runs.id"), index=True)
    settlement_id: Mapped[str] = mapped_column(String(64), index=True)
    decision: Mapped[str] = mapped_column(String(24))
    reason: Mapped[str] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AIInvestigationRecord(Base):
    __tablename__ = "ai_investigations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "external_investigation_id"),
        Index(
            "ix_ai_investigation_tenant_settlement_time", "tenant_id", "settlement_id", "created_at"
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), index=True)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("reconciliation_runs.id"), index=True)
    external_investigation_id: Mapped[str] = mapped_column(String(72), index=True)
    settlement_id: Mapped[str] = mapped_column(String(64), index=True)
    provider: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(128))
    prompt_template_version: Mapped[str] = mapped_column(String(64))
    evidence_ids: Mapped[list[str]] = mapped_column(JSONB)
    input_hash: Mapped[str] = mapped_column(String(64))
    response: Mapped[str] = mapped_column(Text)
    response_hash: Mapped[str] = mapped_column(String(64))
    actor: Mapped[str] = mapped_column(String(120))
    tool_calls: Mapped[list[str]] = mapped_column(JSONB, default=list)
    fallback_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempted_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    attempted_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AuditEventRecord(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_tenant_subject_time", "tenant_id", "subject_id", "created_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    subject_id: Mapped[str] = mapped_column(String(96), index=True)
    actor: Mapped[str] = mapped_column(String(120))
    details: Mapped[dict[str, object]] = mapped_column(JSONB)
    ai_involved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
