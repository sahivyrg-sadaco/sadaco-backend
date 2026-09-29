"""
Deal economics: revenue, goods cost, extra costs and net margin, in two
columns (estimated and actual so far), plus an incoterm checklist.

Conventions
- All results are in the deal's currency.
- Rates follow the deal convention: 1 USD = rate units of a currency.
- "Actual so far" uses each cost's actual amount when entered, otherwise
  its estimate, so the margin is never rosier than it should be.
- CIF value = goods + supplier charges + freight to Miami + forwarder
  + international freight + insurance. Percentage-based insurance is
  calculated on that value before insurance, to avoid a circle.
"""
from decimal import Decimal

from django.db.models import F, Sum

from .models import CATEGORIES, DealCost, DealCostSettings

CATEGORY_LABEL = dict(CATEGORIES)
CATEGORY_ORDER = {k: i for i, (k, _) in enumerate(CATEGORIES)}
CIF_CATEGORIES = {'supplier_charges', 'freight_miami', 'forwarder', 'freight_intl', 'insurance'}
OVERRUN_THRESHOLD = 0.10

# What Sadaco normally pays for, by incoterm. Order matters: shown in this order.
_TO_MIAMI  = ['freight_miami', 'forwarder']
_MAIN      = _TO_MIAMI + ['freight_intl']
EXPECTED_BY_INCOTERM = {
    'EXW': ['freight_miami'],
    'FCA': _TO_MIAMI, 'FAS': _TO_MIAMI, 'FOB': _TO_MIAMI,
    'CFR': _MAIN, 'CPT': _MAIN,
    'CIF': _MAIN + ['insurance'], 'CIP': _MAIN + ['insurance'],
    'DAP': _MAIN + ['local_delivery'], 'DPU': _MAIN + ['local_delivery'],
    'DDU': _MAIN + ['local_delivery'],
    'DDP': _MAIN + ['customs_broker', 'duties', 'port_charges', 'local_delivery'],
}
# Starting shape for rows created by "Add typical costs".
TYPICAL_SHAPE = {
    'duties':    {'amount_type': 'percent', 'percent_base': 'cif_value'},
    'insurance': {'amount_type': 'percent', 'percent_base': 'cif_value'},
}


def default_treatment(deal, settings_obj=None):
    """(treatment, source). E and F terms → built into prices; C and D terms → separate line."""
    # settings_obj: a DealCostSettings, False (known to have none), or None (look it up).
    s = settings_obj if settings_obj is not None else DealCostSettings.objects.filter(deal=deal).first()
    if s:
        return s.default_treatment, 'set'
    term = (deal.incoterm or '').upper()
    if term and term[0] in 'CD':
        return 'separate', 'incoterm'
    return 'included', 'incoterm'


def to_deal_currency(amount, cost, deal):
    if amount is None:
        return 0.0
    amount = float(amount)
    if cost.currency == deal.currency:
        return amount
    fx = float(cost.fx_rate or 1) or 1.0
    deal_rate = float(deal.exchange_rate or 1) or 1.0
    usd = amount / (1.0 if cost.currency == 'USD' else fx)
    return usd if deal.currency == 'USD' else usd * deal_rate


def item_sums(deal):
    agg = deal.items.filter(is_split_child=False).aggregate(
        goods=Sum(F('qty') * F('unit_cost')), sell=Sum(F('qty') * F('unit_price')))
    return float(agg['goods'] or 0), float(agg['sell'] or 0)


