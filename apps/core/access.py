"""
Deal-level access for sales users: they can only open deals they own.

One central check in front of every deal-related endpoint (rather than in
each view, where one could be missed). It works out which deal a request is
about from the URL (/api/deals/12/…, /api/orders/5/, /api/costs/9/, …) and
answers 404 "Not found" when a sales user isn't that deal's owner. Other
roles, unauthenticated requests and non-deal URLs pass straight through
(the views still apply their own permissions).
"""
from django.http import JsonResponse

# URL prefix → (view kwarg, model label, path from the object to its deal id)
OBJECT_ROUTES = [
    ('/api/orders/',           'oid', 'logistics.SupplierOrder', 'deal_id'),
    ('/api/shipments/',        'sid', 'logistics.Shipment',      'deal_id'),
    ('/api/costs/',            'cid', 'costs.DealCost',          'deal_id'),
    ('/api/rfqs/',             'rid', 'rfqs.SupplierRFQ',        'deal_id'),
    ('/api/client-invoices/',  'iid', 'finance.ClientInvoice',   'deal_id'),
    ('/api/client-payments/',  'pid', 'payments.Payment',        'deal_id'),
    ('/api/payables/',         'pid', 'finance.Payable',         'deal_id'),
    ('/api/payable-payments/', 'xid', 'finance.PayablePayment',  'payable__deal_id'),
    ('/api/client-quotes/',    'qid', 'clientquotes.ClientQuote', 'deal_id'),
    ('/api/client-pos/',       'pid', 'clientquotes.ClientPO',   'deal_id'),
    ('/api/attachments/',      'pk',  'documents.FileAttachment', 'deal_id'),
]


def deal_id_for(path, kwargs):
    """The deal a request is about, or None if it isn't about one deal."""
    from django.apps import apps
    if path.startswith('/api/deals/') and 'pk' in kwargs:
        return kwargs['pk']
    if path.endswith('/payment-plan/') and kwargs.get('owner') in ('deals', 'orders'):
        if kwargs['owner'] == 'deals':
            return kwargs.get('oid')
        model, field = apps.get_model('logistics.SupplierOrder'), 'deal_id'
        return model.objects.filter(pk=kwargs.get('oid')).values_list(field, flat=True).first()
    for prefix, kwarg, label, field in OBJECT_ROUTES:
        if path.startswith(prefix) and kwarg in kwargs:
            model = apps.get_model(label)
            return model.objects.filter(pk=kwargs[kwarg]).values_list(field, flat=True).first()
    return None


class DealAccessMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        if not request.path.startswith('/api/') or request.path.startswith('/api/auth/'):
            return None
        # Signed in with a token? (DRF authenticates later, inside the view.)
        try:
            from rest_framework_simplejwt.authentication import JWTAuthentication
            found = JWTAuthentication().authenticate(request)
        except Exception:
            return None   # bad/expired token: the view answers 401 as usual
        if not found:
            return None
        user = found[0]
        if getattr(user, 'role', None) != 'sales':
            return None
        deal_id = deal_id_for(request.path, view_kwargs)
        if deal_id is None:
            return None
        from apps.deals.models import Deal
        if Deal.objects.filter(pk=deal_id, owner=user).exists():
            return None
        return JsonResponse({'detail': 'Not found.'}, status=404)
