"""Changing where a supplier ships an order."""
from .base import SadacoTestCase


class ShipToTests(SadacoTestCase):
    def setUp(self):
        super().setUp()
        self.D = self.deal()['id']
        it = self.item(self.D, 'Bearing', 10, cost=5, price=10)
        q = self.quote(self.D, self.supplier('G'))
        self.award(self.D, it, q, 10, 5)
        self.win(self.D)
        self.order = self.post(f'/api/deals/{self.D}/orders/from-awards/', {})[0]

    def test_default_is_empty_and_it_can_be_changed_and_reset(self):
        self.assertEqual(self.order['ship_to'], '')
        addr = 'Cargo Express Miami\n8400 NW 25th St, Doral, FL 33122\nAttn: SADACO / 7-0001'
        o = self.put(f"/api/orders/{self.order['id']}/", {'ship_to': addr + '  '})
        self.assertEqual(o['ship_to'], addr)
        acts = [a['description'] for a in self.get(f'/api/deals/{self.D}/timeline/')]
        self.assertIn(f"Ship-to address for {self.order['po_number']} changed to: Cargo Express Miami.", acts)
        self.assertEqual(self.get('/api/orders/ship-to/'), [addr])
        o = self.put(f"/api/orders/{self.order['id']}/", {'ship_to': ''})
        self.assertEqual(o['ship_to'], '')

    def test_change_after_sending_reminds_to_tell_the_supplier(self):
        self.put(f"/api/orders/{self.order['id']}/", {'status': 'sent'})
        self.put(f"/api/orders/{self.order['id']}/", {'ship_to': 'Almacén SIDOR\nMatanzas, Puerto Ordaz'})
        acts = [a['description'] for a in self.get(f'/api/deals/{self.D}/timeline/')]
        self.assertTrue(any('already sent: let the supplier know' in a for a in acts))

    def test_sales_only_see_addresses_from_their_deals(self):
        self.put(f"/api/orders/{self.order['id']}/", {'ship_to': 'Somewhere private'})
        sales = self.as_user(self.user('s@test.com', 'sales'))
        self.assertEqual(sales.get('/api/orders/ship-to/').json(), [])
