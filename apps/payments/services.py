"""
Payments & Accounts Receivable services.

Ported from the Flask prototype's modules/payments.py.
Uses django.db.connection instead of psycopg2; SQL is preserved as-is.
"""
import re
from datetime import date, datetime, timedelta

from django.db import connection


# ── Payment terms → due-days mapping ─────────────────────────────────────────

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


def _rows(cur):
    """Convert cursor rows to a list of dicts."""
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


# ── Core AR query ─────────────────────────────────────────────────────────────

def get_ar_overview(owner_id=None) -> list:
    """
    Returns all open invoices with balances and overdue status.

    Each row: invoice_ref, deal_id, deal_reference, client_name,
              invoice_date, payment_terms, due_date,
              total_invoiced, total_paid, balance,
              currency, exchange_rate,
              days_outstanding, days_overdue, overdue_bucket
    """
    owner_filter = "AND d.owner_id = %(owner_id)s" if owner_id else ""

    sql = f"""
        WITH invoice_totals AS (
            SELECT
                ii.invoice_ref,
                ii.deal_id,
                MIN(ii.created_at::DATE)            AS invoice_date,
                SUM(di.qty * di.unit_price)         AS total_invoiced,
                d.currency,
                d.exchange_rate,
                d.payment_terms,
                d.reference                         AS deal_reference,
                c.full_name                         AS client_name
            FROM invoiced_items ii
            JOIN deal_items di ON ii.deal_item_id = di.id
            JOIN deals      d  ON ii.deal_id      = d.id
            JOIN clients    c  ON d.client_id     = c.id
            WHERE d.deal_status != 'lost'
              {owner_filter}
            GROUP BY ii.invoice_ref, ii.deal_id,
                     d.currency, d.exchange_rate, d.payment_terms,
                     d.reference, c.full_name
        ),
        payment_totals AS (
            SELECT invoice_ref,
                   COALESCE(SUM(amount), 0) AS total_paid
            FROM payments
            GROUP BY invoice_ref
        )
        SELECT
            it.invoice_ref,
            it.deal_id,
            it.deal_reference,
            it.client_name,
            it.invoice_date,
            it.payment_terms,
            it.total_invoiced,
            it.currency,
            it.exchange_rate,
            COALESCE(pt.total_paid, 0)                       AS total_paid,
            it.total_invoiced - COALESCE(pt.total_paid, 0)   AS balance
        FROM invoice_totals it
        LEFT JOIN payment_totals pt ON pt.invoice_ref = it.invoice_ref
        WHERE it.total_invoiced - COALESCE(pt.total_paid, 0) > 0.001
        ORDER BY it.invoice_date ASC
    """

    params = {}
    if owner_id:
        params["owner_id"] = owner_id

    today = date.today()
    rows  = []

    with connection.cursor() as cur:
        cur.execute(sql, params)
        for r in _rows(cur):
            inv_date = r["invoice_date"]
            if isinstance(inv_date, str):
                inv_date = datetime.fromisoformat(inv_date).date()

            terms_days   = parse_payment_terms_days(r["payment_terms"])
            due_date     = inv_date + timedelta(days=terms_days) if inv_date else today
            days_out     = (today - inv_date).days if inv_date else 0
            days_overdue = max(0, (today - due_date).days) if inv_date else 0

            if days_overdue == 0:
                bucket = "current"
            elif days_overdue <= 30:
                bucket = "overdue_30"
            elif days_overdue <= 60:
                bucket = "overdue_60"
            else:
                bucket = "overdue_90"

            r["due_date"]         = due_date.isoformat() if inv_date else None
            r["days_outstanding"] = days_out
            r["days_overdue"]     = days_overdue
            r["overdue_bucket"]   = bucket
            r["total_invoiced"]   = float(r["total_invoiced"] or 0)
            r["total_paid"]       = float(r["total_paid"] or 0)
            r["balance"]          = float(r["balance"] or 0)
            r["exchange_rate"]    = float(r["exchange_rate"] or 1)
            if r.get("invoice_date"):
                r["invoice_date"] = inv_date.isoformat()
            rows.append(r)

    return rows


def get_ar_summary() -> dict:
    """Aggregate AR stats (in deal currency — not converted to USD)."""
    rows = get_ar_overview()
    return {
        "total_open":       round(sum(r["balance"] for r in rows), 2),
        "total_overdue_30": round(sum(r["balance"] for r in rows
                                      if r["overdue_bucket"] == "overdue_30"), 2),
        "total_overdue_60": round(sum(r["balance"] for r in rows
                                      if r["overdue_bucket"] == "overdue_60"), 2),
        "total_overdue_90": round(sum(r["balance"] for r in rows
                                      if r["overdue_bucket"] == "overdue_90"), 2),
        "count_open":       len(rows),
        "count_overdue":    sum(1 for r in rows if r["overdue_bucket"] != "current"),
    }


def get_overdue_invoices(days: int = 30) -> list:
    """Return invoices overdue by at least `days` days."""
    return [r for r in get_ar_overview() if r["days_overdue"] >= days]


def get_invoice_payment_history(invoice_ref: str) -> dict:
    """Full payment history for one invoice plus balance."""
    with connection.cursor() as cur:
        cur.execute("""
            SELECT
                ii.invoice_ref,
                MIN(ii.created_at::DATE)       AS invoice_date,
                SUM(di.qty * di.unit_price)    AS total_invoiced,
                d.currency,
                d.exchange_rate,
                d.payment_terms,
                d.reference                    AS deal_reference,
                c.full_name                    AS client_name,
                d.id                           AS deal_id
            FROM invoiced_items ii
            JOIN deal_items di ON ii.deal_item_id = di.id
            JOIN deals      d  ON ii.deal_id = d.id
            JOIN clients    c  ON d.client_id = c.id
            WHERE ii.invoice_ref = %s
            GROUP BY ii.invoice_ref, d.currency, d.exchange_rate,
                     d.payment_terms, d.reference, c.full_name, d.id
        """, [invoice_ref])
        inv_rows = _rows(cur)
        if not inv_rows:
            return {}
        inv = inv_rows[0]

        cur.execute("""
            SELECT id, amount, currency, payment_date, method, notes,
                   recorded_by_id, created_at
            FROM payments
            WHERE invoice_ref = %s
            ORDER BY payment_date ASC
        """, [invoice_ref])
        payments_list = _rows(cur)

    total_invoiced = float(inv["total_invoiced"] or 0)
    total_paid     = sum(float(p["amount"] or 0) for p in payments_list)
    balance        = total_invoiced - total_paid

    inv_date     = inv["invoice_date"]
    if isinstance(inv_date, str):
        inv_date = datetime.fromisoformat(inv_date).date()
    terms_days   = parse_payment_terms_days(inv["payment_terms"])
    due_date     = (inv_date + timedelta(days=terms_days)) if inv_date else date.today()
    days_overdue = max(0, (date.today() - due_date).days) if inv_date else 0

    # JSON-safe datetime/date values
    for p in payments_list:
        for k in ("amount",):
            if p.get(k) is not None:
                p[k] = float(p[k])
        for k in ("payment_date", "created_at"):
            v = p.get(k)
            if hasattr(v, "isoformat"):
                p[k] = v.isoformat()

    return {
        **inv,
        "invoice_date":   inv_date.isoformat() if inv_date else None,
        "total_invoiced": total_invoiced,
        "total_paid":     total_paid,
        "balance":        round(balance, 2),
        "due_date":       due_date.isoformat(),
        "days_overdue":   days_overdue,
        "exchange_rate":  float(inv["exchange_rate"] or 1),
        "payments":       payments_list,
    }
