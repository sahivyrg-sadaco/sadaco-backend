"""
Payment schedules ("plans"): reading them from terms text, validating,
resolving which one applies, and describing them in words.

A plan is a list of steps, each a share of the total and when it's due:
  on_order         advance, due when invoiced              → gates the next step
  before_shipping  must be paid before goods leave           → gates shipping
  after_shipping   credit: due N days after shipping         → no gate
  on_delivery      due when the goods arrive                 → no gate
"""
import re

WHEN = ('on_order', 'before_shipping', 'after_shipping', 'on_delivery')
WHEN_LABEL = {
    'on_order': 'on order', 'before_shipping': 'before shipping',
    'after_shipping': 'after shipping', 'on_delivery': 'on delivery',
}
PRE_SHIPPING = ('on_order', 'before_shipping')


def validate(steps):
    """Clean a list of steps or raise ValueError with a readable message."""
    if not isinstance(steps, list) or not steps:
        raise ValueError('Add at least one payment step.')
    if len(steps) > 5:
        raise ValueError('Use at most 5 payment steps.')
    out = []
    for s in steps:
        try:
            pct = round(float(s.get('pct')), 2)
        except (TypeError, ValueError):
            raise ValueError('Each step needs a percentage.')
        when = s.get('when')
        if when not in WHEN:
            raise ValueError('Each step needs a "when".')
        if pct <= 0:
            raise ValueError('Percentages must be above zero.')
        step = {'pct': pct, 'when': when}
        if when == 'after_shipping':
            try:
                step['days'] = max(0, int(s.get('days') or 0))
            except (TypeError, ValueError):
                raise ValueError('Enter the number of days after shipping.')
        out.append(step)
    if abs(sum(s['pct'] for s in out) - 100) > 0.01:
        raise ValueError(f'The steps add up to {sum(s["pct"] for s in out):g}%. They must add up to 100%.')
    return out


def from_text(terms):
    """
    Best reading of a free-text term into a plan, or None if it can't be read.
    '100% prepagado' → 100% before shipping
    '30% anticipado / 70% contra entrega' → 30% on order, 70% on delivery
    'Net 30', '60 days' → 100% 30/60 days after shipping
    'Letter of credit' → paid against shipping documents: after shipping, 0 days
    """
    t = (terms or '').strip().lower()
    if not t:
        return None
    pcts = [float(x) for x in re.findall(r'(\d{1,3}(?:\.\d+)?)\s*%', t)]
    if len(pcts) >= 2 and abs(sum(pcts) - 100) < 0.01:
        # Pair each percentage with the words around it, in order.
        segs = [x for x in re.split(r'[/,;+]| y | and ', t) if '%' in x]
        if len(segs) != len(pcts):
            segs = [''] * len(pcts)
        return [{'pct': pct, **_when_of(seg, first=k == 0)} for k, (pct, seg) in enumerate(zip(pcts, segs))]
    if 'carta de cr' in t or 'letter of credit' in t or re.search(r'\bl/?c\b', t):
        return [{'pct': 100, 'when': 'after_shipping', 'days': 0}]
    if any(w in t for w in ('con la orden', 'on order')):
        return [{'pct': 100, 'when': 'on_order'}]
    if any(w in t for w in ('antes del emb', 'antes del env', 'before shipping')):
        return [{'pct': 100, 'when': 'before_shipping'}]
    if any(w in t for w in ('al embarque', 'on shipping')):
        return [{'pct': 100, 'when': 'after_shipping', 'days': 0}]
    if any(w in t for w in ('prepag', 'prepaid', 'pre-paid', 'anticip', 'advance', 'cash in advance')) \
            or t in ('cash', 'contado', 'de contado'):
        return [{'pct': 100, 'when': 'before_shipping'}]
    if any(w in t for w in ('contra entrega', 'on delivery', 'cod', 'cash on delivery')):
        return [{'pct': 100, 'when': 'on_delivery'}]
    m = re.search(r'(\d{1,3})\s*(?:d[ií]as|days)|net\s*(\d{1,3})|neto\s*(\d{1,3})', t)
    if m:
        return [{'pct': 100, 'when': 'after_shipping', 'days': int(next(g for g in m.groups() if g))}]
    return None


