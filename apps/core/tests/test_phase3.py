"""Editable supplier quotes, awards cleared on lines not ordered, company details,
volumetric weight, credit notes, copying a deal, the overrides list, the timezone."""
from django.conf import settings

from apps.deals.models import DealItem, DealItemSplit
from apps.quotes.models import SupplierQuoteItem
from .base import SadacoTestCase


class SupplierQuoteEditTests(SadacoTestCase):
    def test_edit_header_and_quick_lead_time(self):
        D = self.deal()['id']
        i1, i2 = self.item(D, 'Bearing', 10, n=1), self.item(D, 'Seal', 5, n=2)
        q = self.quote(D, self.supplier('Grainger'), lead_time_days=14)
        self.price(D, q, i1, 9)
        self.price(D, q, i2, 50, lead_time_days=30)              # its own lead time
        r = self.put(f"/api/deals/{D}/quotes/{q['id']}/", {'payment_terms': 'Net 60', 'supplier_ref': 'GQ-77', 'lead_time_days': 21})
        self.assertEqual((r['payment_terms'], r['supplier_ref'], r['lead_time_days']), ('Net 60', 'GQ-77', 21))
        leads = dict(SupplierQuoteItem.objects.values_list('deal_item_id', 'lead_time_days'))
        self.assertEqual((leads[i1['id']], leads[i2['id']]), (21, 30))
        self.ok(self.api.put(f"/api/deals/{D}/quotes/{q['id']}/", {'lead_time_days': 'soon'}, format='json'), 400)


class LostLineAwardTests(SadacoTestCase):
    def test_processing_a_partial_po_clears_awards_on_lines_not_ordered(self):
        D = self.deal()['id']
        its = [self.item(D, n, 10, cost=5, price=10, n=k + 1) for k, n in enumerate(['A', 'B', 'C'])]
        g, m = self.supplier('G'), self.supplier('M')
        qg, qm = self.quote(D, g), self.quote(D, m)
        self.award(D, its[0], qg, 10, 5)
        self.award(D, its[1], qg, 6, 5)
        self.award(D, its[1], qm, 4, 5)                          # line B split between two suppliers
        self.award(D, its[2], qm, 10, 5)
        self.win(D, lines=[{'deal_item': its[0]['id'], 'qty': 10}, {'deal_item': its[2]['id'], 'qty': 10}])
        self.assertFalse(DealItemSplit.objects.filter(parent_item_id=its[1]['id']).exists())
        self.assertFalse(DealItem.objects.filter(deal_id=D, is_split_child=True, description='B').exists())
        self.assertTrue(DealItemSplit.objects.filter(parent_item_id=its[0]['id']).exists())
        acts = [a['description'] for a in self.get(f'/api/deals/{D}/timeline/')]
        self.assertTrue(any("Awards removed from lines the client didn't order: line 2" in a for a in acts))


class CompanyDetailsTests(SadacoTestCase):
    def test_admin_edits_bank_details_others_cannot(self):
        name = 'SADACO INTERNATIONAL LLC'
        body = {'name': name, 'details': {'tax_id': '12-3456789', 'bank_accounts': {'USD': {
            'beneficiary': name, 'bank': 'Bank of America', 'swift': 'BOFAUS3N', 'account': '0001112223', 'aba': '026009593'}}}}
        merged = self.put('/api/config/company/', body)
        self.assertEqual(merged[name]['bank_accounts']['USD']['account'], '0001112223')
        self.assertEqual(merged[name]['tax_id'], '12-3456789')
        self.assertEqual(merged[name]['address_line1'], settings.SELLER_ENTITIES[name]['address_line1'])   # defaults kept
        self.assertEqual(self.get('/api/config/seller-entities/')[name]['bank_accounts']['USD']['swift'], 'BOFAUS3N')
        sales = self.as_user(self.user('s@test.com', 'sales'))
        self.ok(sales.put('/api/config/company/', body, format='json'), 403)
        self.ok(self.api.put('/api/config/company/', {'name': 'NOT A SADACO ENTITY', 'details': {}}, format='json'), 400)


class VolumetricTests(SadacoTestCase):
    def test_chargeable_weight_is_the_higher_of_actual_and_volumetric(self):
        D = self.deal()['id']
        heavy = self.item(D, 'Steel shaft', 1, n=1)            # 20 kg, small box → actual counts
        bulky = self.item(D, 'Foam filter', 2, n=2)            # 1 kg each, 60×40×40 cm → 19.2 kg volumetric (÷5000)
        r = self.post(f'/api/deals/{D}/freight-estimate/', {
            'lines': [{'deal_item': heavy['id'], 'unit_kg': 20, 'dims_cm': [100, 10, 10]},
                      {'deal_item': bulky['id'], 'unit_kg': 1, 'dims_cm': [60, 40, 40]}],
            'legs': [{'category': 'freight_miami', 'rate_per_kg': 1, 'volumetric_divisor': 5000},
                     {'category': 'freight_intl', 'rate_per_kg': 1}]}, code=200)
        rows = {c['category']: c for c in r['costs']}
        # Courier leg: shaft 20 (vs 2 volumetric) + filters max(2, 2×19.2=38.4) = 58.4
        self.assertEqual(rows['freight_miami']['estimate_amount'], 58.4)
        self.assertIn('chargeable weight (÷5000)', rows['freight_miami']['description'])
        # International leg, actual weight only: 20 + 2 = 22
        self.assertEqual(rows['freight_intl']['estimate_amount'], 22.0)
        est = self.get(f'/api/deals/{D}/freight-estimate/')['estimate']
        self.assertEqual([l['dims_cm'] for l in est['lines']], [[100, 10, 10], [60, 40, 40]])
        self.assertEqual({l['category']: l['volumetric_divisor'] for l in est['legs']}, {'freight_miami': 5000, 'freight_intl': None})


