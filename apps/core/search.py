"""Global search: deals by reference, client or client's reference, and every document number."""
from django.db.models import Q
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.deals.models import Deal

PER_KIND = 6


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def search(request):
    """GET /api/search/?q=4500 → [{kind, label, detail, deal_id, deal_reference, client, tab}]"""
    q = (request.query_params.get('q') or '').strip()
    if len(q) < 2:
        return Response({'results': []})
    deals = Deal.objects.all()
    if getattr(request.user, 'role', None) == 'sales':
        deals = deals.filter(owner=request.user)
    out = []

    def add(kind, label, detail, deal, tab):
        out.append({'kind': kind, 'label': label, 'detail': detail, 'deal_id': deal.id,
                    'deal_reference': deal.reference, 'client': deal.client.dropdown_name if deal.client else '',
                    'tab': tab})

    for d in deals.filter(Q(reference__icontains=q) | Q(client_ref__icontains=q) | Q(client__dropdown_name__icontains=q)
                          | Q(client__full_name__icontains=q)).select_related('client').order_by('-created_at')[:PER_KIND]:
        ref = d.client_ref if d.client_ref and d.client_ref.lower() != 'xxx-xxx' else ''
        add('Deal', d.reference, ', '.join(x for x in (d.client.dropdown_name if d.client else '', ref and f'their ref {ref}', d.status) if x), d, '')

    from apps.clientquotes.models import ClientPO, ClientQuote
    for p in ClientPO.objects.filter(deal__in=deals, po_number__icontains=q).select_related('deal', 'deal__client')[:PER_KIND]:
        add('Client PO', p.po_number, p.get_status_display(), p.deal, 'invoicing')
    for x in ClientQuote.objects.filter(deal__in=deals, number__icontains=q).select_related('deal', 'deal__client')[:PER_KIND]:
        add('Client quote', x.number, x.get_status_display(), x.deal, 'client-quote')

    from apps.finance.models import ClientInvoice, Payable
    for i in ClientInvoice.objects.filter(deal__in=deals, number__icontains=q).select_related('deal', 'deal__client')[:PER_KIND]:
        add('Client invoice', i.number, i.description, i.deal, 'invoicing')
    for p in Payable.objects.filter(deal__in=deals, invoice_ref__icontains=q).select_related('deal', 'deal__client')[:PER_KIND]:
        add('Supplier invoice', p.invoice_ref, p.payee, p.deal, 'money')

    from apps.logistics.models import Shipment, SupplierOrder
    for o in (SupplierOrder.objects.filter(deal__in=deals).filter(Q(po_number__icontains=q) | Q(supplier_ref__icontains=q))
              .select_related('deal', 'deal__client', 'supplier')[:PER_KIND]):
        add('Supplier PO', o.po_number, ', '.join(x for x in (o.supplier.company_name if o.supplier else '',
                                                              o.supplier_ref and f'their ref {o.supplier_ref}') if x), o.deal, 'shipping')
    for s in Shipment.objects.filter(deal__in=deals, tracking_number__icontains=q).select_related('deal', 'deal__client')[:PER_KIND]:
        add('Tracking', s.tracking_number, f'{s.get_leg_display()}, {s.get_status_display().lower()}', s.deal, 'shipping')
    return Response({'results': out})
