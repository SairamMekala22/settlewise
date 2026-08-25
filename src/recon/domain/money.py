"""Central rate-to-minor-unit conversion policy."""

from decimal import ROUND_HALF_UP, Decimal

from recon.domain.models import Money

CURRENCY_EXPONENTS: dict[str, int] = {"INR": 2, "USD": 2, "JPY": 0, "KWD": 3}


def major_to_money(value: str | Decimal, currency: str) -> Money:
    """Convert an explicit decimal major-unit value using the central rounding policy."""
    normalized = currency.upper()
    exponent = CURRENCY_EXPONENTS.get(normalized)
    if exponent is None:
        raise ValueError(f"unsupported currency: {normalized}")
    scale = Decimal(10) ** exponent
    amount_minor = int((Decimal(value) * scale).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return Money(amount_minor, normalized)


def percentage_minor(base_minor: int, rate: Decimal) -> int:
    """Calculate a percentage over an integer amount and round once to a minor unit."""
    return int((Decimal(base_minor) * rate).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
