"""Changing a deal's payment schedule after the PO: the written terms and printed invoices follow it."""
from apps.finance.plans import describe, describe_es, from_text
from .base import SadacoTestCase


class TermsChangeTests(SadacoTestCase):
    def test_changed_schedule_replaces_old_terms_everywhere(self):
        D = self.deal(payment_terms='100% Prepagado')['id']
        it = self.item(D, 'Bearing', 10, cost=50, price=100)
        q = self.quote(D, self.supplier('G'))
        self.award(D, it, q, 10, 50)
        self.win(D)
        self.put(f'/api/deals/{D}/payment-plan/', {'steps': [{'pct': 50, 'when': 'on_order'}, {'pct': 50, 'when': 'on_delivery'}]})
        deal = self.get(f'/api/deals/{D}/')
        self.assertEqual(deal['payment_terms'], '50% anticipado / 50% contra entrega')
        m = self.get(f'/api/deals/{D}/money/')
        g = m['client_gate']
        self.assertEqual((g['source'], g['plan_text'], g['plan_text_es']),
                         ('deal', '50% on order, 50% on delivery', '50% anticipado / 50% contra entrega'))
        self.assertEqual([s['amount'] for s in m['next_invoice']['suggestions']], [500.0, 500.0])

    def test_spanish_wording_reads_back_as_the_same_schedule(self):
        cases = [[{'pct': 100, 'when': 'on_order'}], [{'pct': 100, 'when': 'before_shipping'}],
                 [{'pct': 100, 'when': 'after_shipping', 'days': 0}],
                 [{'pct': 30, 'when': 'on_order'}, {'pct': 70, 'when': 'after_shipping', 'days': 30}],
                 [{'pct': 50, 'when': 'on_order'}, {'pct': 50, 'when': 'on_delivery'}]]
        for steps in cases:
            with self.subTest(text=describe_es(steps)):
                self.assertEqual(describe(from_text(describe_es(steps))), describe(steps))