class CreditNoteTests(SadacoTestCase):
    def setUp(self):
        super().setUp()
        self.D = self.deal()['id']
        it = self.item(self.D, 'Bearing', 10, cost=50, price=100)
        q = self.quote(self.D, self.supplier('G'))
        self.award(self.D, it, q, 10, 50)
        self.win(self.D)
        self.inv = self.post(f'/api/deals/{self.D}/client-invoices/', {'number': 'F-1', 'amount': 1000})['invoices'][0]

    def test_credit_note_reduces_what_is_owed(self):
        m = self.post(f"/api/client-invoices/{self.inv['id']}/credit-note/", {'amount': 200, 'reason': 'Two bearings returned'})
        rows = {r['number']: r for r in m['invoices']}
        self.assertEqual((rows['F-1']['balance'], rows['F-1']['credited'], rows['F-1']['credit_notes']), (800.0, 200.0, ['F-1-NC1']))
        self.assertEqual((rows['F-1-NC1']['kind'], rows['F-1-NC1']['status'], rows['F-1-NC1']['credits_number']), ('credit', 'credit', 'F-1'))
        self.assertEqual((m['client']['invoiced'], m['client']['to_collect']), (800.0, 800.0))
        self.ok(self.api.post(f"/api/client-invoices/{self.inv['id']}/credit-note/", {'amount': 900, 'reason': 'x'}, format='json'), 400)
        self.ok(self.api.post(f"/api/client-invoices/{self.inv['id']}/credit-note/", {'amount': 10}, format='json'), 400)
        self.ok(self.api.post(f"/api/client-invoices/{rows['F-1-NC1']['id']}/payments/", {'amount': 5}, format='json'), 400)
        m = self.post(f"/api/client-invoices/{self.inv['id']}/payments/", {'amount': 800})
        self.assertEqual({r['number']: r['status'] for r in m['invoices']}, {'F-1': 'paid', 'F-1-NC1': 'credit'})
        recv = self.get('/api/finance/receivables/', all='1')['rows']
        self.assertEqual([r['number'] for r in recv], ['F-1'])  # credit notes aren't receivables


class CopyDealTests(SadacoTestCase):
    def test_copy_for_a_repeat_order(self):
        D = self.deal(incoterm='CIF', port_location='La Guaira', payment_terms='30% anticipado / 70% a 30 días')['id']
        self.item(D, 'Bearing', 10, cost=5, price=12, n=1, brand='SKF')
        self.item(D, 'Seal', 2, cost=40, price=90, n=2)
        self.put(f'/api/deals/{D}/cost-settings/', {'target_margin_pct': 40})
        new = self.post(f'/api/deals/{D}/copy/', {'copy_prices': False})
        nd = self.get(f"/api/deals/{new['id']}/")
        self.assertEqual((nd['incoterm'], nd['port_location'], nd['payment_terms'], nd['status']), ('CIF', 'La Guaira', '30% anticipado / 70% a 30 días', 'Quoting'))
        items = [i for i in self.get(f"/api/deals/{new['id']}/items/") if not i['is_split_child']]
        self.assertEqual([(i['description'], i['brand'], float(i['qty']), float(i['unit_price']), float(i['margin_pct'])) for i in items],
                         [('Bearing', 'SKF', 10.0, 0.0, 0.4), ('Seal', '', 2.0, 0.0, 0.4)])
        with_prices = self.post(f'/api/deals/{D}/copy/', {'copy_prices': True})
        prices = [float(i['unit_price']) for i in self.get(f"/api/deals/{with_prices['id']}/items/") if not i['is_split_child']]
        self.assertEqual(prices, [12.0, 90.0])
        ops = self.as_user(self.user('o@test.com', 'operations'))
        self.ok(ops.post(f'/api/deals/{D}/copy/', {}, format='json'), 403)


class OverridesAndTimeTests(SadacoTestCase):
    def test_overrides_list_is_admin_only(self):
        D = self.deal()['id']
        it = self.item(D, 'Bearing', 1, cost=10, price=20)
        q = self.quote(D, self.supplier('G'))
        self.award(D, it, q, 1, 10)
        self.post(f'/api/deals/{D}/orders/from-awards/', {'override_reason': 'Client confirmed by phone, PO to follow'})
        rows = self.get('/api/overrides/')
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]['deal_reference'], rows[0]['by'], rows[0]['reason']), ('7-0001', 'Admin', 'Client confirmed by phone, PO to follow'))
        self.assertTrue(rows[0]['rule'].startswith("The client's purchase order"))
        self.ok(self.as_user(self.user('f@test.com', 'finance')).get('/api/overrides/'), 403)

    def test_timezone_is_venezuela(self):
        self.assertEqual(settings.TIME_ZONE, 'America/Caracas')
