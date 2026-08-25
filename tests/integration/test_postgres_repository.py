import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine

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

    other_tenant = ReconciliationApplication(_repository(f"other-{uuid4().hex}"))
    with pytest.raises(LookupError):
        other_tenant.get_run(original.run_id)
    assert other_tenant.list_runs() == []
