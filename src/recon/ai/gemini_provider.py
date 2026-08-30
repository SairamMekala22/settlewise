"""Gemini GenerateContent API adapter for evidence-bounded advisory explanations."""

from __future__ import annotations

from typing import Protocol, cast
from urllib.parse import quote

import httpx

from recon.ai.controller import AIProviderError, ControllerAnswer
from recon.ai.provider_common import (
    OUTPUT_SCHEMA,
    PROMPT_TEMPLATE_VERSION,
    PROVIDER_INSTRUCTIONS,
    decode_structured_text,
    redacted_provider_input,
    validated_controller_answer,
)

_MODEL_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class ContentTransport(Protocol):
    """Typed boundary around the external Gemini GenerateContent API."""

    def generate_content(
        self, model: str, payload: dict[str, object]
    ) -> dict[str, object]: ...


class HttpxGeminiTransport:
    """Minimal HTTPS transport that keeps the Gemini key out of request bodies."""

    def __init__(self, api_key: str, *, timeout_seconds: float = 20.0) -> None:
        if not api_key.strip():
            raise ValueError("GEMINI_API_KEY is required when AI_PROVIDER=gemini")
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds

    def generate_content(
        self, model: str, payload: dict[str, object]
    ) -> dict[str, object]:
        url = _MODEL_URL.format(model=quote(model, safe=""))
        try:
            response = httpx.post(
                url,
                headers={
                    "x-goog-api-key": self._api_key,
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=self._timeout_seconds,
            )
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise AIProviderError("Gemini response was unavailable; local evidence used") from exc
        if not isinstance(body, dict):
            raise AIProviderError("Gemini returned an invalid response; local evidence used")
        return cast(dict[str, object], body)


class GeminiEvidenceProvider:
    """Generate advisory prose while deterministic reconciliation remains authoritative."""

    name = "gemini"
    prompt_template_version = PROMPT_TEMPLATE_VERSION

    def __init__(self, model: str, transport: ContentTransport) -> None:
        if not model.strip():
            raise ValueError("GEMINI_MODEL is required when AI_PROVIDER=gemini")
        self.model = model.strip()
        self._transport = transport

    def explain(self, question: str, evidence: dict[str, object]) -> ControllerAnswer:
        payload: dict[str, object] = {
            "system_instruction": {"parts": [{"text": PROVIDER_INSTRUCTIONS}]},
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": redacted_provider_input(question, evidence)}],
                }
            ],
            "generationConfig": {
                "maxOutputTokens": 1_200,
                "thinkingConfig": {"thinkingLevel": "low"},
                "responseMimeType": "application/json",
                "responseJsonSchema": OUTPUT_SCHEMA,
            },
            "tools": [],
        }
        response = self._transport.generate_content(self.model, payload)
        parsed = _parse_structured_output(response)
        return validated_controller_answer(
            parsed,
            evidence,
            provider_name=self.name,
            provider_label="Gemini",
            model=self.model,
            prompt_template_version=self.prompt_template_version,
        )


def _parse_structured_output(response: dict[str, object]) -> dict[str, object]:
    candidates = response.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise AIProviderError("Gemini returned no output; local evidence used")
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        if candidate.get("finishReason") not in {None, "STOP"}:
            raise AIProviderError("Gemini did not complete the explanation; local evidence used")
        content = candidate.get("content")
        if not isinstance(content, dict):
            continue
        parts = content.get("parts")
        if not isinstance(parts, list):
            continue
        for block in parts:
            if (
                isinstance(block, dict)
                and isinstance(block.get("text"), str)
            ):
                return decode_structured_text(cast(str, block["text"]), provider_label="Gemini")
    raise AIProviderError("Gemini returned no explanation; local evidence used")
