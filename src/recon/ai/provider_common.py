"""Shared safety contract for external evidence-explanation providers."""

from __future__ import annotations

import json
import re
from typing import cast

from recon.ai.controller import AIProviderError, ControllerAnswer, evidence_identifiers

PROMPT_TEMPLATE_VERSION = "settlement-investigation-v1"

PROVIDER_INSTRUCTIONS = """You are a read-only settlement reconciliation investigator.
Use only the supplied deterministic evidence. Never calculate, infer a new amount, change a
status, or invent an identifier. Each factual finding must cite one or more supplied evidence IDs.
Recommendations are advisory. If evidence is incomplete, conflicting, or the deterministic status
is not RECONCILED, say human review is required. Do not reveal hidden reasoning."""

# This deliberately uses the JSON Schema subset supported by both configured providers. Semantic
# limits are checked again locally because provider output is always untrusted.
OUTPUT_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "minItems": 1,
            "maxItems": 6,
            "items": {
                "type": "object",
                "properties": {
                    "statement": {"type": "string"},
                    "evidence_ids": {
                        "type": "array",
                        "minItems": 1,
                        "items": {"type": "string"},
                    },
                },
                "required": ["statement", "evidence_ids"],
                "additionalProperties": False,
            },
        },
        "recommended_actions": {
            "type": "array",
            "maxItems": 4,
            "items": {"type": "string"},
        },
        "requires_human_review": {"type": "boolean"},
    },
    "required": ["findings", "recommended_actions", "requires_human_review"],
    "additionalProperties": False,
}

_EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_LONG_NUMBER_PATTERN = re.compile(r"(?<!\w)\d{8,}(?!\w)")
_STANDALONE_NUMBER_PATTERN = re.compile(r"(?<![\w.])-?\d[\d,]*(?![\w.])")


def redacted_provider_input(question: str, evidence: dict[str, object]) -> str:
    """Serialize only a redacted question and the bounded evidence bundle."""
    redacted = _EMAIL_PATTERN.sub("[redacted-email]", question)
    redacted = _LONG_NUMBER_PATTERN.sub("[redacted-number]", redacted)
    return json.dumps(
        {"question": redacted, "evidence": evidence},
        sort_keys=True,
        separators=(",", ":"),
    )


def decode_structured_text(text: str, *, provider_label: str) -> dict[str, object]:
    """Decode a provider's schema-constrained text without trusting its declared format."""
    try:
        decoded = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AIProviderError(
            f"{provider_label} returned invalid structured output; local evidence used"
        ) from exc
    if not isinstance(decoded, dict):
        raise AIProviderError(
            f"{provider_label} returned invalid structured output; local evidence used"
        )
    return cast(dict[str, object], decoded)


def validated_controller_answer(
    parsed: dict[str, object],
    evidence: dict[str, object],
    *,
    provider_name: str,
    provider_label: str,
    model: str,
    prompt_template_version: str = PROMPT_TEMPLATE_VERSION,
) -> ControllerAnswer:
    """Validate citations, values, and output limits before rendering advisory prose."""
    allowed_ids = evidence_identifiers(evidence)
    findings = parsed.get("findings")
    actions = parsed.get("recommended_actions")
    review = parsed.get("requires_human_review")
    if not isinstance(findings, list) or not 1 <= len(findings) <= 6:
        raise AIProviderError(f"{provider_label} returned no cited findings; local evidence used")
    if (
        not isinstance(actions, list)
        or len(actions) > 4
        or not all(isinstance(item, str) and 0 < len(item.strip()) <= 500 for item in actions)
    ):
        raise AIProviderError(f"{provider_label} returned invalid actions; local evidence used")
    if not isinstance(review, bool):
        raise AIProviderError(
            f"{provider_label} returned an invalid review decision; local evidence used"
        )

    lines: list[str] = []
    cited_ids: list[str] = []
    for finding in findings:
        if not isinstance(finding, dict):
            raise AIProviderError(
                f"{provider_label} returned an invalid finding; local evidence used"
            )
        statement = finding.get("statement")
        ids = finding.get("evidence_ids")
        if not isinstance(statement, str) or not 0 < len(statement.strip()) <= 800:
            raise AIProviderError(
                f"{provider_label} returned an empty finding; local evidence used"
            )
        if (
            not isinstance(ids, list)
            or not ids
            or not all(isinstance(item, str) for item in ids)
        ):
            raise AIProviderError(
                f"{provider_label} omitted finding citations; local evidence used"
            )
        if set(ids) - allowed_ids:
            raise AIProviderError(
                f"{provider_label} cited unknown evidence; local evidence used"
            )
        _validate_supported_numbers(statement, evidence, provider_label=provider_label)
        cited_ids.extend(ids)
        lines.append(f"{statement.strip()} [evidence: {', '.join(ids)}]")
    if actions:
        lines.append("Recommended actions (advisory): " + "; ".join(actions))
    return ControllerAnswer(
        answer="\n".join(lines),
        evidence_ids=tuple(dict.fromkeys(cited_ids)),
        provider=provider_name,
        model=model,
        prompt_template_version=prompt_template_version,
        advisory=True,
        requires_human_review=review,
    )


def _validate_supported_numbers(
    statement: str,
    evidence: dict[str, object],
    *,
    provider_label: str,
) -> None:
    supported: set[int] = set()

    def collect(value: object) -> None:
        if isinstance(value, bool):
            return
        if isinstance(value, int):
            supported.add(value)
        elif isinstance(value, dict):
            for nested in value.values():
                collect(nested)
        elif isinstance(value, list):
            for nested in value:
                collect(nested)

    collect(evidence)
    for token in _STANDALONE_NUMBER_PATTERN.findall(statement):
        if int(token.replace(",", "")) not in supported:
            raise AIProviderError(
                f"{provider_label} introduced an unsupported number; local evidence used"
            )
