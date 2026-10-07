"""Reading payment terms text into payment schedules."""
from django.test import SimpleTestCase

from apps.finance.plans import describe, from_text, validate


class TermsTextTests(SimpleTestCase):
    def test_common_terms(self):
        cases = {
            '100% prepagado': '100% before shipping',
            '30% anticipado / 70% contra entrega': '30% on order, 70% on delivery',
            '50% anticipado / 50% contra entrega': '50% on order, 50% on delivery',
            'Net 30': '100% 30 days after shipping',
            '60 days': '100% 60 days after shipping',
            'Letter of credit (Carta de crédito)': '100% on shipping',
            '50% advance, 50% before shipping': '50% on order, 50% before shipping',
            '30% anticipado / 70% a 30 días': '30% on order, 70% 30 days after shipping',
            'Cash': '100% before shipping',
            '40% anticipado, 30% antes del envío, 30% contra entrega': '40% on order, 30% before shipping, 30% on delivery',
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(describe(from_text(text)), expected)

    def test_unreadable_terms(self):
        self.assertIsNone(from_text('rubbish'))
        self.assertIsNone(from_text(''))

    def test_validate(self):
        with self.assertRaises(ValueError):
            validate([{'pct': 50, 'when': 'on_order'}, {'pct': 40, 'when': 'before_shipping'}])
        with self.assertRaises(ValueError):
            validate([])
        self.assertEqual(validate([{'pct': '100', 'when': 'after_shipping', 'days': '30'}]),
                         [{'pct': 100.0, 'when': 'after_shipping', 'days': 30}])
