"""Allow-listed deterministic read tools available to the AI controller boundary."""

from __future__ import annotations

from dataclasses import dataclass

from recon.application.service import ReconciliationApplication

SETTLEMENT_EVIDENCE_TOOL = "get_settlement_evidence"

CURATED_FINANCE_QUESTIONS = (
    "Why did this settlement receive this status?",
    "What stored evidence prevents automatic reconciliation?",
    "Which source records should a finance reviewer inspect next?",
)


@dataclass(frozen=True, slots=True)
class EvidenceToolResult:
    """One bounded tool result plus the exact allow-listed call that produced it."""

    evidence: dict[str, object]
    tool_calls: tuple[str, ...]


class EvidenceQueryTools:
    """Expose only tenant-scoped, read-only evidence projections to the controller."""

    allowed_tools = (SETTLEMENT_EVIDENCE_TOOL,)

    def __init__(self, application: ReconciliationApplication) -> None:
        self._application = application

    def settlement_evidence(self, run_id: str, settlement_id: str) -> EvidenceToolResult:
        evidence = self._application.evidence(run_id, settlement_id)
        return EvidenceToolResult(evidence, (SETTLEMENT_EVIDENCE_TOOL,))
