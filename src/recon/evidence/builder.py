"""Build a bounded explanation payload from deterministic outcomes."""

from __future__ import annotations

from recon.domain.models import ReconciliationOutcome


def build_settlement_evidence(outcome: ReconciliationOutcome) -> dict[str, object]:
    """Return integer-only financial evidence suitable for UI or redacted AI tools."""
    calculation = outcome.calculation
    return {
        "schema_version": "1",
        "subject": {"type": "settlement", "id": outcome.settlement_id},
        "outcome": {
            "status": outcome.status.value,
            "confidence": outcome.confidence.value,
        },
        "calculation": {
            "currency": calculation.currency,
            "payment_credits_minor": calculation.payment_credits_minor,
            "refund_debits_minor": calculation.refund_debits_minor,
            "transfer_net_minor": calculation.transfer_net_minor,
            "adjustment_net_minor": calculation.adjustment_net_minor,
            "fees_minor": calculation.fees_minor,
            "tax_minor": calculation.tax_minor,
            "expected_net_minor": calculation.expected_net_minor,
            "reported_settlement_minor": calculation.reported_minor,
            "gateway_delta_minor": calculation.gateway_delta_minor,
        },
        "bank_match": {
            "bank_transaction_id": outcome.bank_match.bank_transaction_id,
            "accepted": outcome.bank_match.accepted,
            "confidence": outcome.bank_match.confidence.value,
            "rule": outcome.bank_match.rule_version,
            "reason": outcome.bank_match.reason,
            "candidate_ids": list(outcome.bank_match.candidate_ids),
        },
        "source_refs": [
            {"type": "ledger_line", "id": line_id} for line_id in calculation.included_line_ids
        ],
        "exceptions": [
            {
                "code": item.code.value,
                "message": item.message,
                "affected_amount_minor": item.affected_amount_minor,
                "currency": item.currency,
                "severity": item.severity,
                "evidence_ids": list(item.evidence_ids),
            }
            for item in outcome.exceptions
        ],
        "rule_results": [
            {
                "rule": calculation.rule_version,
                "result": "PASS" if calculation.gateway_delta_minor == 0 else "FAIL",
            },
            {
                "rule": outcome.bank_match.rule_version,
                "result": "PASS" if outcome.bank_match.accepted else "REVIEW_OR_FAIL",
            },
        ],
    }
