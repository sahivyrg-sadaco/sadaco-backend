"""Client invoices, payables and payments in both directions."""
from datetime import date
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.deals.models import Deal
from apps.payments.models import Payment
from . import services
from .models import ClientInvoice, Payable, PayablePayment

INVOICE_ROLES = ('admin', 'finance', 'sales')
PAYABLE_ROLES = ('admin', 'finance', 'operations')
PAYMENT_ROLES = ('admin', 'finance')


def _forbid(request, roles):
    if getattr(request.user, 'role', None) not in roles:
        names = ', '.join(r for r in roles if r != 'admin')
        return Response({'error': f'Only admin and {names} users can do this.'}, status=status.HTTP_403_FORBIDDEN)
    return None


def _bad(msg, field=None):
    return Response({field: [msg]} if field else {'error': msg}, status=status.HTTP_400_BAD_REQUEST)


def _money(v, field, allow_zero=False):
    try:
        d = Decimal(str(v))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError((field, 'Enter an amount.'))
    if d < 0 or (d == 0 and not allow_zero):
        raise ValueError((field, 'Enter an amount above zero.'))
    return d.quantize(Decimal('0.01'))


def _date(v, field, default=None):
    if v in (None, ''):
        if default is not None:
            return default
        raise ValueError((field, 'Enter a date.'))
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        raise ValueError((field, 'Enter a valid date.'))


def _handle(fn):
    """Turn ValueError((field, message)) into a 400 response."""
    try:
        return fn()
    except ValueError as e:
        field, msg = e.args[0] if e.args and isinstance(e.args[0], tuple) else (None, str(e))
        return _bad(msg, field)


def _money_payload(deal, user=None):
    from .stages import sync
    sync(deal, user)
    return services.deal_money(deal)


# ── Per-deal ─────────────────────────────────────────────────────────────────
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def deal_money(request, pk):
    """GET /api/deals/{id}/money/ (reading only: stages are re-checked when something changes)"""
    return Response(services.deal_money(get_object_or_404(Deal, pk=pk)))


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_client_invoice(request, pk):
    """POST /api/deals/{id}/client-invoices/ { number, description, invoice_date, due_date, amount, notes }"""
    deal = get_object_or_404(Deal, pk=pk)
    if (r := _forbid(request, INVOICE_ROLES)):
        return r
    from . import gates
    blocked = gates.enforce(request, deal, gates.for_client_invoice(deal))
    if blocked:
        return blocked

    def go():
        d = request.data
        number = str(d.get('number') or '').strip()
        if not number:
            raise ValueError(('number', 'Enter the invoice number.'))
        inv_date = _date(d.get('invoice_date'), 'invoice_date', timezone.localdate())
        due = _date(d.get('due_date'), 'due_date', services.terms_due_date(inv_date, deal.payment_terms))
        if due < inv_date:
            raise ValueError(('due_date', 'The due date is before the invoice date.'))
        try:
            with transaction.atomic():
                inv = ClientInvoice.objects.create(
                    deal=deal, number=number, description=str(d.get('description') or '').strip(),
                    invoice_date=inv_date, due_date=due, amount=_money(d.get('amount'), 'amount'),
                    currency=deal.currency, notes=str(d.get('notes') or ''), created_by=request.user)
        except IntegrityError:
            raise ValueError(('number', 'Another invoice already uses this number.'))
        services.log(deal, request.user, f'Client invoice {inv.number} issued: {inv.currency} {inv.amount:,.2f}.')
        return Response(_money_payload(deal, request.user), status=status.HTTP_201_CREATED)
    return _handle(go)


