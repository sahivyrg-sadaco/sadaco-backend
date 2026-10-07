"""Shared set-up for the SADACO test suite: users, an API client, and quick builders."""
import datetime as dt

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.clients.models import Client
from apps.suppliers.models import Supplier

TODAY = timezone.localdate


def days(n):
    return timezone.localdate() + dt.timedelta(days=n)


class SadacoTestCase(TestCase):
    """Every test starts with an admin, a Venezuelan client, and an API client signed in as admin."""

    def setUp(self):
        cache.clear()   # login-attempt counters
        self.admin = User.objects.create_user('admin@test.com', 'Admin', 'admin', 'password-123')
        self.api = self.as_user(self.admin)
        self.cl = Client.objects.create(dropdown_name='SIDOR', full_name='Siderúrgica del Orinoco', code=7,
                                        country='Venezuela', contact_email='compras@sidor.test',
                                        payment_terms='Net 30')

    # ── plumbing ──
    def as_user(self, user):
        c = APIClient()
        c.force_authenticate(user)
        return c

    def user(self, email, role, name=None):
        return User.objects.create_user(email, name or role.title(), role, 'password-123')

    def ok(self, response, code=200):
        self.assertEqual(response.status_code, code, response.content[:500])
        return response.json() if response.content else None

    def post(self, url, data=None, code=201, api=None):
        return self.ok((api or self.api).post(url, data or {}, format='json'), code)

    def put(self, url, data, code=200, api=None):
        return self.ok((api or self.api).put(url, data, format='json'), code)

    def get(self, url, code=200, api=None, **params):
        return self.ok((api or self.api).get(url, params or None), code)

    # ── builders ──
    def supplier(self, name, terms='Net 30', **kw):
        return Supplier.objects.create(company_name=name, payment_terms=terms, **kw)

    def deal(self, **kw):
        data = {'client': self.cl.id, 'seller_entity': 'SADACO INTERNATIONAL LLC', 'currency': 'USD',
                'payment_terms': 'Net 30', **kw}
        return self.post('/api/deals/', data)

    def item(self, deal_id, description, qty, cost=0, price=0, n=1, **kw):
        return self.post(f'/api/deals/{deal_id}/items/', {'description': description, 'qty': qty, 'unit_cost': cost,
                                                          'unit_price': price, 'item_number': n, **kw})

    def quote(self, deal_id, supplier, **kw):
        return self.post(f'/api/deals/{deal_id}/quotes/', {'supplier': supplier.id, **kw})

    def price(self, deal_id, quote, item, unit_price, **kw):
        return self.post(f"/api/deals/{deal_id}/quotes/{quote['id']}/items/",
                         {'deal_item_id': item['id'], 'unit_price': unit_price, **kw})

    def award(self, deal_id, item, quote, qty, cost):
        return self.post(f'/api/deals/{deal_id}/splits/', {'parent_item_id': item['id'], 'supplier_quote_id': quote['id'],
                                                           'qty_awarded': qty, 'unit_cost': cost})

    def win(self, deal_id, lines=None, amount=None):
        """Quote the client, record their PO (optionally only some lines) and process it. Returns the PO."""
        cq = self.post(f'/api/deals/{deal_id}/client-quotes/', {})
        q = cq['quotes'][0]
        self.post(f"/api/client-quotes/{q['id']}/sent/", {}, code=200)
        body = {'quote': q['id'], 'po_number': f'PO-{deal_id}'}
        if lines is not None:
            body['lines'] = lines
        if amount is not None:
            body['amount'] = amount
        po = self.post(f'/api/deals/{deal_id}/client-pos/', body)['pos'][0]
        self.post(f"/api/client-pos/{po['id']}/process/", {'checks': {'items': True, 'amount': True, 'terms': True}}, code=200)
        return po

    def stage(self, deal_id):
        return self.get(f'/api/deals/{deal_id}/')['status']
