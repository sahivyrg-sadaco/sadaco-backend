# =============================================================================
# apps/core/currency.py — Multi-currency support for SADACO ERP
#
# Provides:
#   - Currency symbol lookup
#   - Consistent amount formatting  (e.g. "$ 1,234.56"  or  "Bs. 1,234.56")
#   - Deal total calculations in both deal currency and USD equivalent
# =============================================================================

# ── Currency symbols ──────────────────────────────────────────────────────────
CURRENCY_SYMBOLS = {
    "USD": "$",
    "EUR": "€",
    "VES": "Bs.",
    "COP": "COP $",
    "BRL": "R$",
    "GBP": "£",
    "CAD": "CA$",
}

# Currencies that display after the number vs. before
SYMBOL_AFTER = {"EUR"}   # e.g. "1.234,56 €"


def symbol(currency: str) -> str:
    """Return the display symbol for a currency code."""
    return CURRENCY_SYMBOLS.get(currency.upper(), currency)


def fmt(amount, currency: str = "USD", decimals: int = 2) -> str:
    """
    Format a monetary amount with its currency symbol.
    Examples:
        fmt(1234.5, "USD")  → "$ 1,234.50"
        fmt(1234.5, "VES")  → "Bs. 1,234.50"
        fmt(1234.5, "EUR")  → "1,234.50 €"
    """
    try:
        value = float(amount or 0)
    except (TypeError, ValueError):
        value = 0.0
    formatted = f"{value:,.{decimals}f}"
    sym = symbol(currency)
    if currency.upper() in SYMBOL_AFTER:
        return f"{formatted} {sym}"
    return f"{sym} {formatted}"


def to_usd(amount, currency: str, exchange_rate: float) -> float:
    """
    Convert an amount to USD using the stored exchange rate.
    exchange_rate is always expressed as: 1 USD = exchange_rate LOCAL.
    So: usd_value = local_amount / exchange_rate
    For USD deals the rate is 1.0, so this is a no-op.
    """
    try:
        rate = float(exchange_rate or 1)
        if rate == 0:
            rate = 1.0
        return float(amount or 0) / rate
    except (TypeError, ValueError):
        return 0.0


def deal_totals(items: list, currency: str, exchange_rate: float) -> dict:
    """
    Calculate cost/price totals for a deal from its line items.

    Args:
        items         : list of deal items (dicts with qty, unit_cost, unit_price)
        currency      : deal currency code e.g. "USD", "VES"
        exchange_rate : 1 USD = exchange_rate units of currency

    Returns a dict with:
        total_cost, total_price, total_cost_usd, total_price_usd,
        margin_amount, margin_pct, currency, exchange_rate, is_usd,
        and pre-formatted fmt_* strings for convenience.
    """
    total_cost = 0.0
    total_price = 0.0

    for item in items:
        qty   = float(item.get("qty") or 0)
        cost  = float(item.get("unit_cost") or 0)
        price = float(item.get("unit_price") or 0)
        total_cost  += qty * cost
        total_price += qty * price

    margin_amount = total_price - total_cost
    margin_pct    = (margin_amount / total_price * 100) if total_price > 0 else 0.0
    rate          = float(exchange_rate or 1) or 1.0
    is_usd        = currency.upper() == "USD"

    return {
        "total_cost":       round(total_cost, 2),
        "total_price":      round(total_price, 2),
        "total_cost_usd":   round(total_cost / rate, 2),
        "total_price_usd":  round(total_price / rate, 2),
        "margin_amount":    round(margin_amount, 2),
        "margin_pct":       round(margin_pct, 1),
        "currency":         currency,
        "exchange_rate":    rate,
        "is_usd":           is_usd,
        "fmt_cost":         fmt(total_cost, currency),
        "fmt_price":        fmt(total_price, currency),
        "fmt_cost_usd":     fmt(total_cost / rate, "USD"),
        "fmt_price_usd":    fmt(total_price / rate, "USD"),
        "fmt_margin":       fmt(margin_amount, currency),
        "fmt_rate":         f"1 USD = {fmt(rate, currency, decimals=4)}",
    }