@api_view(['PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def client_invoice_detail(request, iid):
    """PUT/DELETE /api/client-invoices/{id}/ — delete only without payments; otherwise cancel."""
    inv = get_object_or_404(ClientInvoice.objects.select_related('deal'), pk=iid)
    deal = inv.deal
    if (r := _forbid(request, INVOICE_ROLES)):
        return r
    has_payments = Payment.objects.filter(invoice_ref=inv.number).exists()

    if request.method == 'DELETE':
        if has_payments:
            return _bad('This invoice has payments. Cancel it instead, or delete the payments first.')
        services.log(deal, request.user, f'Client invoice {inv.number} deleted.')
        inv.delete()
        return Response(_money_payload(deal, request.user))

    def go():
        d = request.data
        if 'number' in d:
            new = str(d['number']).strip()
            if not new:
                raise ValueError(('number', 'Enter the invoice number.'))
            if new != inv.number:
                if ClientInvoice.objects.filter(number=new).exclude(pk=inv.pk).exists():
                    raise ValueError(('number', 'Another invoice already uses this number.'))
                Payment.objects.filter(invoice_ref=inv.number, deal=deal).update(invoice_ref=new)
                inv.number = new
        for f in ('description', 'notes'):
            if f in d:
                setattr(inv, f, str(d[f] or '').strip())
        if 'invoice_date' in d:
            inv.invoice_date = _date(d['invoice_date'], 'invoice_date')
        if 'due_date' in d:
            inv.due_date = _date(d['due_date'], 'due_date')
        if inv.due_date < inv.invoice_date:
            raise ValueError(('due_date', 'The due date is before the invoice date.'))
        if 'amount' in d:
            inv.amount = _money(d['amount'], 'amount')
        if 'cancelled' in d and bool(d['cancelled']) != inv.cancelled:
            inv.cancelled = bool(d['cancelled'])
            services.log(deal, request.user, f'Client invoice {inv.number} '
                         + ('cancelled.' if inv.cancelled else 'reinstated.'))
        inv.save()
        return Response(_money_payload(deal, request.user))
    return _handle(go)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def client_payment(request, iid):
    """POST /api/client-invoices/{id}/payments/ { amount, payment_date, method, notes }"""
    inv = get_object_or_404(ClientInvoice.objects.select_related('deal'), pk=iid)
    if (r := _forbid(request, PAYMENT_ROLES)):
        return r

    if inv.kind == 'credit':
        return _bad('Payments are recorded against invoices, not credit notes.')

    def go():
        d = request.data
        amount = _money(d.get('amount'), 'amount')
        p = Payment.objects.create(
            invoice_ref=inv.number, deal=inv.deal, amount=amount, currency=inv.currency,
            payment_date=_date(d.get('payment_date'), 'payment_date', timezone.localdate()),
            method=str(d.get('method') or '').strip(), notes=str(d.get('notes') or '').strip(),
            recorded_by=request.user)
        services.log(inv.deal, request.user,
                     f'Payment received on {inv.number}: {p.currency} {p.amount:,.2f}'
                     + (f' ({p.method})' if p.method else '') + '.')
        return Response(_money_payload(inv.deal, request.user), status=status.HTTP_201_CREATED)
    return _handle(go)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def credit_note(request, iid):
    """
    POST /api/client-invoices/{id}/credit-note/ { amount, reason, number?, date? }
    Reduces what the client owes on that invoice (e.g. a returned item or a
    price correction). At most the invoice's amount, less earlier credit notes.
    """
    from decimal import Decimal
    inv = get_object_or_404(ClientInvoice.objects.select_related('deal'), pk=iid)
    if (r := _forbid(request, INVOICE_ROLES)):
        return r
    if inv.kind != 'invoice' or inv.cancelled:
        return _bad('Credit notes go against a live invoice.')

    def go():
        d = request.data
        amount = _money(d.get('amount'), 'amount')
        already = sum(float(c.amount) for c in inv.credit_notes.filter(cancelled=False))
        room = round(float(inv.amount) - already, 2)
        if float(amount) > room + 0.001:
            raise ValueError(f'At most {inv.currency} {room:,.2f} can still be credited on {inv.number}.')
        reason = str(d.get('reason') or '').strip()
        if not reason:
            raise ValueError('Say what the credit is for, e.g. "Item 3 returned".')
        number = str(d.get('number') or '').strip()
        if not number:
            n = inv.credit_notes.count() + 1
            number = f'{inv.number}-NC{n}'
            while ClientInvoice.objects.filter(number=number).exists():
                n += 1
                number = f'{inv.number}-NC{n}'
        if ClientInvoice.objects.filter(number=number).exists():
            raise ValueError('Another invoice or credit note already uses this number.')
        when = _date(d.get('date'), 'date', timezone.localdate())
        ClientInvoice.objects.create(
            deal=inv.deal, number=number, description=reason[:200], invoice_date=when, due_date=when,
            amount=Decimal(str(amount)), currency=inv.currency, kind='credit', credits=inv, created_by=request.user)
        services.log(inv.deal, request.user, f'Credit note {number} on {inv.number}: {inv.currency} {float(amount):,.2f} ({reason}).')
        return Response(_money_payload(inv.deal, request.user), status=status.HTTP_201_CREATED)
    return _handle(go)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def client_payment_delete(request, pid):
    """DELETE /api/client-payments/{id}/"""
    p = get_object_or_404(Payment.objects.select_related('deal'), pk=pid)
    if (r := _forbid(request, PAYMENT_ROLES)):
        return r
    deal = p.deal
    if p.transfer_group:
        from . import credit
        credit.undo(p.transfer_group, request.user)
        return Response(_money_payload(deal, request.user) if deal else {})
    services.log(deal, request.user, f'Payment on {p.invoice_ref} of {p.currency} {p.amount:,.2f} removed.')
    p.delete()
    return Response(_money_payload(deal, request.user) if deal else {})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_payable(request, pk):
    """
    POST /api/deals/{id}/payables/ — a supplier's invoice for goods.
    { supplier_order, invoice_ref, invoice_date, due_date?, amount?, notes }
    Amount defaults to the order total; the due date to the order's payment terms.
    """
    deal = get_object_or_404(Deal, pk=pk)
    if (r := _forbid(request, PAYABLE_ROLES)):
        return r
    from apps.logistics.models import SupplierOrder

    def go():
        d = request.data
        order = SupplierOrder.objects.filter(pk=d.get('supplier_order'), deal=deal).select_related('supplier').first()
        if not order:
            raise ValueError(('supplier_order', 'Choose the supplier order this invoice is for.'))
        inv_date = _date(d.get('invoice_date'), 'invoice_date', timezone.localdate())
        due = _date(d.get('due_date'), 'due_date', services.terms_due_date(inv_date, order.payment_terms))
        if due < inv_date:
            raise ValueError(('due_date', 'The due date is before the invoice date.'))
        amount = _money(d.get('amount') if d.get('amount') not in (None, '') else order.total, 'amount')
        p = Payable.objects.create(
            deal=deal, kind='goods', supplier=order.supplier, supplier_order=order,
            payee=order.supplier.company_name if order.supplier else '',
            invoice_ref=str(d.get('invoice_ref') or '').strip(), invoice_date=inv_date, due_date=due,
            amount=amount, currency=order.currency, payment_terms=order.payment_terms,
            notes=str(d.get('notes') or ''), created_by=request.user)
        services.log(deal, request.user, f'Supplier invoice recorded for {order.po_number}: '
                     f'{p.currency} {p.amount:,.2f}, due {p.due_date:%b %d}.')
        return Response(_money_payload(deal, request.user), status=status.HTTP_201_CREATED)
    return _handle(go)


@api_view(['PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def payable_detail(request, pid):
    """PUT/DELETE /api/payables/{id}/ — cost invoices take amount and reference from the cost."""
    p = get_object_or_404(Payable.objects.select_related('deal'), pk=pid)
    deal = p.deal
    if (r := _forbid(request, PAYABLE_ROLES)):
        return r
    if request.method == 'DELETE':
        if p.deal_cost_id:
            return _bad('This comes from a cost invoice. Remove the invoice on the Costs & margin tab instead.')
        if p.payments.exists():
            return _bad('This invoice has payments. Delete the payments first.')
        services.log(deal, request.user, f'Supplier invoice {p.invoice_ref or ""} for {p.payee} deleted.'.replace('  ', ' '))
        p.delete()
        return Response(_money_payload(deal, request.user))

    def go():
        d = request.data
        linked = bool(p.deal_cost_id)
        if not linked:
            if 'invoice_ref' in d:
                p.invoice_ref = str(d['invoice_ref'] or '').strip()
            if 'invoice_date' in d:
                p.invoice_date = _date(d['invoice_date'], 'invoice_date')
            if 'amount' in d:
                p.amount = _money(d['amount'], 'amount')
        if 'due_date' in d:
            p.due_date = _date(d['due_date'], 'due_date')
        if 'notes' in d:
            p.notes = str(d['notes'] or '')
        if p.due_date < p.invoice_date:
            raise ValueError(('due_date', 'The due date is before the invoice date.'))
        p.save()
        return Response(_money_payload(deal, request.user))
    return _handle(go)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def payable_payment(request, pid):
    """POST /api/payables/{id}/payments/ { amount, payment_date, method, reference, notes }"""
    p = get_object_or_404(Payable.objects.select_related('deal'), pk=pid)
    if (r := _forbid(request, PAYMENT_ROLES)):
        return r

    def go():
        d = request.data
        x = PayablePayment.objects.create(
            payable=p, amount=_money(d.get('amount'), 'amount'),
            payment_date=_date(d.get('payment_date'), 'payment_date', timezone.localdate()),
            method=str(d.get('method') or '').strip(), reference=str(d.get('reference') or '').strip(),
            notes=str(d.get('notes') or '').strip(), recorded_by=request.user)
        services.log(p.deal, request.user, f'Paid {p.payee or "supplier"}: {p.currency} {x.amount:,.2f}'
                     + (f' ({x.method})' if x.method else '') + '.')
        return Response(_money_payload(p.deal, request.user), status=status.HTTP_201_CREATED)
    return _handle(go)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def payable_payment_delete(request, xid):
    """DELETE /api/payable-payments/{id}/"""
    x = get_object_or_404(PayablePayment.objects.select_related('payable', 'payable__deal'), pk=xid)
    if (r := _forbid(request, PAYMENT_ROLES)):
        return r
    deal = x.payable.deal
    services.log(deal, request.user, f'Payment to {x.payable.payee or "supplier"} of '
                 f'{x.payable.currency} {x.amount:,.2f} removed.')
    x.delete()
    return Response(_money_payload(deal, request.user))


# ── Company-wide ─────────────────────────────────────────────────────────────
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def receivables(request):
    """GET /api/finance/receivables/?all=1"""
    return Response(services.receivables(request.user, include_paid=request.query_params.get('all') == '1'))


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def payables(request):
    """GET /api/finance/payables/?all=1"""
    return Response(services.payables(request.user, include_paid=request.query_params.get('all') == '1'))


# ── Payment plans ────────────────────────────────────────────────────────────
from . import plans as _plans  # noqa: E402
from .models import PaymentPlan  # noqa: E402

PLAN_OWNERS = {
    'suppliers': ('suppliers.Supplier', 'supplier', ('admin', 'finance', 'operations')),
    'clients':   ('clients.Client', 'client', ('admin', 'finance', 'sales')),
    'orders':    ('logistics.SupplierOrder', 'supplier_order', ('admin', 'finance', 'operations', 'sales')),
    'deals':     ('deals.Deal', 'deal', ('admin', 'finance', 'sales')),
}


@api_view(['GET', 'PUT'])
@permission_classes([IsAuthenticated])
def payment_plan(request, owner, oid):
    """
    GET/PUT /api/{suppliers|clients|orders|deals}/{id}/payment-plan/
    GET → { steps, text, source, own }   (own = set on this record, not inherited)
    PUT { steps } saves; PUT { steps: null } removes it (inherit / read from terms again).
    """
    from django.apps import apps as django_apps
    if owner not in PLAN_OWNERS:
        return Response(status=status.HTTP_404_NOT_FOUND)
    model_label, field, roles = PLAN_OWNERS[owner]
    obj = get_object_or_404(django_apps.get_model(model_label), pk=oid)

    if request.method == 'PUT':
        if (r := _forbid(request, roles)):
            return r
        steps = request.data.get('steps')
        if steps is None:
            PaymentPlan.objects.filter(**{field: obj}).delete()
        else:
            try:
                clean = _plans.validate(steps)
            except ValueError as e:
                return _bad(str(e), 'steps')
            PaymentPlan.objects.update_or_create(**{field: obj}, defaults={'steps': clean})
            # Keep the written terms in step with the schedule, so nothing shows the old terms.
            if field in ('deal', 'supplier_order', 'client', 'supplier'):
                obj.payment_terms = _plans.describe_es(clean)[:100]
                obj.save(update_fields=['payment_terms'])
        deal = obj if field == 'deal' else getattr(obj, 'deal', None)
        if deal is not None:
            what = 'client payment terms' if field == 'deal' else f'payment terms for {obj.po_number}'
            services.log(deal, request.user, f'Changed {what}: '
                         + (_plans.describe(clean) if steps is not None else 'back to the usual terms') + '.')
        obj.refresh_from_db()

    own = PaymentPlan.objects.filter(**{field: obj}).first()
    if field == 'supplier_order':
        steps, source = _plans.for_order(obj)
    elif field == 'deal':
        steps, source = _plans.for_deal(obj)
    else:
        steps = own.steps if own else (_plans.from_text(obj.payment_terms) or None)
        source = field if own else ('terms' if steps else 'none')
    return Response({'steps': steps, 'text': _plans.describe(steps) if steps else '', 'source': source, 'own': bool(own)})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def overrides(request):
    """GET /api/overrides/ → every payment-rule override, newest first (admin only)."""
    from apps.deals.models import DealActivity
    if getattr(request.user, 'role', None) != 'admin':
        return Response({'error': 'Only an admin can see overrides.'}, status=status.HTTP_403_FORBIDDEN)
    rows = (DealActivity.objects.filter(activity_type='override').select_related('deal', 'deal__client', 'user')
            .order_by('-created_at')[:500])
    out = []
    for a in rows:
        text = a.description or ''
        rule, _, reason = text.partition(' Reason: ')
        if rule.startswith('Payment rule overridden by') and ': ' in rule:
            rule = rule.split(': ', 1)[1]
        out.append({'id': a.id, 'when': a.created_at.isoformat(), 'deal_id': a.deal_id,
                    'deal_reference': a.deal.reference if a.deal else '',
                    'client': a.deal.client.dropdown_name if a.deal and a.deal.client else '',
                    'by': a.user.name if a.user else '', 'rule': rule.strip(), 'reason': reason.strip()})
    return Response(out)


# ── Client credit ────────────────────────────────────────────────────────────
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def client_credit(request, cid):
    """GET /api/clients/{id}/credit/ → available credit per currency, where it sits, and past moves."""
    from apps.clients.models import Client
    from . import credit
    return Response(credit.summary(get_object_or_404(Client, pk=cid)))


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def client_credit_refund(request, cid):
    """POST /api/clients/{id}/credit/refund/ { currency, amount, date?, method?, notes? }"""
    from apps.clients.models import Client
    from . import credit
    c = get_object_or_404(Client, pk=cid)
    if (r := _forbid(request, PAYMENT_ROLES)):
        return r

    def go():
        d = request.data
        credit.refund(c, str(d.get('currency') or 'USD'), float(_money(d.get('amount'), 'amount')), request.user,
                      date=_date(d.get('date'), 'date', timezone.localdate()), method=str(d.get('method') or '').strip(),
                      notes=str(d.get('notes') or '').strip())
        return Response(credit.summary(c), status=status.HTTP_201_CREATED)
    return _handle(go)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def client_credit_apply(request, cid):
    """POST /api/clients/{id}/credit/apply/ { invoice, amount, date? } → credit moved onto that invoice"""
    from apps.clients.models import Client
    from . import credit
    c = get_object_or_404(Client, pk=cid)
    if (r := _forbid(request, PAYMENT_ROLES)):
        return r

    def go():
        d = request.data
        target = ClientInvoice.objects.filter(pk=d.get('invoice')).select_related('deal').first()
        if not target:
            raise ValueError('Choose the invoice to apply the credit to.')
        credit.apply(c, target, float(_money(d.get('amount'), 'amount')), request.user, date=_date(d.get('date'), 'date', timezone.localdate()))
        return Response(credit.summary(c), status=status.HTTP_201_CREATED)
    return _handle(go)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def client_credit_undo(request, group):
    """DELETE /api/client-credit/{group}/ → undo a refund or a credit move (all its sides)."""
    from . import credit
    if (r := _forbid(request, PAYMENT_ROLES)):
        return r

    def go():
        credit.undo(group, request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)
    return _handle(go)
