"""Conservative settlement-to-bank matching."""

from __future__ import annotations

import re
import unicodedata

from recon.domain.models import (
    BankMatch,
    BankTransaction,
    ConfidenceTier,
    MatchFeatures,
    Settlement,
)

_SEPARATOR_RE = re.compile(r"[\s\-_/.:]+")


def normalize_reference(value: str | None) -> str | None:
    """Normalize safe separators without deleting source alphanumeric content."""
    if value is None:
        return None
    normalized = unicodedata.normalize("NFKC", value).upper().strip()
    normalized = _SEPARATOR_RE.sub("", normalized)
    return normalized or None


def _days_between(settlement: Settlement, bank: BankTransaction) -> int:
    start = settlement.processed_at or settlement.created_at
    return (bank.booked_at.date() - start.date()).days


def match_settlement_to_bank(
    settlement: Settlement,
    bank_transactions: list[BankTransaction],
    *,
    normal_window_days: int = 3,
    broad_window_days: int = 7,
) -> BankMatch:
    """Match only uniquely proven bank credits; route weaker candidates to review."""
    settlement_utr = normalize_reference(settlement.utr)
    candidates: list[tuple[BankTransaction, MatchFeatures]] = []

    for bank in bank_transactions:
        days = _days_between(settlement, bank)
        currency_match = bank.amount.currency == settlement.amount.currency
        credit_direction = bank.direction.upper() == "CREDIT"
        if not currency_match or not credit_direction or not -1 <= days <= broad_window_days:
            continue
        bank_refs = {normalize_reference(bank.utr), normalize_reference(bank.reference)}
        features = MatchFeatures(
            currency_match=True,
            credit_direction=True,
            amount_exact=bank.amount.amount_minor == settlement.amount.amount_minor,
            utr_exact=settlement_utr is not None and settlement_utr in bank_refs,
            date_distance_days=days,
            within_normal_window=0 <= days <= normal_window_days,
        )
        if features.amount_exact or features.utr_exact:
            candidates.append((bank, features))

    candidate_ids = tuple(item[0].bank_transaction_id for item in candidates)
    high = [
        item
        for item in candidates
        if item[1].utr_exact and item[1].amount_exact and item[1].within_normal_window
    ]
    if len(high) == 1:
        bank, features = high[0]
        return BankMatch(
            settlement.settlement_id,
            bank.bank_transaction_id,
            ConfidenceTier.HIGH,
            True,
            features,
            candidate_ids,
            "BANK_EXACT_UTR_AMOUNT_V1",
            "Unique exact UTR, amount, currency, direction, and normal date window",
        )
    if len(high) > 1:
        return BankMatch(
            settlement.settlement_id,
            None,
            ConfidenceTier.LOW,
            False,
            None,
            candidate_ids,
            "BANK_AMBIGUITY_V1",
            "Multiple candidates satisfy the automatic rule",
        )

    medium = [
        item
        for item in candidates
        if item[1].amount_exact and (item[1].within_normal_window or item[1].utr_exact)
    ]
    if len(medium) == 1:
        bank, features = medium[0]
        reason = (
            "Exact UTR and amount outside the normal date window"
            if features.utr_exact
            else "Unique exact amount in window but UTR is absent or does not match"
        )
        return BankMatch(
            settlement.settlement_id,
            bank.bank_transaction_id,
            ConfidenceTier.MEDIUM,
            False,
            features,
            candidate_ids,
            "BANK_REVIEW_CANDIDATE_V1",
            reason,
        )

    if candidates:
        return BankMatch(
            settlement.settlement_id,
            None,
            ConfidenceTier.LOW,
            False,
            None,
            candidate_ids,
            "BANK_AMBIGUITY_V1",
            "Weak or competing bank candidates require review",
        )
    return BankMatch(
        settlement.settlement_id,
        None,
        ConfidenceTier.NONE,
        False,
        None,
        (),
        "BANK_NO_CANDIDATE_V1",
        "No bank credit candidate satisfies currency, direction, reference/amount, and date gates",
    )
