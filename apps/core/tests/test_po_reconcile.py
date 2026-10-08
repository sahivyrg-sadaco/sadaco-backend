"""Processing a client PO that differs from the quote: reconciliation, accepted differences, editing before processing."""
from apps.clientquotes.models import ClientPO
from .base import SadacoTestCase


class PoReconcileTests(SadacoTestCase):
    def setUp(self):
        super().setUp()
        self.D = self.deal()['id']
        self.its = [self.item(self.D, n, q, cost=5, price=10, n=k + 1) for k, (n, q) in enumerate([('A', 100), ('B', 20), ('C', 10)])]
        q = self.post(f'/api/deals/{self.D}/client-quotes/', {})['quotes'][0]
        self.post(f"/api/client-quotes/{q['id']}/sent/", {}, code=200)
        self.qid = q['id']

    def record(self, lines, amount=None):
        body = {'quote': self.qid, 'po_number': 'PO-77', 'lines': lines}
        if amount is not None:
            body['amount'] = amount
        return self.post(f'/api/deals/{self.D}/client-pos/', body)['pos'][0]

    def process(self, po, checks, **kw):
        return self.api.post(f"/api/client-pos/{po['id']}/process/", {'checks': checks, **kw}, format='json')

    def test_reconciliation_shows_each_line(self):
        po = self.record([{'deal_item': self.its[0]['id'], 'qty': 70}, {'deal_item': self.its[1]['id'], 'qty': 20}])
        r = po['reconcile']
        self.assertEqual([(l['n'], l['quoted_qty'], l['po_qty'], l['status']) for l in r['lines']],
                         [(1, 100.0, 70.0, 'reduced'), (2, 20.0, 20.0, 'match'), (3, 10.0, 0.0, 'not_ordered')])
        self.assertEqual((r['items_match'], r['items_summary']), (False, '1 line(s) not ordered, 1 with a smaller quantity'))
        self.assertEqual((r['ordered_value'], r['amount_match']), (900.0, True))

    def test_differences_must_be_accepted_not_confirmed_as_matching(self):
        po = self.record([{'deal_item': self.its[0]['id'], 'qty': 70}])
        r = self.process(po, {'items': 'match', 'amount': 'match', 'terms': 'match'})
        self.assertEqual(r.status_code, 400)
        self.assertIn('differ from the quote', r.json()['error'])
        self.ok(self.process(po, {'items': 'accepted', 'amount': 'match', 'terms': 'match'}))
        p = ClientPO.objects.get(pk=po['id'])
        self.assertEqual((p.status, p.checks['items'], p.checks['items_summary']),
                         ('processed', 'accepted', '2 line(s) not ordered, 1 with a smaller quantity'))

    def test_amount_and_terms_differences(self):
        po = self.record([{'deal_item': i['id'], 'qty': i['qty']} for i in self.its], amount=1250)
        self.assertEqual(po['reconcile']['amount_diff'], -50.0)
        self.assertEqual(self.process(po, {'items': 'match', 'amount': 'match', 'terms': 'match'}).status_code, 400)
        r = self.process(po, {'items': 'match', 'amount': 'accepted', 'terms': 'differ'}, terms_note='')
        self.assertEqual(r.status_code, 400)
        self.ok(self.process(po, {'items': 'match', 'amount': 'accepted', 'terms': 'differ'},
                             terms_note='Client asked 45 days instead of 30'))
        acts = ' '.join(a['description'] for a in self.get(f'/api/deals/{self.D}/timeline/'))
        self.assertIn('by USD -50.00 (accepted)', acts)
        self.assertIn('Terms differ from the quote (accepted): Client asked 45 days instead of 30', acts)

    def test_edit_a_wrongly_recorded_po_before_processing(self):
        po = self.record([{'deal_item': self.its[0]['id'], 'qty': 70}])
        fixed = self.put(f"/api/client-pos/{po['id']}/", {
            'lines': [{'deal_item': i['id'], 'qty': i['qty']} for i in self.its], 'po_number': 'PO-77B'})['pos'][0]
        self.assertEqual((fixed['po_number'], fixed['amount'], fixed['reconcile']['items_match']), ('PO-77B', 1300.0, True))
        self.ok(self.process(fixed, {'items': 'match', 'amount': 'match', 'terms': 'match'}))
        self.ok(self.api.put(f"/api/client-pos/{po['id']}/", {'po_number': 'X'}, format='json'), 400)   # processed now

    def test_old_style_true_checks_still_work(self):
        po = self.record([{'deal_item': self.its[0]['id'], 'qty': 70}])
        self.ok(self.process(po, {'items': True, 'amount': True, 'terms': True}))
        self.assertEqual(ClientPO.objects.get(pk=po['id']).checks['items'], 'accepted')
