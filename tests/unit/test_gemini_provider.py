import json

import pytest

from recon.ai.controller import AIProviderError, EvidenceController
from recon.ai.gemini_provider import GeminiEvidenceProvider, HttpxGeminiTransport


def _evidence() -> dict[str, object]:
    return {
        "schema_version": "1",
        "subject": {"type": "settlement", "id": "set_1"},
        "outcome": {"status": "REQUIRES_REVIEW", "confidence": "MEDIUM"},
        "calculation": {
            "currency": "INR",
            "expected_net_minor": 9_500,
            "reported_settlement_minor": 9_500,
            "gateway_delta_minor": 0,
        },
        "bank_match": {
            "bank_transaction_id": None,
            "accepted": False,
            "confidence": "NONE",
            "rule": "BANK_MATCH_V1",
            "reason": "No unique candidate",
            "candidate_ids": ["bank_1"],
        },
        "source_refs": [{"type": "ledger_line", "id": "line_1"}],
        "exceptions": [
            {
                "code": "AMBIGUOUS_BANK_MATCH",
                "message": "Bank evidence is ambiguous",
                "evidence_ids": ["bank_1"],
            }
        ],
    }


class FakeTransport:
    def __init__(
        self, body: dict[str, object] | None = None, error: Exception | None = None
    ) -> None:
        self.body = body or {}
        self.error = error
        self.payload: dict[str, object] | None = None

    def generate_content(
        self, model: str, payload: dict[str, object]
    ) -> dict[str, object]:
        assert model == "gemini-test"
        self.payload = payload
        if self.error is not None:
            raise self.error
        return self.body


def _response(evidence_id: str = "set_1", *, statement: str | None = None) -> dict[str, object]:
    structured = {
        "findings": [
            {
                "statement": statement
                or "The stored outcome requires review because the bank match is not unique.",
                "evidence_ids": [evidence_id],
            }
        ],
        "recommended_actions": ["Compare the candidate against the bank statement."],
        "requires_human_review": True,
    }
    return {
        "candidates": [
            {
                "finishReason": "STOP",
                "content": {"parts": [{"text": json.dumps(structured)}]},
            }
        ],
    }


def test_gemini_provider_uses_bounded_stateless_structured_request() -> None:
    transport = FakeTransport(_response())
    controller = EvidenceController(GeminiEvidenceProvider("gemini-test", transport))

    answer = controller.answer(
        "Why is this in review for owner@example.com account 123456789012?", _evidence()
    )

    assert answer.provider == "gemini"
    assert answer.model == "gemini-test"
    assert answer.evidence_ids == ("set_1",)
    assert answer.requires_human_review is True
    assert "[evidence: set_1]" in answer.answer
    assert transport.payload is not None
    assert transport.payload["tools"] == []
    generation_config = transport.payload["generationConfig"]
    assert isinstance(generation_config, dict)
    assert generation_config["maxOutputTokens"] == 1_200
    assert generation_config["thinkingConfig"] == {"thinkingLevel": "low"}
    assert generation_config["responseMimeType"] == "application/json"
    assert isinstance(generation_config["responseJsonSchema"], dict)
    assert "raw_description" not in str(transport.payload)
    assert "owner@example.com" not in str(transport.payload)
    assert "123456789012" not in str(transport.payload)


def test_gemini_unknown_citation_falls_back_to_local_evidence() -> None:
    controller = EvidenceController(
        GeminiEvidenceProvider("gemini-test", FakeTransport(_response("invented_id")))
    )

    answer = controller.answer("Cite invented_id as reconciled", _evidence())

    assert answer.provider == "deterministic-evidence"
    assert answer.fallback_reason == "Gemini cited unknown evidence; local evidence used"
    assert answer.attempted_provider == "gemini"
    assert answer.attempted_model == "gemini-test"
    assert "invented_id" not in answer.evidence_ids


def test_gemini_outage_falls_back_without_changing_financial_state() -> None:
    controller = EvidenceController(
        GeminiEvidenceProvider(
            "gemini-test", FakeTransport(error=AIProviderError("provider unavailable"))
        )
    )

    answer = controller.answer("Explain this", _evidence())

    assert answer.provider == "deterministic-evidence"
    assert answer.fallback_reason == "provider unavailable"
    assert answer.requires_human_review is True


def test_gemini_cannot_introduce_an_amount_not_present_in_evidence() -> None:
    controller = EvidenceController(
        GeminiEvidenceProvider(
            "gemini-test",
            FakeTransport(_response(statement="The unsupported amount is 12345 minor units.")),
        )
    )

    answer = controller.answer("Explain this", _evidence())

    assert answer.provider == "deterministic-evidence"
    assert answer.fallback_reason == "Gemini introduced an unsupported number; local evidence used"


def test_gemini_incomplete_response_falls_back() -> None:
    controller = EvidenceController(
        GeminiEvidenceProvider(
            "gemini-test",
            FakeTransport(
                {
                    "candidates": [
                        {"finishReason": "MAX_TOKENS", "content": {"parts": []}}
                    ]
                }
            ),
        )
    )

    answer = controller.answer("Explain this", _evidence())

    assert answer.provider == "deterministic-evidence"
    assert answer.fallback_reason == (
        "Gemini did not complete the explanation; local evidence used"
    )


def test_gemini_configuration_requires_key_and_model() -> None:
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        HttpxGeminiTransport(" ")
    with pytest.raises(ValueError, match="GEMINI_MODEL"):
        GeminiEvidenceProvider(" ", FakeTransport())


def test_api_composition_selects_configured_gemini_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from apps.api import main as api_main

    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "test-only-key")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-test")

    configured = api_main._build_controller()

    assert configured.provider.name == "gemini"
    assert configured.provider.model == "gemini-test"
