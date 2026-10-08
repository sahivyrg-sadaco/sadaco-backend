"""
Freight estimated by weight.

Each line's unit weight and lead time come from the supplier quotes: the
awarded supplier first (the one awarded the largest share), otherwise the
lowest-priced quote that has a weight. Weights the user corrects in the
estimator are remembered in the saved breakdown and used next time.

Saving the estimate writes one cost row per leg (freight to Miami,
international freight) with estimate = total kg × rate (at least the
minimum charge) and a per-line breakdown proportional to weight.
"""
from decimal import Decimal

from apps.deals.models import DealItem, DealItemSplit
from .models import DealCost

LEGS = [('freight_miami', 'Freight to Miami'), ('freight_intl', 'International freight')]
LEG_LABEL = dict(LEGS)


def _f(v):
    return float(v) if v is not None else None


def item_logistics(deal):
    """Per line: qty, unit weight, lead time, and where each came from."""
    from apps.quotes.models import SupplierQuoteItem
    items = list(DealItem.objects.filter(deal=deal, is_split_child=False).order_by('item_number', 'id'))
    qitems = {}
    for qi in SupplierQuoteItem.objects.filter(deal_item__in=items).select_related('quote', 'quote__supplier'):
        qitems.setdefault(qi.deal_item_id, []).append(qi)
    awards = {}
    for s in DealItemSplit.objects.filter(parent_item__in=items):
        awards.setdefault(s.parent_item_id, []).append(s)

    saved, saved_dims = {}, {}
    for c in DealCost.objects.filter(deal=deal, basis='weight'):
        for b in c.breakdown or []:
            if b.get('unit_kg') is not None:
                saved[b['deal_item']] = b['unit_kg']
            if b.get('dims_cm'):
                saved_dims[b['deal_item']] = b['dims_cm']

    lines, max_lead = [], None
    for k, it in enumerate(items, 1):
        qis = qitems.get(it.id, [])
        by_quote = {qi.quote_id: qi for qi in qis}
        awarded = sorted(awards.get(it.id, []), key=lambda s: -float(s.qty_awarded))
        awarded_qis = [by_quote[s.supplier_quote_id] for s in awarded if s.supplier_quote_id in by_quote]
        if not awarded_qis and it.awarded_quote_id in by_quote:
            awarded_qis = [by_quote[it.awarded_quote_id]]

        weight, wsrc = None, None
        if it.id in saved:
            weight, wsrc = saved[it.id], 'saved'
        else:
            for qi in awarded_qis:
                if qi.unit_weight_kg is not None:
                    weight, wsrc = float(qi.unit_weight_kg), f'awarded: {qi.quote.supplier.company_name if qi.quote.supplier else "supplier"}'
                    break
            if weight is None:
                priced = sorted([q for q in qis if q.unit_weight_kg is not None],
                                key=lambda q: (float(q.unit_price) <= 0, float(q.unit_price)))
                if priced:
                    qi = priced[0]
                    weight, wsrc = float(qi.unit_weight_kg), f'quote: {qi.quote.supplier.company_name if qi.quote.supplier else "supplier"}'

        # Lead time: the slowest awarded supplier; before awards, the same supplier the
        # weight came from (the cheapest quote), so both figures describe one likely source.
        def lead_of(qi):
            return qi.lead_time_days if qi.lead_time_days is not None else qi.quote.lead_time_days

        def name(qi):
            return qi.quote.supplier.company_name if qi.quote.supplier else 'supplier'
        lead, lsrc = None, None
        awarded_leads = [(lead_of(qi), qi) for qi in awarded_qis if lead_of(qi) is not None]
        if awarded_leads:
            lead, qi = max(awarded_leads, key=lambda x: x[0])
            lsrc = f'awarded: {name(qi)}'
        else:
            by_price = sorted([q for q in qis if lead_of(q) is not None],
                              key=lambda q: (float(q.unit_price) <= 0, float(q.unit_price)))
            if by_price:
                lead, qi = lead_of(by_price[0]), by_price[0]
                lsrc = f'quote: {name(qi)}'
        if lead is not None:
            max_lead = lead if max_lead is None else max(max_lead, lead)

        lines.append({
            'deal_item': it.id, 'n': k, 'description': it.description, 'qty': float(it.qty), 'unit': it.unit,
            'unit_kg': weight, 'weight_source': wsrc, 'lead_time_days': lead, 'lead_source': lsrc,
            'dims_cm': saved_dims.get(it.id),
        })
    rows = {c.category: c for c in DealCost.objects.filter(deal=deal, basis='weight')}
    from .models import DealCostSettings
    settings_obj = DealCostSettings.objects.filter(deal=deal).first()
    transit = (settings_obj.transit_days if settings_obj else None) or {}
    legs = []
    for key, label in LEGS:
        c = rows.get(key)
        legs.append({'category': key, 'label': label, 'transit_days': transit.get(key),
                     'rate_per_kg': _f(c.weight_rate) if c and c.charge_mode != 'ocean' else None,
                     'min_charge': _f(c.weight_minimum) if c else None,
                     'volumetric_divisor': c.volumetric_divisor if c else None,
                     'charge_mode': (c.charge_mode or 'weight') if c else 'weight',
                     'rate_per_cbm': _f(c.weight_rate) if c and c.charge_mode == 'ocean' else None,
                     'estimate': _f(c.estimate_amount) if c else None})
    return {'lines': lines, 'legs': legs, 'max_lead_time_days': max_lead, 'currency': deal.currency}


