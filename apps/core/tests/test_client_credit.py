"""Credit notes in the P&L, client credit from overpayments, refunds, and applying credit to another deal."""
from apps.clients.models import Client
from apps.payments.models import Payment
from .base import SadacoTestCase


class CreditNotesInPnlTests(SadacoTestCase):
    def test_credit_note_reduces_revenue_and_margin(self):
        D = self.deal()['id']
        it = self.item(D, 'Filter', 10, cost=30, price=60)
        q = self.quote(D, self.supplier('G'))
        self.award(D, it, q, 10, 30)
        self.win(D)
        before = self.get(f'/api/deals/{D}/costs/')['economics']
        inv = self.post(f'/api/deals/{D}/client-invoices/', {'number': 'F-1', 'amount': 600})['invoices'][0]
        self.post(f"/api/client-invoices/{inv['id']}/credit-note/", {'amount': 60, 'reason': 'One filter returned'})
        e = self.get(f'/api/deals/{D}/costs/')['economics']
        self.assertEqual((before['estimate']['revenue'], e['estimate']['revenue'], e['actual_so_far']['revenue']), (600.0, 540.0, 540.0))
        self.assertEqual(e['credit_notes'], 60.0)
        self.assertEqual(e['estimate']['net_profit'], 240.0)
        self.assertEqual(self.get('/api/deals/')[0]['economics']['revenue'], 540.0)


class ClientCreditTests(SadacoTestCase):
    def setUp(self):
        super().setUp()
        self.g = self.supplier('G')

    def won_deal(self, price, terms='Net 30'):
        D = self.deal(payment_terms=terms)['id']
        it = self.item(D, 'Part', 10, cost=price / 2, price=price)
        q = self.quote(D, self.g)
        self.award(D, it, q, 10, price / 2)
        self.win(D)
        return D

    def credit(self):
        return self.get(f'/api/clients/{self.cl.id}/credit/')

    def test_overpayment_and_credit_after_payment_become_client_credit(self):
        A = self.won_deal(100)
        inv = self.post(f'/api/deals/{A}/client-invoices/', {'number': 'A-1', 'amount': 1000})['invoices'][0]
        self.post(f"/api/client-invoices/{inv['id']}/payments/", {'amount': 1000})
        m = self.post(f"/api/client-invoices/{inv['id']}/credit-note/", {'amount': 60, 'reason': 'Price correction'})
        row = [r for r in m['invoices'] if r['number'] == 'A-1'][0]
        self.assertEqual((row['status'], row['balance'], row['excess']), ('paid', 0.0, 60.0))
        self.assertEqual(m['client_credit']['available'], 60.0)
        c = self.credit()['by_currency']['USD']
        self.assertEqual((c['available'], [s['number'] for s in c['sources']]), (60.0, ['A-1']))

    def test_refund_and_undo(self):
        A = self.won_deal(100)
        inv = self.post(f'/api/deals/{A}/client-invoices/', {'number': 'A-1', 'amount': 1000})['invoices'][0]
        self.post(f"/api/client-invoices/{inv['id']}/payments/", {'amount': 1050})        # overpaid by 50
        self.ok(self.api.post(f'/api/clients/{self.cl.id}/credit/refund/', {'currency': 'USD', 'amount': 80}, format='json'), 400)
        s = self.post(f'/api/clients/{self.cl.id}/credit/refund/', {'currency': 'USD', 'amount': 50, 'method': 'Wire', 'notes': 'Ref 991'})
        self.assertEqual(s['by_currency'], {})
        self.assertEqual((s['history'][0]['kind'], s['history'][0]['amount']), ('refund', 50.0))
        self.assertEqual(self.get(f'/api/deals/{A}/money/')['client']['received'], 1000.0)   # net of the refund
        self.ok(self.api.delete(f"/api/client-credit/{s['history'][0]['group']}/"), 204)
        self.assertEqual(self.credit()['by_currency']['USD']['available'], 50.0)

    def test_apply_credit_to_another_deal_unlocks_its_advance(self):
        A = self.won_deal(100)
        inv_a = self.post(f'/api/deals/{A}/client-invoices/', {'number': 'A-1', 'amount': 1000})['invoices'][0]
        self.post(f"/api/client-invoices/{inv_a['id']}/payments/", {'amount': 1000})
        self.post(f"/api/client-invoices/{inv_a['id']}/credit-note/", {'amount': 300, 'reason': 'Three parts returned'})
        B = self.won_deal(100, terms='30% anticipado / 70% a 30 días')
        inv_b = self.post(f'/api/deals/{B}/client-invoices/', {'number': 'B-1', 'amount': 300})['invoices'][0]
        self.assertEqual(self.api.post(f'/api/deals/{B}/orders/from-awards/', {}, format='json').status_code, 409)
        self.ok(self.api.post(f'/api/clients/{self.cl.id}/credit/apply/', {'invoice': inv_b['id'], 'amount': 400}, format='json'), 400)
        s = self.post(f'/api/clients/{self.cl.id}/credit/apply/', {'invoice': inv_b['id'], 'amount': 300})
        self.assertEqual(s['by_currency'], {})
        h = s['history'][0]
        self.assertEqual((h['kind'], h['amount'], h['from'][0]['number'], h['to']['number']), ('applied', 300.0, 'A-1', 'B-1'))
        mb = self.get(f'/api/deals/{B}/money/')
        self.assertEqual((mb['invoices'][0]['status'], mb['client']['received']), ('paid', 300.0))
        ma = self.get(f'/api/deals/{A}/money/')
        self.assertEqual((ma['invoices'][0]['excess'], ma['client']['received']), (0.0, 700.0))   # no double counting
        self.post(f'/api/deals/{B}/orders/from-awards/', {})                                      # advance met by credit
        # Removing the credit payment on B undoes both sides.
        pay_b = Payment.objects.get(invoice_ref='B-1', kind='credit_in')
        self.ok(self.api.delete(f'/api/client-payments/{pay_b.id}/'))
        self.assertFalse(Payment.objects.filter(transfer_group=h['group']).exists())
        self.assertEqual(self.credit()['by_currency']['USD']['available'], 300.0)

    def test_credit_stays_with_its_client_and_currency(self):
        A = self.won_deal(100)
        inv = self.post(f'/api/deals/{A}/client-invoices/', {'number': 'A-1', 'amount': 1000})['invoices'][0]
        self.post(f"/api/client-invoices/{inv['id']}/payments/", {'amount': 1100})
        other = Client.objects.create(dropdown_name='CVG', full_name='CVG Alucasa', code=8)
        D2 = self.post('/api/deals/', {'client': other.id, 'seller_entity': 'X', 'currency': 'USD'})['id']
        it = self.item(D2, 'Part', 1, cost=50, price=100)
        q = self.quote(D2, self.g)
        self.award(D2, it, q, 1, 50)
        self.win(D2)
        inv2 = self.post(f'/api/deals/{D2}/client-invoices/', {'number': 'C-1', 'amount': 100})['invoices'][0]
        r = self.api.post(f'/api/clients/{self.cl.id}/credit/apply/', {'invoice': inv2['id'], 'amount': 50}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertIn('different client', r.json()['error'])
