"""Core immutable financial records.

All money is represented in integer minor units. External identifiers remain strings and
are always scoped by tenant/source at persistence boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class PaymentStatus(StrEnum):
    CREATED = "created"
    AUTHORIZED = "authorized"
    CAPTURED = "captured"
    REFUNDED = "refunded"
    FAILED = "failed"


class SettlementStatus(StrEnum):
    CREATED = "created"
    PROCESSED = "processed"
    FAILED = "failed"


class LedgerType(StrEnum):
    PAYMENT = "payment"
    REFUND = "refund"
    TRANSFER = "transfer"
    ADJUSTMENT = "adjustment"


class ConfidenceTier(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    NONE = "NONE"


class OutcomeStatus(StrEnum):
    RECONCILED = "RECONCILED"
    RECONCILED_WITH_WARNINGS = "RECONCILED_WITH_WARNINGS"
    PARTIALLY_RECONCILED = "PARTIALLY_RECONCILED"
    UNRECONCILED = "UNRECONCILED"
    REQUIRES_REVIEW = "REQUIRES_REVIEW"
    INVALID_DATA = "INVALID_DATA"


class ExceptionCode(StrEnum):
    MISSING_SETTLEMENT_LEDGER = "MISSING_SETTLEMENT_LEDGER"
    SETTLEMENT_AMOUNT_MISMATCH = "SETTLEMENT_AMOUNT_MISMATCH"
    SETTLEMENT_FAILED = "SETTLEMENT_FAILED"
    HELD_LEDGER_LINE = "HELD_LEDGER_LINE"
    UNSETTLED_LEDGER_LINE = "UNSETTLED_LEDGER_LINE"
    CURRENCY_MISMATCH = "CURRENCY_MISMATCH"
    BANK_CREDIT_MISSING = "BANK_CREDIT_MISSING"
    BANK_CREDIT_DELAYED = "BANK_CREDIT_DELAYED"
    BANK_AMOUNT_MISMATCH = "BANK_AMOUNT_MISMATCH"
    UTR_MISSING = "UTR_MISSING"
    UTR_MISMATCH = "UTR_MISMATCH"
    DUPLICATE_BANK_CREDIT = "DUPLICATE_BANK_CREDIT"
    AMBIGUOUS_BANK_MATCH = "AMBIGUOUS_BANK_MATCH"
    ORDER_WITHOUT_CAPTURED_PAYMENT = "ORDER_WITHOUT_CAPTURED_PAYMENT"
    ORPHAN_PAYMENT = "ORPHAN_PAYMENT"
    PAYMENT_AMOUNT_MISMATCH = "PAYMENT_AMOUNT_MISMATCH"
    ORPHAN_REFUND = "ORPHAN_REFUND"
    REFUND_TOTAL_EXCEEDS_PAYMENT = "REFUND_TOTAL_EXCEEDS_PAYMENT"
    CONFLICTING_SOURCE_RECORD = "CONFLICTING_SOURCE_RECORD"
    MALFORMED_RECORD = "MALFORMED_RECORD"


@dataclass(frozen=True, slots=True)
class Money:
    """An exact amount in a single ISO currency."""

    amount_minor: int
    currency: str

    def __post_init__(self) -> None:
        normalized = self.currency.upper().strip()
        if len(normalized) != 3 or not normalized.isalpha():
            raise ValueError("currency must be a three-letter ISO code")
        if not -(2**63) <= self.amount_minor < 2**63:
            raise OverflowError("money amount exceeds signed BIGINT range")
        object.__setattr__(self, "currency", normalized)

    def _same_currency(self, other: Money) -> None:
        if self.currency != other.currency:
            raise ValueError(f"currency mismatch: {self.currency} != {other.currency}")

    def __add__(self, other: Money) -> Money:
        self._same_currency(other)
        return Money(self.amount_minor + other.amount_minor, self.currency)

    def __sub__(self, other: Money) -> Money:
        self._same_currency(other)
        return Money(self.amount_minor - other.amount_minor, self.currency)


@dataclass(frozen=True, slots=True)
class MerchantOrder:
    order_id: str
    amount: Money
    status: str
    created_at: datetime
    merchant_reference: str


@dataclass(frozen=True, slots=True)
class Payment:
    payment_id: str
    order_id: str | None
    amount: Money
    status: PaymentStatus
    captured_at: datetime | None
    method: str
    fee_minor: int = 0
    tax_minor: int = 0


@dataclass(frozen=True, slots=True)
class Refund:
    refund_id: str
    payment_id: str
    amount: Money
    status: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class Settlement:
    settlement_id: str
    amount: Money
    status: SettlementStatus
    utr: str | None
    created_at: datetime
    processed_at: datetime | None
    source_fees_minor: int = 0
    source_tax_minor: int = 0


@dataclass(frozen=True, slots=True)
class SettlementLedgerLine:
    """One canonical Razorpay settlement recon transaction line.

    Credit, debit, fee, and tax are non-negative source components. The versioned V1
    mapping is credit - debit - fee - tax and is applied exactly once.
    """

    line_id: str
    settlement_id: str
    entity_id: str
    line_type: LedgerType
    currency: str
    credit_minor: int
    debit_minor: int
    fee_minor: int
    tax_minor: int
    settled: bool
    on_hold: bool
    created_at: datetime
    settled_at: datetime | None
    payment_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "currency", self.currency.upper().strip())
        for value in (self.credit_minor, self.debit_minor, self.fee_minor, self.tax_minor):
            if value < 0:
                raise ValueError("ledger components must be non-negative")
        if self.credit_minor and self.debit_minor:
            raise ValueError("a ledger line cannot be both a credit and debit")

    @property
    def net_effect_minor(self) -> int:
        return self.credit_minor - self.debit_minor - self.fee_minor - self.tax_minor


@dataclass(frozen=True, slots=True)
class BankTransaction:
    bank_transaction_id: str
    booked_at: datetime
    amount: Money
    direction: str
    utr: str | None
    reference: str | None


@dataclass(frozen=True, slots=True)
class SettlementCalculation:
    settlement_id: str
    currency: str
    payment_credits_minor: int
    refund_debits_minor: int
    transfer_net_minor: int
    adjustment_net_minor: int
    fees_minor: int
    tax_minor: int
    expected_net_minor: int
    reported_minor: int
    gateway_delta_minor: int
    included_line_ids: tuple[str, ...]
    excluded_line_ids: tuple[str, ...]
    rule_version: str = "SETTLEMENT_NET_V1"


@dataclass(frozen=True, slots=True)
class MatchFeatures:
    currency_match: bool
    credit_direction: bool
    amount_exact: bool
    utr_exact: bool
    date_distance_days: int
    within_normal_window: bool


@dataclass(frozen=True, slots=True)
class BankMatch:
    settlement_id: str
    bank_transaction_id: str | None
    confidence: ConfidenceTier
    accepted: bool
    features: MatchFeatures | None
    candidate_ids: tuple[str, ...]
    rule_version: str
    reason: str


@dataclass(frozen=True, slots=True)
class ExceptionCase:
    code: ExceptionCode
    message: str
    affected_amount_minor: int
    currency: str
    evidence_ids: tuple[str, ...]
    severity: str = "MATERIAL"


@dataclass(frozen=True, slots=True)
class ReconciliationOutcome:
    settlement_id: str
    status: OutcomeStatus
    confidence: ConfidenceTier
    calculation: SettlementCalculation
    bank_match: BankMatch
    exceptions: tuple[ExceptionCase, ...] = field(default_factory=tuple)
