"""
Analytics services — read-only queries for the dashboard.

Ported from the Flask prototype's modules/analytics.py.
Uses django.db.connection instead of psycopg2; SQL preserved as-is.
"""
from datetime import date

from django.db import connection


def _rows(cur):
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def _float(v):
    return float(v) if v is not None else None


def _date_range(period: str = None, date_from: str = None, date_to: str = None):
    """
    Return (start_date, end_date) from a period string.
    period: 'month' | 'quarter' | 'year' | 'custom'
    """
    today = date.today()

    if period == 'month':
        start, end = today.replace(day=1), today
    elif period == 'quarter':
        q_start_month = ((today.month - 1) // 3) * 3 + 1
        start = today.replace(month=q_start_month, day=1)
        end   = today
    elif period == 'year':
        start = today.replace(month=1, day=1)
        end   = today
    elif period == 'custom' and date_from and date_to:
        start = date.fromisoformat(date_from)
        end   = date.fromisoformat(date_to)
    else:
        start = today.replace(month=1, day=1)
        end   = today

    return start, end


# ── 1. Revenue by client ─────────────────────────────────────────────────────

def revenue_by_client(period='year', date_from=None, date_to=None,
                      owner_id=None) -> list:
    start, end = _date_range(period, date_from, date_to)
    owner_filter = "AND d.owner_id = %(owner_id)s" if owner_id else ""

    sql = f"""
        SELECT
            c.full_name                                        AS client_name,
            COUNT(DISTINCT d.id)                               AS deal_count,
            ROUND(SUM(
                di.qty * di.unit_price / NULLIF(d.exchange_rate, 0)
            )::NUMERIC, 2)                                     AS total_usd
        FROM invoiced_items ii
        JOIN deal_items di ON ii.deal_item_id = di.id
        JOIN deals      d  ON ii.deal_id      = d.id
        JOIN clients    c  ON d.client_id     = c.id
        WHERE ii.created_at::DATE BETWEEN %(start)s AND %(end)s
          {owner_filter}
        GROUP BY c.id, c.full_name
        ORDER BY total_usd DESC NULLS LAST
        LIMIT 15
    """
    params = {'start': start, 'end': end}
    if owner_id:
        params['owner_id'] = owner_id

    with connection.cursor() as cur:
        cur.execute(sql, params)
        rows = _rows(cur)
    for r in rows:
        r['total_usd']  = _float(r.get('total_usd'))
        r['deal_count'] = int(r.get('deal_count') or 0)
    return rows


# ── 2. Monthly invoicing volume ──────────────────────────────────────────────

def monthly_invoicing(period='year', date_from=None, date_to=None,
                      owner_id=None) -> list:
    start, end = _date_range(period, date_from, date_to)
    owner_filter = "AND d.owner_id = %(owner_id)s" if owner_id else ""

    sql = f"""
        SELECT
            TO_CHAR(ii.created_at, 'YYYY-MM')                 AS month,
            COUNT(DISTINCT d.id)                               AS deal_count,
            ROUND(SUM(
                di.qty * di.unit_price / NULLIF(d.exchange_rate, 0)
            )::NUMERIC, 2)                                     AS total_usd
        FROM invoiced_items ii
        JOIN deal_items di ON ii.deal_item_id = di.id
        JOIN deals      d  ON ii.deal_id      = d.id
        WHERE ii.created_at::DATE BETWEEN %(start)s AND %(end)s
          {owner_filter}
        GROUP BY TO_CHAR(ii.created_at, 'YYYY-MM')
        ORDER BY month ASC
    """
    params = {'start': start, 'end': end}
    if owner_id:
        params['owner_id'] = owner_id

    with connection.cursor() as cur:
        cur.execute(sql, params)
        rows = _rows(cur)
    for r in rows:
        r['total_usd']  = _float(r.get('total_usd'))
        r['deal_count'] = int(r.get('deal_count') or 0)
    return rows


# ── 3. Pipeline by stage ─────────────────────────────────────────────────────

def pipeline_by_stage(owner_id=None) -> list:
    owner_filter = "AND d.owner_id = %(owner_id)s" if owner_id else ""

    sql = f"""
        SELECT
            d.status                                           AS stage,
            COUNT(*)                                           AS count,
            ROUND(COALESCE(SUM(
                di.qty * di.unit_price / NULLIF(d.exchange_rate, 0)
            ), 0)::NUMERIC, 2)                                 AS total_usd
        FROM deals d
        LEFT JOIN deal_items di ON di.deal_id = d.id
        WHERE d.deal_status = 'active'
          {owner_filter}
        GROUP BY d.status
        ORDER BY CASE d.status
            WHEN 'Quoting'     THEN 1
            WHEN 'Negotiating' THEN 2
            WHEN 'PO Sent'     THEN 3
            WHEN 'Invoiced'    THEN 4
            WHEN 'Delivered'   THEN 5
            WHEN 'Closed'      THEN 6
            WHEN 'Cancelled'   THEN 7
            ELSE 8 END
    """
    params = {}
    if owner_id:
        params['owner_id'] = owner_id

    with connection.cursor() as cur:
        cur.execute(sql, params)
        rows = _rows(cur)
    for r in rows:
        r['count']     = int(r.get('count') or 0)
        r['total_usd'] = _float(r.get('total_usd'))
    return rows


# ── 4. Margin % by client ────────────────────────────────────────────────────

def margin_by_client(period='year', date_from=None, date_to=None,
                     owner_id=None) -> list:
    start, end = _date_range(period, date_from, date_to)
    owner_filter = "AND d.owner_id = %(owner_id)s" if owner_id else ""

    sql = f"""
        SELECT
            c.full_name                                        AS client_name,
            ROUND(AVG(
                CASE WHEN di.unit_price > 0
                THEN (di.unit_price - di.unit_cost) / di.unit_price * 100
                ELSE 0 END
            )::NUMERIC, 1)                                     AS avg_margin_pct,
            ROUND(SUM(
                di.qty * di.unit_price / NULLIF(d.exchange_rate, 0)
            )::NUMERIC, 2)                                     AS total_usd
        FROM invoiced_items ii
        JOIN deal_items di ON ii.deal_item_id = di.id
        JOIN deals      d  ON ii.deal_id      = d.id
        JOIN clients    c  ON d.client_id     = c.id
        WHERE ii.created_at::DATE BETWEEN %(start)s AND %(end)s
          {owner_filter}
        GROUP BY c.id, c.full_name
        HAVING SUM(di.qty * di.unit_price) > 0
        ORDER BY avg_margin_pct DESC NULLS LAST
        LIMIT 15
    """
    params = {'start': start, 'end': end}
    if owner_id:
        params['owner_id'] = owner_id

    with connection.cursor() as cur:
        cur.execute(sql, params)
        rows = _rows(cur)
    for r in rows:
        r['avg_margin_pct'] = _float(r.get('avg_margin_pct'))
        r['total_usd']      = _float(r.get('total_usd'))
    return rows


# ── 5. Summary KPI cards ─────────────────────────────────────────────────────

def kpi_summary(period='year', date_from=None, date_to=None,
                owner_id=None) -> dict:
    start, end = _date_range(period, date_from, date_to)
    owner_filter = "AND d.owner_id = %(owner_id)s" if owner_id else ""
    params = {'start': start, 'end': end}
    if owner_id:
        params['owner_id'] = owner_id

    with connection.cursor() as cur:
        # Total invoiced
        cur.execute(f"""
            SELECT ROUND(COALESCE(SUM(
                di.qty * di.unit_price / NULLIF(d.exchange_rate, 0)
            ), 0)::NUMERIC, 2) AS total_usd
            FROM invoiced_items ii
            JOIN deal_items di ON ii.deal_item_id = di.id
            JOIN deals      d  ON ii.deal_id = d.id
            WHERE ii.created_at::DATE BETWEEN %(start)s AND %(end)s
              {owner_filter}
        """, params)
        total_invoiced = _float(_rows(cur)[0]['total_usd']) or 0.0

        # Deal counts
        cur.execute(f"""
            SELECT
                COUNT(*) FILTER (WHERE deal_status = 'active') AS active_deals,
                COUNT(*) FILTER (WHERE deal_status = 'won')     AS won_deals,
                COUNT(*) FILTER (WHERE deal_status = 'lost')    AS lost_deals,
                COUNT(*)                                         AS total_deals
            FROM deals d
            WHERE d.created_at::DATE BETWEEN %(start)s AND %(end)s
              {owner_filter}
        """, params)
        counts = _rows(cur)[0]

        # Avg margin
        cur.execute(f"""
            SELECT ROUND(AVG(
                CASE WHEN di.unit_price > 0
                THEN (di.unit_price - di.unit_cost) / di.unit_price * 100
                ELSE 0 END
            )::NUMERIC, 1) AS avg_margin
            FROM invoiced_items ii
            JOIN deal_items di ON ii.deal_item_id = di.id
            JOIN deals      d  ON ii.deal_id = d.id
            WHERE ii.created_at::DATE BETWEEN %(start)s AND %(end)s
              {owner_filter}
        """, params)
        avg_margin = _float(_rows(cur)[0]['avg_margin']) or 0.0

    return {
        'total_invoiced_usd': total_invoiced,
        'avg_margin_pct':     avg_margin,
        **{k: int(v or 0) for k, v in counts.items()},
    }