def compute(deal, costs=None, goods=None, sell=None, settings_obj=None):
    """
    Full economics for one deal. `costs`, `goods`, `sell` and `settings_obj`
    can be passed in (e.g. from a prefetch) to avoid extra queries.
    """
    if costs is None:
        costs = list(DealCost.objects.filter(deal=deal).select_related('shipment'))
    if goods is None or sell is None:
        goods, sell = item_sums(deal)
    treatment_default, treatment_source = default_treatment(deal, settings_obj)

    def fixed_value(c, col):
        """Amount known without a percentage, or None if it's a pending percentage."""
        if col == 'act' and c.actual_amount is not None:
            return to_deal_currency(c.actual_amount, c, deal)
        if c.amount_type == 'percent':
            return None
        return to_deal_currency(c.estimate_amount, c, deal)

    values = {'est': {}, 'act': {}}
    cif = {}
    for col in ('est', 'act'):
        pre_cif = goods
        for c in costs:
            v = fixed_value(c, col)
            if v is not None:
                values[col][c.id] = v
                if c.category in CIF_CATEGORIES:
                    pre_cif += v
        # Percentage costs inside CIF (typically insurance) use CIF before them.
        cif_col = pre_cif
        bases = {'goods_cost': goods, 'sell_value': sell, 'cif_value': pre_cif}
        for c in costs:
            if c.id not in values[col] and c.category in CIF_CATEGORIES:
                v = bases.get(c.percent_base, 0) * float(c.percent or 0) / 100
                values[col][c.id] = v
                cif_col += v
        cif[col] = cif_col
        bases['cif_value'] = cif_col
        for c in costs:
            if c.id not in values[col]:
                values[col][c.id] = bases.get(c.percent_base, 0) * float(c.percent or 0) / 100

    rows, by_cat, overruns = [], {}, []
    charges = 0.0
    invoiced = 0
    for c in costs:
        est, act = values['est'][c.id], values['act'][c.id]
        treatment = c.client_treatment or treatment_default
        charge = None
        if treatment == 'separate':
            # What we bill is always in the deal's currency: the set amount, else the
            # estimate, else (never estimated) the invoice, passed through at cost.
            if c.charge_amount is not None:
                charge = float(c.charge_amount)
            elif est > 0 or c.actual_amount is None:
                charge = est
            else:
                charge = act
            charges += charge
        if c.actual_amount is not None:
            invoiced += 1
        over = None
        if c.actual_amount is not None and est > 0:
            over = (act - est) / est
            if over > OVERRUN_THRESHOLD and not c.overrun_acknowledged:
                overruns.append({'id': c.id, 'category': CATEGORY_LABEL[c.category],
                                 'description': c.description, 'estimate': round(est, 2),
                                 'actual': round(act, 2), 'over_pct': round(over * 100, 1)})
        rows.append({'id': c.id, 'estimate': round(est, 2), 'actual_so_far': round(act, 2),
                     'has_actual': c.actual_amount is not None, 'treatment': treatment,
                     'charge': round(charge, 2) if charge is not None else None,
                     'over_pct': round(over * 100, 1) if over is not None else None})
        cat = by_cat.setdefault(c.category, {'category': c.category, 'label': CATEGORY_LABEL[c.category],
                                             'estimate': 0.0, 'actual_so_far': 0.0, 'count': 0, 'invoiced': 0})
        cat['estimate'] += est
        cat['actual_so_far'] += act
        cat['count'] += 1
        cat['invoiced'] += c.actual_amount is not None

    extra_est = sum(values['est'].values())
    extra_act = sum(values['act'].values())
    revenue = sell + charges

    def col(extra):
        profit = revenue - goods - extra
        return {'revenue': round(revenue, 2), 'extra_costs': round(extra, 2),
                'net_profit': round(profit, 2),
                'net_margin_pct': round(profit / revenue * 100, 1) if revenue > 0 else None}

    # Incoterm checklist.
    term = (deal.incoterm or '').upper()
    checklist = []
    for cat_key in EXPECTED_BY_INCOTERM.get(term, []):
        cat_rows = [c for c in costs if c.category == cat_key]
        if not cat_rows:
            checklist.append({'category': cat_key, 'label': CATEGORY_LABEL[cat_key], 'problem': 'missing'})
        elif all(values['est'][c.id] == 0 and c.actual_amount is None for c in cat_rows):
            checklist.append({'category': cat_key, 'label': CATEGORY_LABEL[cat_key], 'problem': 'no_amount'})

    return {
        'currency': deal.currency,
        'incoterm': term or None,
        'default_treatment': treatment_default,
        'default_treatment_source': treatment_source,
        'items_sell': round(sell, 2),
        'separate_charges': round(charges, 2),
        'goods_cost': round(goods, 2),
        'gross_profit': round(sell - goods, 2),
        'gross_margin_pct': round((sell - goods) / sell * 100, 1) if sell > 0 else None,
        'cif_value': {'estimate': round(cif['est'], 2), 'actual_so_far': round(cif['act'], 2)},
        'estimate': col(extra_est),
        'actual_so_far': col(extra_act),
        'costs_total': len(costs),
        'costs_invoiced': invoiced,
        'by_category': sorted(
            [{**v, 'estimate': round(v['estimate'], 2), 'actual_so_far': round(v['actual_so_far'], 2)}
             for v in by_cat.values()],
            key=lambda r: CATEGORY_ORDER[r['category']]),
        'rows': rows,
        'overruns': overruns,
        'checklist': checklist,
        'expected': [{'category': k, 'label': CATEGORY_LABEL[k]} for k in EXPECTED_BY_INCOTERM.get(term, [])],
    }


