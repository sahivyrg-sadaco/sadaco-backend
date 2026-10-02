"""
Payment helpers. Client invoices, payables and receivables now live in apps.finance;
the Payment model here stores the client payments recorded against client invoices.
"""
import re

TERMS_DAYS = {
    "net 30":                              30,
    "net 60":                              60,
    "net 90":                              90,
    "net 15":                              15,
    "100% prepagado":                       0,
    "prepaid":                              0,
    "cash":                                 0,
    "letter of credit (carta de crédito)": 45,
    "30% anticipado / 70% contra entrega": 30,
    "50% anticipado / 50% contra entrega": 30,
    "30 days":                             30,
    "60 days":                             60,
}


def parse_payment_terms_days(terms: str) -> int:
    """Return the number of days until payment is due from invoice date."""
    if not terms:
        return 30
    key = terms.strip().lower()
    if key in TERMS_DAYS:
        return TERMS_DAYS[key]
    m = re.search(r'\d+', key)
    if m:
        return int(m.group())
    return 30
