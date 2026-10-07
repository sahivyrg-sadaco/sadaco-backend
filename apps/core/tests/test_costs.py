"""Extra costs, the P&L, freight by weight, landed cost and recalculated prices."""
from apps.costs.models import DealCost
from apps.deals.models import DealItem
from .base import SadacoTestCase


class EconomicsTests(SadacoTestCase):
    def test_cif_percentages_and_currency(self):
        d = self.deal(incoterm='CIF')
        D = d['id']
        self.item(D, 'Bearing', 10, cost=10, price=20)
        # All costs billed separately for this deal, to check revenue too.
        self.put(f'/api/deals/{D}/cost-settings/', {'default_treatment': 'separate'})
        rows = self.post(f'/api/deals/{D}/costs/typical/', {})['costs']
        ids = {r['category']: r['id'] for r in rows}
        self.put(f"/api/costs/{ids['freight_miami']}/", {'estimate_amount': 20})
        self.put(f"/api/costs/{ids['forwarder']}/", {'estimate_amount': 30})
        self.put(f"/api/costs/{ids['freight_intl']}/", {'estimate_amount': 50})
        self.put(f"/api/costs/{ids['insurance']}/", {'percent': 1})
        self.post(f'/api/deals/{D}/costs/', {'category': 'duties', 'amount_type': 'percent', 'percent': 5, 'percent_base': 'cif_value'})
        self.ok(self.api.post(f'/api/deals/{D}/costs/', {'category': 'customs_broker', 'estimate_amount': 3600,
                                                         'currency': 'VES', 'fx_rate': 0}, format='json'), 400)
        self.post(f'/api/deals/{D}/costs/', {'category': 'customs_broker', 'estimate_amount': 3600, 'currency': 'VES', 'fx_rate': 36})
        e = self.post(f'/api/deals/{D}/costs/', {'category': 'bank', 'estimate_amount': 15, 'client_treatment': 'included'})['economics']
        # CIF = 100 goods + 20 + 30 + 50 = 200, insurance 1% = 2 → 202; duties 5% of 202 = 10.10; broker 3600/36 = 100
        self.assertEqual(e['cif_value']['estimate'], 202.0)
        self.assertEqual(e['separate_charges'], 212.1)
        self.assertEqual(e['estimate']['revenue'], 412.1)
        self.assertEqual(e['estimate']['extra_costs'], 227.1)
        self.assertEqual(e['estimate']['net_profit'], 85.0)
        self.assertEqual(e['estimate']['net_margin_pct'], 20.6)
        self.assertEqual(e['gross_margin_pct'], 50.0)

    def test_default_treatment_is_built_in_for_every_incoterm(self):
        for term in ['DDP', 'CIF', 'EXW', '']:
            d = self.deal(incoterm=term)
            e = self.get(f"/api/deals/{d['id']}/costs/")['economics']
            self.assertEqual((e['default_treatment'], e['default_treatment_source']), ('included', 'standard'), term)

    def test_shipment_freight_attaches_to_estimate_and_overrun_reaches_board(self):
        d = self.deal()
        D = d['id']
        self.item(D, 'Bearing', 10, cost=10, price=20)
        self.post(f'/api/deals/{D}/costs/', {'category': 'freight_miami', 'estimate_amount': 20})
        s = self.post(f'/api/deals/{D}/shipments/', {'leg': 'to_miami', 'mode': 'truck', 'freight_cost': 26, 'freight_currency': 'USD'})
        rows = [c for c in self.get(f'/api/deals/{D}/costs/')['costs'] if c['category'] == 'freight_miami']
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]['estimate_amount'], rows[0]['actual_amount']), (20.0, 26.0))
        board = self.get('/api/tracking/attention/')['entries']
        self.assertTrue(any(e['kind'] == 'cost' and '30%' in e['flags'][0]['text'] for e in board))
        # Removing the freight keeps the estimate row, unlinked; deleting a shipment-only row removes it.
        self.put(f"/api/shipments/{s['id']}/", {'freight_cost': None})
        row = DealCost.objects.get(deal_id=D, category='freight_miami')
        self.assertEqual((float(row.estimate_amount), row.actual_amount, row.shipment_id), (20.0, None, None))

    def test_supplier_invoice_difference_feeds_actual_goods(self):
        d = self.deal()
        D = d['id']
        it = self.item(D, 'Bearing', 10, cost=10, price=20)
        g = self.supplier('Grainger')
        q = self.quote(D, g)
        self.award(D, it, q, 10, 10)
        self.win(D)
        o = self.post(f'/api/deals/{D}/orders/from-awards/', {})[0]
        self.post(f'/api/deals/{D}/payables/', {'supplier_order': o['id'], 'invoice_ref': 'G-1', 'amount': o['total'] + 30})
        e = self.get(f'/api/deals/{D}/costs/')['economics']
        self.assertEqual((e['estimate']['goods'], e['actual_so_far']['goods'], e['goods_invoice_difference']), (100.0, 130.0, 30.0))


