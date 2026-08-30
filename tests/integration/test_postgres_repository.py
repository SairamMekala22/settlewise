import os
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine

from recon.ai.controller import EvidenceController
from recon.application.service import ReconciliationApplication
from recon.persistence.models import Base
from recon.persistence.postgres import PostgresRunRepository

DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    DATABASE_URL is None,
    reason="TEST_DATABASE_URL is required for PostgreSQL durability tests",
)


def _repository(tenant_slug: str) -> PostgresRunRepository:
    assert DATABASE_URL is not None
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    Base.metadata.create_all(engine)
    return PostgresRunRepository(DATABASE_URL, tenant_slug=tenant_slug, engine=engine)


def test_run_survives_application_restart_and_is_tenant_isolated() -> None:
    tenant_slug = f"test-{uuid4().hex}"
    first_app = ReconciliationApplication(_repository(tenant_slug))
    original = first_app.create_demo_run(seed=991, order_count=200)

    restarted_app = ReconciliationApplication(_repository(tenant_slug))
    restored = restarted_app.get_run(original.run_id)
    assert restored == original
    assert restarted_app.analytics(original.run_id)["settlement_count"] == len(original.outcomes)
    assert [item.run_id for item in restarted_app.list_runs()] == [original.run_id]

    settlement_id = original.outcomes[0].settlement_id
    restarted_app.review(
        original.run_id,
        settlement_id,
        decision="CONFIRMED",
        reason="Restart durability integration test",
        actor="integration-test",
    )
    after_second_restart = ReconciliationApplication(_repository(tenant_slug))
    review_events = after_second_restart.audit_events(subject_id=settlement_id)
    assert review_events[-1].event_type == "REVIEW_DECISION_RECORDED"

    evidence = after_second_restart.evidence(original.run_id, settlement_id)
    answer = EvidenceController().answer("Explain the stored result", evidence)
    after_second_restart.record_ai_investigation(
        original.run_id,
        settlement_id,
        question="Explain the stored result",
        evidence=evidence,
        provider=answer.provider,
        model=answer.model,
        prompt_template_version=answer.prompt_template_version,
        evidence_ids=answer.evidence_ids,
        response=answer.answer,
        actor="integration-test",
        fallback_reason=answer.fallback_reason,
        attempted_provider=answer.attempted_provider,
        attempted_model=answer.attempted_model,
        tool_calls=("get_settlement_evidence",),
    )
    after_third_restart = ReconciliationApplication(_repository(tenant_slug))
    investigation_events = after_third_restart.audit_events(subject_id=settlement_id)
    assert investigation_events[-1].event_type == "AI_INVESTIGATION_RECORDED"
    assert investigation_events[-1].ai_involved is False
    assert investigation_events[-1].timestamp.utcoffset() == timedelta(0)

    other_tenant = ReconciliationApplication(_repository(f"other-{uuid4().hex}"))
    with pytest.raises(LookupError):
        other_tenant.get_run(original.run_id)
    assert other_tenant.list_runs() == []
