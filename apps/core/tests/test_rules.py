"""Payment rules on supplier orders and shipments, with admin overrides."""
from .base import SadacoTestCase, days


class PaymentRuleTests(SadacoTestCase):
    def setUp(self):
        super().setUp()
        self.ops = self.user('ops@test.com', 'operations')
        self.g = self.supplier('Grainger')
        self.put(f'/api/suppliers/{self.g.id}/payment-plan/', {'steps': [{'pct': 50, 'when': 'on_order'}, {'pct': 50, 'when': 'before_shipping'}]})
        self.m = self.supplier('Motion', terms='Net 30')
        self.D = self.deal()['id']
        i1 = self.item(self.D, 'Bearing', 10, cost=60, price=100, n=1)
        i2 = self.item(self.D, 'Seal', 1, cost=150, price=200, n=2)
        qg, qm = self.quote(self.D, self.g), self.quote(self.D, self.m)
        self.award(self.D, i1, qg, 10, 60)
        self.award(self.D, i2, qm, 1, 150)
        self.win(self.D)
        self.orders = {o['supplier_name']: o for o in self.post(f'/api/deals/{self.D}/orders/from-awards/', {})}
        for o in self.orders.values():
            self.put(f"/api/orders/{o['id']}/", {'status': 'sent'})

    def ship(self, order, **kw):
        body = {'leg': 'to_miami', 'mode': 'courier', 'orders': [order['id']], 'status': 'in_transit', **kw}
        return self.api.post(f'/api/deals/{self.D}/shipments/', body, format='json')

    def test_prepaid_supplier_needs_invoice_payment_and_tracking(self):
        G = self.orders['Grainger']
        r = self.ship(G)
        codes = {g['code'] for g in r.json()['gates']}
        self.assertEqual((r.status_code, codes), (409, {'tracking', 'supplier_payment'}))
        bill = [p for p in self.post(f'/api/deals/{self.D}/payables/', {'supplier_order': G['id'], 'invoice_ref': 'G-1'}, api=self.as_user(self.ops))['payables']
                if p['po_number'] == G['po_number']][0]
        self.assertEqual([(i['pct'], i['when']) for i in bill['installments']], [(50, 'on_order'), (50, 'before_shipping')])
        self.post(f"/api/payables/{bill['id']}/payments/", {'amount': 300})
        self.assertIn('Pay USD 300.00 more', self.ship(G, tracking_number='1Z').json()['error'])
        self.post(f"/api/payables/{bill['id']}/payments/", {'amount': 300})
        self.ok(self.ship(G, tracking_number='1Z'), 201)
        self.assertEqual(self.get(f"/api/orders/{G['id']}/")['status'], 'shipped')

    def test_supplier_on_credit_ships_and_bill_is_due_after_shipping(self):
        M = self.orders['Motion']
        self.ok(self.ship(M, tracking_number='FX7'), 201)
        bill = [p for p in self.post(f'/api/deals/{self.D}/payables/', {'supplier_order': M['id'], 'invoice_ref': 'M-5'})['payables']
                if p['po_number'] == M['po_number']][0]
        self.assertEqual(bill['due_date'], days(30).isoformat())

    def test_override_needs_admin_and_a_reason(self):
        G = self.orders['Grainger']
        r = self.as_user(self.ops).post(f'/api/deals/{self.D}/shipments/', {'leg': 'to_miami', 'mode': 'courier', 'orders': [G['id']],
                                        'status': 'in_transit', 'override_reason': 'trust me'}, format='json')
        self.assertEqual((r.status_code, r.json()['error']), (409, 'Only an admin can override payment rules.'))
        self.assertIn('at least', self.ship(G, override_reason='ok').json()['error'])
        self.ok(self.ship(G, override_reason='Supplier agreed to ship; invoice to follow'), 201)
        acts = [a['description'] for a in self.get(f'/api/deals/{self.D}/timeline/')]
        self.assertTrue(any(a.startswith('Payment rule overridden by Admin') for a in acts))