class FreightAndLandedTests(SadacoTestCase):
    def setUp(self):
        super().setUp()
        d = self.deal()
        self.D = d['id']
        self.i1 = self.item(self.D, 'Bearing', 100, cost=10, price=20, n=1)
        self.i2 = self.item(self.D, 'Seal', 10, cost=100, price=200, n=2)
        g = self.supplier('Grainger')
        self.q = self.quote(self.D, g, lead_time_days=14)
        self.price(self.D, self.q, self.i1, 10, unit_weight_kg=0.1)
        self.price(self.D, self.q, self.i2, 100, unit_weight_kg=3, lead_time_days=30)

    def test_quote_lead_time_fills_items_without_their_own(self):
        from apps.quotes.models import SupplierQuoteItem
        leads = dict(SupplierQuoteItem.objects.values_list('deal_item_id', 'lead_time_days'))
        self.assertEqual((leads[self.i1['id']], leads[self.i2['id']]), (14, 30))

    def test_estimate_split_by_weight_with_minimum(self):
        r = self.post(f'/api/deals/{self.D}/freight-estimate/', {
            'lines': [{'deal_item': self.i1['id'], 'unit_kg': 0.1}, {'deal_item': self.i2['id'], 'unit_kg': 3}],
            'legs': [{'category': 'freight_miami', 'rate_per_kg': 1, 'min_charge': 80, 'transit_days': 5},
                     {'category': 'freight_intl', 'rate_per_kg': 5, 'transit_days': 21}]}, code=200)
        rows = {c['category']: c for c in r['costs']}
        # 10 kg + 30 kg = 40 kg; Miami 40 × 1 = 40 → minimum 80; international 40 × 5 = 200
        self.assertEqual(rows['freight_miami']['estimate_amount'], 80.0)
        self.assertEqual(rows['freight_intl']['estimate_amount'], 200.0)
        self.assertAlmostEqual(sum(r['freight_by_item'].values()), 280.0, places=2)
        legs = {l['category']: l['transit_days'] for l in r['estimate']['legs']}
        self.assertEqual(legs, {'freight_miami': 5, 'freight_intl': 21})
        self.assertEqual(r['estimate']['max_lead_time_days'], 30)

    def test_landed_cost_and_recalculated_prices(self):
        self.post(f'/api/deals/{self.D}/freight-estimate/', {
            'lines': [{'deal_item': self.i1['id'], 'unit_kg': 0.1}, {'deal_item': self.i2['id'], 'unit_kg': 3}],
            'legs': [{'category': 'freight_intl', 'rate_per_kg': 5}]}, code=200)
        self.post(f'/api/deals/{self.D}/costs/', {'category': 'bank', 'estimate_amount': 100})
        lines = {l['n']: l for l in self.get(f'/api/deals/{self.D}/landed/')['lines']}
        # Bearing: 10 + 0.50 freight + 0.50 bank = 11 → 22 at 50%. Seal: 100 + 15 + 5 = 120 → 240.
        self.assertEqual((lines[1]['landed_unit'], lines[1]['suggested_price']), (11.0, 22.0))
        self.assertEqual((lines[2]['landed_unit'], lines[2]['suggested_price']), (120.0, 240.0))
        r = self.post(f'/api/deals/{self.D}/landed/apply/', {'target_margin_pct': 50, 'items': [self.i1['id'], self.i2['id']]}, code=200)
        self.assertEqual(r['changed'], 2)
        self.assertEqual(self.get(f'/api/deals/{self.D}/costs/')['economics']['estimate']['net_margin_pct'], 50.0)
        self.assertEqual(float(DealItem.objects.get(pk=self.i1['id']).unit_price), 22.0)

    def test_target_margin_default_and_override(self):
        e = self.get(f'/api/deals/{self.D}/costs/')['economics']
        self.assertEqual((e['target_margin_pct'], e['target_margin_source']), (50.0, 'company'))
        e = self.put(f'/api/deals/{self.D}/cost-settings/', {'target_margin_pct': 35})['economics']
        self.assertEqual((e['target_margin_pct'], e['target_margin_source']), (35.0, 'deal'))
        self.ok(self.api.put(f'/api/deals/{self.D}/cost-settings/', {'target_margin_pct': 120}, format='json'), 400)
