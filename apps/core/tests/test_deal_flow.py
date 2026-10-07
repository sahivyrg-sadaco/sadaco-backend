"""Quote → client PO (all or some lines) → invoices → supplier orders → shipments → stages."""
from apps.clientquotes.models import ClientQuote
from .base import SadacoTestCase, days


class ClientFlowTests(SadacoTestCase):
    def setUp(self):
        super().setUp()
        self.D = self.deal(incoterm='CIF', port_location='La Guaira')['id']
        self.its = [self.item(self.D, 'Bearing', 100, cost=10, price=20, n=1),
                    self.item(self.D, 'Seal', 20, cost=50, price=100, n=2),
                    self.item(self.D, 'Gasket', 10, cost=3, price=6, n=3)]
        self.g, self.m = self.supplier('Grainger'), self.supplier('Motion')
        self.qg, self.qm = self.quote(self.D, self.g), self.quote(self.D, self.m)
        self.award(self.D, self.its[0], self.qg, 60, 10)
        self.award(self.D, self.its[0], self.qm, 40, 10.5)
        self.award(self.D, self.its[1], self.qm, 20, 50)
        self.award(self.D, self.its[2], self.qg, 10, 3)

    def test_quote_needs_prices_and_snapshots(self):
        d2 = self.deal()['id']
        self.item(d2, 'No price', 1)
        self.ok(self.api.post(f'/api/deals/{d2}/client-quotes/', {}, format='json'), 400)
        q = self.post(f'/api/deals/{self.D}/client-quotes/', {})['quotes'][0]
        self.assertEqual((q['number'], q['status'], q['language'], q['total']), (f'7-0001-Q1', 'draft', 'es', 2000 + 2000 + 60))
        self.post(f"/api/client-quotes/{q['id']}/sent/", {}, code=200)
        self.assertEqual(self.stage(self.D), 'Negotiating')
        # A new version replaces the old one when sent.
        self.put(f"/api/deals/{self.D}/items/{self.its[0]['id']}/", {'unit_price': 21})
        self.assertTrue(self.get(f'/api/deals/{self.D}/client-quotes/')['quotes'][0]['changed_since'])
        q2 = self.post(f'/api/deals/{self.D}/client-quotes/', {})['quotes'][0]
        self.post(f"/api/client-quotes/{q2['id']}/sent/", {}, code=200)
        statuses = {x['number']: x['status'] for x in self.get(f'/api/deals/{self.D}/client-quotes/')['quotes']}
        self.assertEqual(statuses, {'7-0001-Q1': 'superseded', '7-0001-Q2': 'sent'})

    def test_old_quotes_without_item_ids_still_map(self):
        q = self.post(f'/api/deals/{self.D}/client-quotes/', {})['quotes'][0]
        ClientQuote.objects.filter(pk=q['id']).update(
            lines=[{k: v for k, v in l.items() if k != 'deal_item'} for l in ClientQuote.objects.get(pk=q['id']).lines])
        lines = self.get(f'/api/deals/{self.D}/client-quotes/')['quotes'][0]['lines']
        self.assertEqual([l['deal_item'] for l in lines], [i['id'] for i in self.its])

    def test_partial_po_limits_supplier_orders_and_economics(self):
        orders_blocked = self.api.post(f'/api/deals/{self.D}/orders/from-awards/', {}, format='json')
        self.assertEqual(orders_blocked.status_code, 409)       # no processed PO yet
        po = self.win(self.D, lines=[{'deal_item': self.its[0]['id'], 'qty': 70}, {'deal_item': self.its[1]['id'], 'qty': 20}])
        self.assertEqual(po['amount'], 70 * 20 + 20 * 100)
        cq = self.get(f'/api/deals/{self.D}/client-quotes/')
        self.assertEqual({int(k): v for k, v in cq['won_items'].items()}, {self.its[0]['id']: 70.0, self.its[1]['id']: 20.0})
        e = self.get(f'/api/deals/{self.D}/costs/')['economics']
        self.assertEqual((e['items_sell'], e['goods_cost']), (3400.0, 70 * 10 + 20 * 50))
        orders = self.post(f'/api/deals/{self.D}/orders/from-awards/', {})
        lines = {o['supplier_name']: sorted((i['description'], float(i['qty'])) for i in o['items']) for o in orders}
        # 70 bearings: Grainger's 60 award first, then 10 from Motion. No gaskets.
        self.assertEqual(lines, {'Grainger': [('Bearing', 60.0)], 'Motion': [('Bearing', 10.0), ('Seal', 20.0)]})
        deal = self.get(f'/api/deals/{self.D}/')
        self.assertEqual((deal['status'], deal['deal_status'], deal['client_ref']), ("Client's PO Received", 'won', f'PO-{self.D}'))

    def test_stages_follow_events(self):
        self.win(self.D)
        orders = self.post(f'/api/deals/{self.D}/orders/from-awards/', {})
        for o in orders:
            self.put(f"/api/orders/{o['id']}/", {'status': 'sent'})
        self.assertEqual(self.stage(self.D), 'PO Sent')
        base = self.get(f'/api/deals/{self.D}/money/')['next_invoice']['revenue']
        inv = self.post(f'/api/deals/{self.D}/client-invoices/', {'number': 'F1', 'amount': base})['invoices'][0]
        self.assertEqual(self.stage(self.D), 'Invoiced')
        for o in orders:
            self.post(f'/api/deals/{self.D}/payables/', {'supplier_order': o['id'], 'invoice_ref': f"B{o['id']}"})
            self.post(f'/api/deals/{self.D}/shipments/', {'leg': 'to_miami', 'mode': 'courier', 'tracking_number': f"T{o['id']}",
                                                          'orders': [o['id']], 'status': 'arrived'})
        self.post(f'/api/deals/{self.D}/shipments/', {'leg': 'delivery', 'mode': 'truck', 'status': 'arrived'})
        self.assertEqual(self.stage(self.D), 'Delivered')
        self.post(f"/api/client-invoices/{inv['id']}/payments/", {'amount': inv['amount']})
        self.assertEqual(self.stage(self.D), 'Delivered')       # suppliers not paid yet
        for p in self.get(f'/api/deals/{self.D}/money/')['payables']:
            self.post(f"/api/payables/{p['id']}/payments/", {'amount': p['balance']})
        self.assertEqual(self.stage(self.D), 'Closed')

    def test_search(self):
        self.win(self.D)
        orders = self.post(f'/api/deals/{self.D}/orders/from-awards/', {})
        self.post(f'/api/deals/{self.D}/shipments/', {'leg': 'to_miami', 'mode': 'truck', 'tracking_number': '1ZTEST99'})
        kinds = lambda q: {r['kind'] for r in self.get('/api/search/', q=q)['results']}   # noqa: E731
        self.assertIn('Client PO', kinds(f'PO-{self.D}'))
        self.assertIn('Supplier PO', kinds(orders[0]['po_number']))
        self.assertIn('Tracking', kinds('1ZTEST'))
        self.assertEqual(self.get('/api/search/', q='x')['results'], [])