def add_typical(deal, user):
    """Create estimate rows for expected categories that have none yet."""
    have = set(DealCost.objects.filter(deal=deal).values_list('category', flat=True))
    created = []
    for cat_key in EXPECTED_BY_INCOTERM.get((deal.incoterm or '').upper(), []):
        if cat_key in have:
            continue
        shape = TYPICAL_SHAPE.get(cat_key, {'amount_type': 'fixed'})
        created.append(DealCost.objects.create(
            deal=deal, category=cat_key, currency=deal.currency,
            fx_rate=deal.exchange_rate if deal.currency != 'USD' else 1,
            created_by=user if getattr(user, 'is_authenticated', False) else None, **shape))
    return created


# ── Shipment freight → cost ─────────────────────────────────────────────────
LEG_CATEGORY = {
    'to_miami': 'freight_miami', 'export': 'freight_intl', 'delivery': 'local_delivery',
    'direct': 'freight_intl', 'other': 'other',
}


def _is_empty_estimate(c):
    return c.estimate_amount is None and c.amount_type == 'fixed' and c.charge_amount is None


def sync_shipment_cost(shipment):
    """
    Keep one cost row per shipment whose actual amount is the shipment's
    freight cost. A new shipment's freight first attaches to a matching
    estimate row (same category, same currency, not yet invoiced), so the
    estimate and the real invoice sit side by side.
    """
    deal = shipment.deal
    cost = DealCost.objects.filter(shipment=shipment).first()
    fc = shipment.freight_cost

    if fc is None:
        if cost:
            if _is_empty_estimate(cost):
                cost.delete()
            else:
                cost.shipment = None
                cost.actual_amount = None
                cost.save()
        return None

    currency = shipment.freight_currency or deal.currency
    if cost and cost.currency != currency and not _is_empty_estimate(cost):
        # Currency changed under an estimate: detach and start a separate row.
        cost.shipment, cost.actual_amount = None, None
        cost.save()
        cost = None
    if not cost:
        cat = LEG_CATEGORY.get(shipment.leg, 'other')
        cost = (DealCost.objects.filter(deal=deal, category=cat, shipment__isnull=True,
                                        actual_amount__isnull=True, currency=currency, amount_type='fixed')
                .order_by('id').first()) or DealCost(deal=deal, category=cat, amount_type='fixed')
        cost.shipment = shipment
    cost.actual_amount = fc
    cost.currency = currency
    if currency == 'USD':
        cost.fx_rate = 1
    elif currency == deal.currency:
        cost.fx_rate = deal.exchange_rate or 1
    if not cost.payee:
        cost.payee = shipment.forwarder or shipment.carrier
    if not cost.description:
        cost.description = (f'Tracking {shipment.tracking_number}' if shipment.tracking_number
                            else f'{shipment.get_leg_display()} shipment')
    cost.save()
    return cost


def detach_shipment(shipment):
    """Before a shipment is deleted: drop its freight from the costs."""
    shipment.freight_cost = None
    sync_shipment_cost(shipment)