def save_estimate(deal, lines_in, legs_in, user, display_unit='kg'):
    """
    lines_in: [{deal_item, unit_kg, dims_cm?: [L, W, H] per unit}]
    legs_in:  [{category, rate_per_kg, min_charge, transit_days, volumetric_divisor?}]
    Returns the cost rows written. A leg with no rate is left untouched.
    With a volumetric divisor, each line is charged on the higher of its actual
    weight and its volumetric weight (L×W×H in cm ÷ divisor, per unit × qty).
    """
    def _dims(v):
        try:
            d = [float(x) for x in (v or [])]
            return d if len(d) == 3 and all(x > 0 for x in d) else None
        except (TypeError, ValueError):
            raise ValueError('Dimensions must be numbers.')
    weights = {int(l['deal_item']): (float(l['unit_kg']) if l.get('unit_kg') not in (None, '') else None)
               for l in lines_in}
    dims = {int(l['deal_item']): _dims(l.get('dims_cm')) for l in lines_in}
    items = list(DealItem.objects.filter(deal=deal, is_split_child=False).order_by('item_number', 'id'))
    rows = []
    for k, it in enumerate(items, 1):
        w = weights.get(it.id)
        rows.append({'deal_item': it.id, 'n': k, 'description': it.description[:80], 'qty': float(it.qty),
                     'unit_kg': w, 'dims_cm': dims.get(it.id), 'actual_kg': (w or 0) * float(it.qty)})

    def charged(r, divisor):
        """Weight this line is charged on for a leg."""
        if divisor and r['dims_cm']:
            l, w_, h = r['dims_cm']
            return round(max(r['actual_kg'], l * w_ * h / divisor * r['qty']), 3)
        return r['actual_kg']
    # Transit days are kept for the quoted delivery time, whether or not a rate is given.
    from .models import DealCostSettings
    transit = {}
    for leg in legs_in:
        if leg.get('category') in LEG_LABEL and leg.get('transit_days') not in (None, ''):
            try:
                transit[leg['category']] = max(0, int(leg['transit_days']))
            except (TypeError, ValueError):
                raise ValueError('Transit times must be whole days.')
    if transit or DealCostSettings.objects.filter(deal=deal).exists():
        s, _ = DealCostSettings.objects.get_or_create(deal=deal)
        s.transit_days = transit
        s.save(update_fields=['transit_days'])

    written = []
    for leg in legs_in:
        cat = leg.get('category')
        if cat not in LEG_LABEL:
            continue
        ocean = leg.get('charge_mode') == 'ocean'
        try:
            rate = float((leg.get('rate_per_cbm') if ocean else leg.get('rate_per_kg')) or 0)
            minimum = float(leg.get('min_charge') or 0)
        except (TypeError, ValueError):
            raise ValueError('Rates and minimum charges must be numbers.')
        if rate <= 0:
            continue
        try:
            divisor = None if ocean else (int(leg.get('volumetric_divisor') or 0) or None)
        except (TypeError, ValueError):
            raise ValueError('The volumetric divisor must be a whole number, e.g. 5000 or 6000.')
        if ocean:
            # W/M: each line pays on the greater of its cubic metres and its tonnes.
            leg_rows = []
            for r in rows:
                # Full precision here (rounded only when shown), so the screen's preview matches to the cent.
                cbm = (r['dims_cm'][0] * r['dims_cm'][1] * r['dims_cm'][2] / 1_000_000) * r['qty'] if r['dims_cm'] else 0.0
                leg_rows.append({**r, 'cbm': cbm, 'kg': r['actual_kg'], 'wm': max(cbm, r['actual_kg'] / 1000)})
            total_units = sum(r['wm'] for r in leg_rows)
        else:
            leg_rows = [{**r, 'kg': charged(r, divisor)} for r in rows]
            total_units = sum(r['kg'] for r in leg_rows)
        total_kg = sum(r['kg'] for r in leg_rows)
        raw = total_units * rate
        amount = round(max(raw, minimum), 2)
        factor = (amount / raw) if raw > 0 else 0
        breakdown = []
        for r in leg_rows:
            share = round((r['wm'] if ocean else r['kg']) * rate * factor, 2) if raw > 0 else 0
            breakdown.append({**r, 'amount': share})
        # Rounding: put any cent difference on the heaviest line.
        diff = round(amount - sum(b['amount'] for b in breakdown), 2)
        if diff and breakdown:
            heaviest = max(breakdown, key=lambda b: b['wm'] if ocean else b['kg'])
            heaviest['amount'] = round(heaviest['amount'] + diff, 2)
        c = (DealCost.objects.filter(deal=deal, category=cat, basis='weight').first()
             or DealCost.objects.filter(deal=deal, category=cat, basis='', shipment__isnull=True,
                                        actual_amount__isnull=True, amount_type='fixed').order_by('id').first()
             or DealCost(deal=deal, category=cat, created_by=user if getattr(user, 'is_authenticated', False) else None))
        c.basis = 'weight'
        c.amount_type = 'fixed'
        c.currency = deal.currency
        c.fx_rate = deal.exchange_rate if deal.currency != 'USD' else 1
        c.estimate_amount = Decimal(str(amount))
        c.breakdown = breakdown
        c.weight_rate = Decimal(str(rate))
        c.weight_minimum = Decimal(str(minimum)) if minimum else None
        c.volumetric_divisor = divisor
        c.charge_mode = 'ocean' if ocean else 'weight'
        minimum_note = f' (minimum {deal.currency} {minimum:,.2f} applied)' if minimum and minimum > raw else ''
        basis = f'By chargeable weight (÷{divisor})' if divisor else 'By weight'
        if ocean:
            cbm_total = sum(r['cbm'] for r in leg_rows)
            c.description = (f'Ocean W/M: {total_units:,.2f} revenue tonnes ({cbm_total:,.2f} m³, {total_kg:,.0f} kg) '
                             f'× {deal.currency} {rate:,.2f}/m³{minimum_note}')
        elif display_unit == 'lb':   # described the way it was entered; stored in kg either way
            c.description = (f'{basis}: {total_kg / 0.45359237:,.1f} lb × {deal.currency} '
                             f'{rate * 0.45359237:,.2f}/lb{minimum_note}')
        else:
            c.description = f'{basis}: {total_kg:,.1f} kg × {deal.currency} {rate:,.2f}/kg{minimum_note}'
        c.save()
        written.append(c)
    return written


def freight_by_item(deal):
    """{deal_item_id: freight estimate} summed over the weight-based cost rows."""
    out = {}
    for c in DealCost.objects.filter(deal=deal, basis='weight'):
        for b in c.breakdown or []:
            out[b['deal_item']] = round(out.get(b['deal_item'], 0) + float(b.get('amount') or 0), 2)
    return out
