"""OpenAI Responses API adapter for evidence-bounded advisory explanations."""

from __future__ import annotations

from typing import Protocol, cast

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


class ResponsesTransport(Protocol):
    """Typed boundary around the external Responses API."""

    def create_response(self, payload: dict[str, object]) -> dict[str, object]: ...


class HttpxOpenAITransport:
    """Minimal HTTPS transport; secrets stay in headers and outside audit payloads."""

    def __init__(self, api_key: str, *, timeout_seconds: float = 20.0) -> None:
        if not api_key.strip():
            raise ValueError("OPENAI_API_KEY is required when AI_PROVIDER=openai")
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds

    def create_response(self, payload: dict[str, object]) -> dict[str, object]:
        try:
            response = httpx.post(
                "https://api.openai.com/v1/responses",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=self._timeout_seconds,
            )
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise AIProviderError("OpenAI response was unavailable; local evidence used") from exc
        if not isinstance(body, dict):
            raise AIProviderError("OpenAI returned an invalid response; local evidence used")
        return cast(dict[str, object], body)


class OpenAIEvidenceProvider:
    """Generate prose only; deterministic evidence remains authoritative."""

    name = "openai"
    prompt_template_version = PROMPT_TEMPLATE_VERSION

    def __init__(self, model: str, transport: ResponsesTransport) -> None:
        if not model.strip():
            raise ValueError("OPENAI_MODEL is required when AI_PROVIDER=openai")
        self.model = model.strip()
        self._transport = transport

    def explain(self, question: str, evidence: dict[str, object]) -> ControllerAnswer:
        payload: dict[str, object] = {
            "model": self.model,
            "instructions": PROVIDER_INSTRUCTIONS,
            "input": redacted_provider_input(question, evidence),
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "settlement_investigation",
                    "strict": True,
                    "schema": OUTPUT_SCHEMA,
                }
            },
            "max_output_tokens": 1_200,
            "store": False,
            "tools": [],
        }
        raw_response = self._transport.create_response(payload)
        parsed = _parse_structured_output(raw_response)
        return validated_controller_answer(
            parsed,
            evidence,
            provider_name=self.name,
            provider_label="OpenAI",
            model=self.model,
            prompt_template_version=self.prompt_template_version,
        )


def _parse_structured_output(response: dict[str, object]) -> dict[str, object]:
    output = response.get("output")
    if not isinstance(output, list):
        raise AIProviderError("OpenAI returned no output; local evidence used")
    for item in output:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "refusal":
                raise AIProviderError("OpenAI declined the request; local evidence used")
            if block.get("type") == "output_text" and isinstance(block.get("text"), str):
                return decode_structured_text(cast(str, block["text"]), provider_label="OpenAI")
    raise AIProviderError("OpenAI returned no explanation; local evidence used")