class InvoicingTests(SadacoTestCase):
    def setUp(self):
        super().setUp()
        self.D = self.deal(payment_terms='30% anticipado / 70% a 30 días')['id']
        self.it = self.item(self.D, 'Bearing', 10, cost=60, price=100)
        g = self.supplier('Grainger')
        q = self.quote(self.D, g)
        self.award(self.D, self.it, q, 10, 60)

    def test_invoice_needs_processed_po_and_suggestions_follow_terms(self):
        r = self.api.post(f'/api/deals/{self.D}/client-invoices/', {'number': 'F1', 'amount': 300}, format='json')
        self.assertEqual(r.status_code, 409)
        self.win(self.D, amount=900)                            # client ordered for 900, not 1000
        nxt = self.get(f'/api/deals/{self.D}/money/')['next_invoice']
        self.assertEqual((nxt['revenue'], nxt['revenue_source']), (900.0, 'po'))
        self.assertEqual([(s['amount'], s['due_days']) for s in nxt['suggestions']], [(270.0, 0), (630.0, 30)])

    def test_orders_wait_for_the_advance_and_payments_are_tracked(self):
        self.win(self.D)
        r = self.api.post(f'/api/deals/{self.D}/orders/from-awards/', {}, format='json')
        self.assertEqual(r.status_code, 409)
        self.assertIn('payment due on order', r.json()['error'])
        inv = self.post(f'/api/deals/{self.D}/client-invoices/', {'number': 'F1', 'amount': 300})['invoices'][0]
        self.ok(self.api.post(f'/api/deals/{self.D}/client-invoices/', {'number': 'F1', 'amount': 5}, format='json'), 400)
        m = self.post(f"/api/client-invoices/{inv['id']}/payments/", {'amount': 100})
        self.assertEqual((m['invoices'][0]['status'], m['invoices'][0]['balance']), ('partial', 200.0))
        self.post(f"/api/client-invoices/{inv['id']}/payments/", {'amount': 200})
        self.post(f'/api/deals/{self.D}/orders/from-awards/', {})
        # Renaming the invoice keeps its payments; deleting one with payments is refused.
        m = self.put(f"/api/client-invoices/{inv['id']}/", {'number': 'INV-2026-015'})
        self.assertEqual((m['invoices'][0]['number'], m['invoices'][0]['paid']), ('INV-2026-015', 300.0))
        self.ok(self.api.delete(f"/api/client-invoices/{inv['id']}/"), 400)

    def test_cost_invoices_become_payables(self):
        c = self.post(f'/api/deals/{self.D}/costs/', {'category': 'forwarder', 'payee': 'Cargo Express', 'estimate_amount': 150})['costs'][0]
        self.put(f"/api/costs/{c['id']}/", {'actual_amount': 175, 'invoice_ref': 'CE-1'})
        p = [x for x in self.get(f'/api/deals/{self.D}/money/')['payables'] if x['kind'] == 'cost']
        self.assertEqual([(x['payee'], x['amount'], x['invoice_ref']) for x in p], [('Cargo Express', 175.0, 'CE-1')])
        self.put(f"/api/costs/{c['id']}/", {'actual_amount': 180})
        self.assertEqual([x['amount'] for x in self.get(f'/api/deals/{self.D}/money/')['payables']], [180.0])
