"""Read-only finance controller that cannot calculate or mutate financial state."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ControllerAnswer:
    answer: str
    evidence_ids: tuple[str, ...]
    provider: str
    model: str
    prompt_template_version: str
    advisory: bool
    requires_human_review: bool
    fallback_reason: str | None = None
    attempted_provider: str | None = None
    attempted_model: str | None = None


class AIProviderError(RuntimeError):
    """A safe, user-displayable provider failure that permits local fallback."""


class AIProvider(Protocol):
    """A provider receives only a redacted evidence bundle and must return cited prose."""

    name: str
    model: str
    prompt_template_version: str

    def explain(self, question: str, evidence: dict[str, object]) -> ControllerAnswer: ...


class DeterministicEvidenceProvider:
    """Safe local fallback that narrates values already calculated by the engine."""

    name = "deterministic-evidence"
    model = "local-rules"
    prompt_template_version = "deterministic-evidence-v1"

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
        return ControllerAnswer(
            answer=answer,
            evidence_ids=tuple(dict.fromkeys(evidence_ids)),
            provider=self.name,
            model=self.model,
            prompt_template_version=self.prompt_template_version,
            advisory=True,
            requires_human_review=str(outcome["status"]) != "RECONCILED",
        )


class EvidenceController:
    """Validate the evidence boundary before delegating narrative generation."""

    def __init__(
        self,
        provider: AIProvider | None = None,
        fallback: AIProvider | None = None,
    ) -> None:
        self.provider = provider or DeterministicEvidenceProvider()
        self.fallback = fallback or DeterministicEvidenceProvider()

    def answer(self, question: str, evidence: dict[str, object]) -> ControllerAnswer:
        if not question.strip():
            raise ValueError("question is required")
        required = {"subject", "outcome", "calculation", "bank_match", "exceptions", "source_refs"}
        if not required.issubset(evidence):
            raise ValueError("evidence bundle is incomplete")
        normalized_question = question.strip()
        try:
            answer = self.provider.explain(normalized_question, evidence)
        except AIProviderError as exc:
            if self.provider.name == self.fallback.name:
                raise
            answer = replace(
                self.fallback.explain(normalized_question, evidence),
                fallback_reason=str(exc),
                attempted_provider=self.provider.name,
                attempted_model=self.provider.model,
            )
        allowed_ids = evidence_identifiers(evidence)
        unknown_ids = set(answer.evidence_ids) - allowed_ids
        if unknown_ids:
            raise AIProviderError("provider returned citations outside the evidence bundle")
        outcome = evidence["outcome"]
        assert isinstance(outcome, dict)
        return replace(
            answer,
            requires_human_review=str(outcome["status"]) != "RECONCILED",
        )


def evidence_identifiers(evidence: dict[str, object]) -> set[str]:
    """Return the only identifiers an advisory provider is allowed to cite."""
    identifiers: set[str] = set()
    subject = evidence.get("subject")
    if isinstance(subject, dict) and subject.get("id") is not None:
        identifiers.add(str(subject["id"]))
    bank = evidence.get("bank_match")
    if isinstance(bank, dict):
        if bank.get("bank_transaction_id") is not None:
            identifiers.add(str(bank["bank_transaction_id"]))
        identifiers.update(str(item) for item in bank.get("candidate_ids", []))
    source_refs = evidence.get("source_refs")
    if isinstance(source_refs, list):
        for item in source_refs:
            if isinstance(item, dict) and item.get("id") is not None:
                identifiers.add(str(item["id"]))
    exceptions = evidence.get("exceptions")
    if isinstance(exceptions, list):
        for item in exceptions:
            if isinstance(item, dict):
                identifiers.update(str(value) for value in item.get("evidence_ids", []))
    return identifiers