def _when_of(seg, first):
    s = seg or ''
    if any(w in s for w in ('anticip', 'advance', 'on order', 'con la orden', 'adelanto')):
        return {'when': 'on_order'}
    if any(w in s for w in ('antes del env', 'antes del emb', 'antes de despach', 'before ship', 'before shipping', 'previo al emb')):
        return {'when': 'before_shipping'}
    if any(w in s for w in ('al embarque', 'on shipping')):
        return {'when': 'after_shipping', 'days': 0}
    if any(w in s for w in ('contra entrega', 'on delivery', 'a la entrega')):
        return {'when': 'on_delivery'}
    m = re.search(r'(\d{1,3})\s*(?:d[ií]as|days)|net\s*(\d{1,3})', s)
    if m:
        return {'when': 'after_shipping', 'days': int(next(g for g in m.groups() if g))}
    return {'when': 'on_order'} if first else {'when': 'before_shipping'}


def describe(steps):
    """'50% on order, 50% 30 days after shipping'"""
    out = []
    for s in steps or []:
        pct = f'{s["pct"]:g}%'
        if s['when'] == 'after_shipping':
            d = s.get('days', 0)
            out.append(f'{pct} on shipping' if d == 0 else f'{pct} {d} days after shipping')
        else:
            out.append(f'{pct} {WHEN_LABEL[s["when"]]}')
    return ', '.join(out)


WHEN_ES = {'on_order': 'anticipado', 'before_shipping': 'antes del embarque', 'on_delivery': 'contra entrega'}


def describe_es(steps):
    """'50% anticipado / 50% a 30 días del embarque', in the style of the terms list."""
    if len(steps or []) == 1 and steps[0]['when'] == 'on_order':
        return f'{steps[0]["pct"]:g}% con la orden'      # "anticipado" alone reads as before shipping
    out = []
    for s in steps or []:
        pct = f'{s["pct"]:g}%'
        if s['when'] == 'after_shipping':
            d = s.get('days', 0)
            out.append(f'{pct} al embarque' if d == 0 else f'{pct} a {d} días del embarque')
        else:
            out.append(f'{pct} {WHEN_ES[s["when"]]}')
    return ' / '.join(out)


def pre_shipping_pct(steps):
    return sum(s['pct'] for s in steps if s['when'] in PRE_SHIPPING)


def on_order_pct(steps):
    return sum(s['pct'] for s in steps if s['when'] == 'on_order')


# ── Which plan applies ──────────────────────────────────────────────────────
# Unknown supplier terms are treated as payment before shipping (the safe side
# for a purchase); unknown client terms as 30 days' credit (no gate), and both
# are labelled "assumed" so someone sets them properly.
SUPPLIER_FALLBACK = [{'pct': 100, 'when': 'before_shipping'}]
CLIENT_FALLBACK   = [{'pct': 100, 'when': 'after_shipping', 'days': 30}]


def _plan_of(obj, attr='payment_plan'):
    try:
        return getattr(obj, attr).steps if obj is not None else None
    except Exception:   # no plan row
        return None


def for_order(order):
    """(steps, source) for a supplier order. source: order | supplier | terms | assumed"""
    if (s := _plan_of(order)):
        return s, 'order'
    if order.supplier and (s := _plan_of(order.supplier)):
        return s, 'supplier'
    for text in (order.payment_terms, order.supplier.payment_terms if order.supplier else ''):
        if (s := from_text(text)):
            return s, 'terms'
    return SUPPLIER_FALLBACK, 'assumed'


def for_deal(deal):
    """(steps, source) for the client side of a deal. source: deal | client | terms | assumed"""
    if (s := _plan_of(deal)):
        return s, 'deal'
    if deal.client and (s := _plan_of(deal.client)):
        return s, 'client'
    for text in (deal.payment_terms, deal.client.payment_terms if deal.client else ''):
        if (s := from_text(text)):
            return s, 'terms'
    return CLIENT_FALLBACK, 'assumed'
