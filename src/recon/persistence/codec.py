"""Explicit JSON codec for immutable run snapshots.

The codec is deliberately verbose: financial enums, timestamps, and integer amounts are
reconstructed through domain constructors rather than trusted as arbitrary objects.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, cast

from recon.domain.models import (
    BankMatch,
    BankTransaction,
    ConfidenceTier,
    ExceptionCase,
    ExceptionCode,
    LedgerType,
    MatchFeatures,
    MerchantOrder,
    Money,
    OutcomeStatus,
    Payment,
    PaymentStatus,
    ReconciliationOutcome,
    Refund,
    Settlement,
    SettlementCalculation,
    SettlementLedgerLine,
    SettlementStatus,
)
from recon.evaluation.metrics import EvaluationReport
from recon.synthetic.generator import GeneratedDataset, GeneratorConfig, GroundTruth

if TYPE_CHECKING:
    from recon.application.service import RunSnapshot

JsonObject = dict[str, object]


def _dt(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None:
        raise ValueError("persisted timestamp is missing timezone")
    return parsed


def _optional_dt(value: object) -> datetime | None:
    return None if value is None else _dt(value)


def _int(value: object) -> int:
    if not isinstance(value, (int, str)) or isinstance(value, bool):
        raise ValueError("persisted integer field has an invalid type")
    return int(value)


def _money(value: object) -> Money:
    data = cast(JsonObject, value)
    return Money(_int(data["amount_minor"]), str(data["currency"]))


def _json_value(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def encode_snapshot(snapshot: RunSnapshot) -> JsonObject:
    """Encode a RunSnapshot without relying on pickle or arbitrary class loading."""
    return cast(JsonObject, _json_value(asdict(snapshot)))


def _order(data: JsonObject) -> MerchantOrder:
    return MerchantOrder(
        str(data["order_id"]),
        _money(data["amount"]),
        str(data["status"]),
        _dt(data["created_at"]),
        str(data["merchant_reference"]),
    )


def _payment(data: JsonObject) -> Payment:
    return Payment(
        str(data["payment_id"]),
        str(data["order_id"]) if data["order_id"] is not None else None,
        _money(data["amount"]),
        PaymentStatus(str(data["status"])),
        _optional_dt(data["captured_at"]),
        str(data["method"]),
        _int(data["fee_minor"]),
        _int(data["tax_minor"]),
    )


def _refund(data: JsonObject) -> Refund:
    return Refund(
        str(data["refund_id"]),
        str(data["payment_id"]),
        _money(data["amount"]),
        str(data["status"]),
        _dt(data["created_at"]),
    )


def _settlement(data: JsonObject) -> Settlement:
    return Settlement(
        str(data["settlement_id"]),
        _money(data["amount"]),
        SettlementStatus(str(data["status"])),
        str(data["utr"]) if data["utr"] is not None else None,
        _dt(data["created_at"]),
        _optional_dt(data["processed_at"]),
        _int(data["source_fees_minor"]),
        _int(data["source_tax_minor"]),
    )


def _ledger(data: JsonObject) -> SettlementLedgerLine:
    return SettlementLedgerLine(
        str(data["line_id"]),
        str(data["settlement_id"]),
        str(data["entity_id"]),
        LedgerType(str(data["line_type"])),
        str(data["currency"]),
        _int(data["credit_minor"]),
        _int(data["debit_minor"]),
        _int(data["fee_minor"]),
        _int(data["tax_minor"]),
        bool(data["settled"]),
        bool(data["on_hold"]),
        _dt(data["created_at"]),
        _optional_dt(data["settled_at"]),
        str(data["payment_id"]) if data["payment_id"] is not None else None,
    )


def _bank(data: JsonObject) -> BankTransaction:
    return BankTransaction(
        str(data["bank_transaction_id"]),
        _dt(data["booked_at"]),
        _money(data["amount"]),
        str(data["direction"]),
        str(data["utr"]) if data["utr"] is not None else None,
        str(data["reference"]) if data["reference"] is not None else None,
    )


def _exception(data: JsonObject) -> ExceptionCase:
    return ExceptionCase(
        ExceptionCode(str(data["code"])),
        str(data["message"]),
        _int(data["affected_amount_minor"]),
        str(data["currency"]),
        tuple(str(item) for item in cast(list[object], data["evidence_ids"])),
        str(data["severity"]),
    )


def _calculation(data: JsonObject) -> SettlementCalculation:
    return SettlementCalculation(
        settlement_id=str(data["settlement_id"]),
        currency=str(data["currency"]),
        payment_credits_minor=_int(data["payment_credits_minor"]),
        refund_debits_minor=_int(data["refund_debits_minor"]),
        transfer_net_minor=_int(data["transfer_net_minor"]),
        adjustment_net_minor=_int(data["adjustment_net_minor"]),
        fees_minor=_int(data["fees_minor"]),
        tax_minor=_int(data["tax_minor"]),
        expected_net_minor=_int(data["expected_net_minor"]),
        reported_minor=_int(data["reported_minor"]),
        gateway_delta_minor=_int(data["gateway_delta_minor"]),
        included_line_ids=tuple(
            str(item) for item in cast(list[object], data["included_line_ids"])
        ),
        excluded_line_ids=tuple(
            str(item) for item in cast(list[object], data["excluded_line_ids"])
        ),
        rule_version=str(data["rule_version"]),
    )


def _bank_match(data: JsonObject) -> BankMatch:
    raw_features = data["features"]
    features = None
    if raw_features is not None:
        feature_data = cast(JsonObject, raw_features)
        features = MatchFeatures(
            bool(feature_data["currency_match"]),
            bool(feature_data["credit_direction"]),
            bool(feature_data["amount_exact"]),
            bool(feature_data["utr_exact"]),
            _int(feature_data["date_distance_days"]),
            bool(feature_data["within_normal_window"]),
        )
    return BankMatch(
        str(data["settlement_id"]),
        str(data["bank_transaction_id"]) if data["bank_transaction_id"] is not None else None,
        ConfidenceTier(str(data["confidence"])),
        bool(data["accepted"]),
        features,
        tuple(str(item) for item in cast(list[object], data["candidate_ids"])),
        str(data["rule_version"]),
        str(data["reason"]),
    )


def _outcome(data: JsonObject) -> ReconciliationOutcome:
    return ReconciliationOutcome(
        str(data["settlement_id"]),
        OutcomeStatus(str(data["status"])),
        ConfidenceTier(str(data["confidence"])),
        _calculation(cast(JsonObject, data["calculation"])),
        _bank_match(cast(JsonObject, data["bank_match"])),
        tuple(
            _exception(cast(JsonObject, item)) for item in cast(list[object], data["exceptions"])
        ),
    )


def decode_snapshot(payload: JsonObject) -> RunSnapshot:
    """Decode and validate a persisted payload into a RunSnapshot."""
    from recon.application.service import RunSnapshot

    dataset_data = cast(JsonObject, payload["dataset"])
    config_data = cast(JsonObject, dataset_data["config"])
    config = GeneratorConfig(
        seed=_int(config_data["seed"]),
        order_count=_int(config_data["order_count"]),
        payments_per_settlement=_int(config_data["payments_per_settlement"]),
        currency=str(config_data["currency"]),
        fee_rate=str(config_data["fee_rate"]),
        tax_rate=str(config_data["tax_rate"]),
        inject_anomalies=bool(config_data["inject_anomalies"]),
    )
    truth_data = cast(JsonObject, dataset_data["truth"])
    truth = GroundTruth(
        expected_status_by_settlement={
            str(key): str(value)
            for key, value in cast(
                dict[object, object], truth_data["expected_status_by_settlement"]
            ).items()
        },
        expected_bank_by_settlement={
            str(key): str(value) if value is not None else None
            for key, value in cast(
                dict[object, object], truth_data["expected_bank_by_settlement"]
            ).items()
        },
        anomaly_by_settlement={
            str(key): str(value)
            for key, value in cast(
                dict[object, object], truth_data["anomaly_by_settlement"]
            ).items()
        },
        expected_commercial_exception_codes=[
            str(item)
            for item in cast(list[object], truth_data["expected_commercial_exception_codes"])
        ],
    )
    dataset = GeneratedDataset(
        config,
        [_order(cast(JsonObject, item)) for item in cast(list[object], dataset_data["orders"])],
        [_payment(cast(JsonObject, item)) for item in cast(list[object], dataset_data["payments"])],
        [_refund(cast(JsonObject, item)) for item in cast(list[object], dataset_data["refunds"])],
        [
            _settlement(cast(JsonObject, item))
            for item in cast(list[object], dataset_data["settlements"])
        ],
        [
            _ledger(cast(JsonObject, item))
            for item in cast(list[object], dataset_data["ledger_lines"])
        ],
        [
            _bank(cast(JsonObject, item))
            for item in cast(list[object], dataset_data["bank_transactions"])
        ],
        truth,
    )
    raw_evaluation = payload["evaluation"]
    evaluation = None
    if raw_evaluation is not None:
        evaluation_data = cast(JsonObject, raw_evaluation)
        evaluation = EvaluationReport(
            settlement_count=_int(evaluation_data["settlement_count"]),
            correct_outcomes=_int(evaluation_data["correct_outcomes"]),
            outcome_accuracy=float(str(evaluation_data["outcome_accuracy"])),
            automatically_reconciled=_int(evaluation_data["automatically_reconciled"]),
            false_reconciled=_int(evaluation_data["false_reconciled"]),
            auto_reconcile_precision=float(str(evaluation_data["auto_reconcile_precision"])),
            review_cases=_int(evaluation_data["review_cases"]),
            unresolved_cases=_int(evaluation_data["unresolved_cases"]),
            confusion={
                str(expected): {
                    str(actual): _int(count)
                    for actual, count in cast(dict[object, object], values).items()
                }
                for expected, values in cast(
                    dict[object, object], evaluation_data["confusion"]
                ).items()
            },
            exception_precision=float(str(evaluation_data["exception_precision"])),
            exception_recall=float(str(evaluation_data["exception_recall"])),
            expected_commercial_exceptions=_int(evaluation_data["expected_commercial_exceptions"]),
            detected_commercial_exceptions=_int(evaluation_data["detected_commercial_exceptions"]),
        )
    return RunSnapshot(
        str(payload["run_id"]),
        _dt(payload["created_at"]),
        str(payload["ruleset_version"]),
        dataset,
        [_outcome(cast(JsonObject, item)) for item in cast(list[object], payload["outcomes"])],
        tuple(
            _exception(cast(JsonObject, item))
            for item in cast(list[object], payload["commercial_exceptions"])
        ),
        evaluation,
    )
