"""Persistence boundary owned by the application layer."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from recon.application.service import AIInvestigation, AuditEvent, ReviewDecision, RunSnapshot


class RunRepository(Protocol):
    """Durable storage contract for immutable runs and append-only decisions."""

    def save_run(self, snapshot: RunSnapshot, audit_event: AuditEvent) -> None:
        """Persist a completed run and its completion audit event atomically."""
        ...

    def get_run(self, run_id: str) -> RunSnapshot | None:
        """Load one immutable run snapshot, or return None when absent."""
        ...

    def list_runs(self) -> list[RunSnapshot]:
        """Load completed snapshots newest first."""
        ...

    def save_review(self, run_id: str, review: ReviewDecision, audit_event: AuditEvent) -> None:
        """Append a review decision and its audit event atomically."""
        ...

    def audit_events(self, subject_id: str | None = None) -> list[AuditEvent]:
        """Load append-only audit events within the configured tenant."""
        ...

    def save_ai_investigation(
        self, investigation: AIInvestigation, audit_event: AuditEvent
    ) -> None:
        """Append an advisory investigation and its audit event atomically."""
        ...
