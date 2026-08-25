"""Read-only finance controller that cannot calculate or mutate financial state."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ControllerAnswer:
    answer: str
    evidence_ids: tuple[str, ...]
    provider: str
    advisory: bool


class AIProvider(Protocol):
    """A provider receives only a redacted evidence bundle and must return cited prose."""

    name: str

    def explain(self, question: str, evidence: dict[str, object]) -> ControllerAnswer: ...


class DeterministicEvidenceProvider:
    """Safe local fallback that narrates values already calculated by the engine."""

    name = "deterministic-evidence"

    def explain(self, question: str, evidence: dict[str, object]) -> ControllerAnswer:
        del question
        subject = evidence["subject"]
        outcome = evidence["outcome"]
        calculation = evidence["calculation"]
        exceptions = evidence["exceptions"]
        bank = evidence["bank_match"]
        assert isinstance(subject, dict)
        assert isinstance(outcome, dict)
        assert isinstance(calculation, dict)
        assert isinstance(exceptions, list)
        assert isinstance(bank, dict)
        settlement_id = str(subject["id"])
        currency = str(calculation["currency"])
        expected = int(calculation["expected_net_minor"])
        reported = int(calculation["reported_settlement_minor"])
        delta = int(calculation["gateway_delta_minor"])
        evidence_ids = [settlement_id]
        evidence_ids.extend(str(item) for item in bank.get("candidate_ids", []))
        for exception in exceptions:
            if isinstance(exception, dict):
                evidence_ids.extend(str(item) for item in exception.get("evidence_ids", []))
        cause = (
            "; ".join(str(item["message"]) for item in exceptions if isinstance(item, dict))
            if exceptions
            else (
                "No exception was found: the ledger, reported settlement, "
                "and bank match all passed."
            )
        )
        answer = (
            f"Settlement {settlement_id} is {outcome['status']} with "
            f"{outcome['confidence']} confidence. The deterministic ledger expected "
            f"{expected} minor units {currency}; the reported amount was "
            f"{reported}, a gateway delta of {delta}. {cause} Bank rule: {bank['reason']}"
        )
        return ControllerAnswer(answer, tuple(dict.fromkeys(evidence_ids)), self.name, True)


class EvidenceController:
    """Validate the evidence boundary before delegating narrative generation."""

    def __init__(self, provider: AIProvider | None = None) -> None:
        self.provider = provider or DeterministicEvidenceProvider()

    def answer(self, question: str, evidence: dict[str, object]) -> ControllerAnswer:
        if not question.strip():
            raise ValueError("question is required")
        required = {"subject", "outcome", "calculation", "bank_match", "exceptions", "source_refs"}
        if not required.issubset(evidence):
            raise ValueError("evidence bundle is incomplete")
        return self.provider.explain(question.strip(), evidence)
