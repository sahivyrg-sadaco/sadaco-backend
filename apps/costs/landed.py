"""
Landed cost per line, and prices recalculated from it.

Landed unit cost = supplier unit cost + this line's share of the extra costs
that are built into item prices (treatment "included"):
  - freight estimated by weight uses its per-line split (per unit of the quoted qty);
  - any other built-in cost is shared by line value (qty × unit cost).
Quantities are the won quantities once a client PO is processed, else the quoted ones.
Prices are set so the margin on the landed cost equals the target:
  price = landed / (1 - target).
"""
from decimal import Decimal

from apps.deals.models import DealItem
from .models import DealCost
from .services import compute, target_margin


def landed(deal, target_pct=None):
    from apps.clientquotes.services import won_items
    won = won_items(deal)
    items = list(DealItem.objects.filter(deal=deal, is_split_child=False).order_by('item_number', 'id'))
    qty_of = {it.id: (float(won.get(it.id, 0)) if won is not None else float(it.qty or 0)) for it in items}
    econ = compute(deal)
    est = {r['id']: r['estimate'] for r in econ['rows']}
    costs = {c.id: c for c in DealCost.objects.filter(deal=deal)}

    built_in = {it.id: 0.0 for it in items}           # total built-in cost carried by each line
    unallocated = 0.0
    value = {it.id: qty_of[it.id] * float(it.unit_cost or 0) for it in items}
    total_value = sum(value.values())
    for r in econ['rows']:
        if r['treatment'] != 'included' or not est.get(r['id']):
            continue
        c = costs.get(r['id'])
        amount = est[r['id']]
        if c is not None and c.basis == 'weight' and c.breakdown:
            split_total = sum(float(b.get('amount') or 0) for b in c.breakdown) or 0
            scale = amount / split_total if split_total else 0
            for b in c.breakdown:
                it = next((i for i in items if i.id == b.get('deal_item')), None)
                if it is None or not float(it.qty or 0):
                    continue
                per_unit = float(b.get('amount') or 0) * scale / float(it.qty)
                built_in[it.id] += per_unit * qty_of[it.id]
        elif total_value > 0:
            for it in items:
                built_in[it.id] += amount * value[it.id] / total_value
        else:
            unallocated += amount

    pct = float(target_pct) if target_pct is not None else target_margin(deal)[0]
    rows = []
    for k, it in enumerate(items, 1):
        q = qty_of[it.id]
        cost = float(it.unit_cost or 0)
        per_unit = built_in[it.id] / q if q else 0.0
        land = cost + per_unit
        price = float(it.unit_price or 0)
        suggested = land / (1 - pct / 100) if land > 0 and pct < 100 else None
        rows.append({
            'deal_item': it.id, 'n': k, 'description': it.description, 'qty': q, 'unit': it.unit,
            'won': won is None or q > 0,
            'unit_cost': round(cost, 4), 'built_in_per_unit': round(per_unit, 4), 'landed_unit': round(land, 4),
            'unit_price': round(price, 4),
            'landed_margin_pct': round((price - land) / price * 100, 1) if price > 0 else None,
            'suggested_price': round(suggested, 4) if suggested else None,
        })
    return {'target_margin_pct': pct, 'currency': deal.currency, 'lines': rows,
            'unallocated': round(unallocated, 2), 'built_in_total': round(sum(built_in.values()), 2)}


def apply(deal, target_pct, item_ids, user):
    """Set the chosen lines' prices to the target margin on landed cost. Returns the lines changed."""
    data = landed(deal, target_pct)
    wanted = {int(i) for i in item_ids}
    changed = []
    for r in data['lines']:
        if r['deal_item'] not in wanted or not r['suggested_price']:
            continue
        it = DealItem.objects.get(pk=r['deal_item'])
        price = Decimal(str(round(r['suggested_price'], 4)))
        it.unit_price = price
        cost = float(it.unit_cost or 0)
        # Stored margin stays "on supplier cost", as the line editor shows it.
        it.margin_pct = Decimal(str(round((float(price) - cost) / float(price), 4))) if float(price) > 0 else it.margin_pct
        it.save(update_fields=['unit_price', 'margin_pct'])
        changed.append(r)
    return changed
