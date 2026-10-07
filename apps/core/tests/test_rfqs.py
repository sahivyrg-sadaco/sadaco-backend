"""RFQs: reminders, replies linked to quotes, and quoting only the items asked about."""
import datetime as dt

from django.utils import timezone

from apps.deals.models import Deal
from apps.rfqs.models import SupplierRFQ
from .base import SadacoTestCase, days


class RfqTests(SadacoTestCase):
    def setUp(self):
        super().setUp()
        self.D = self.deal()['id']
        self.its = [self.item(self.D, n, 10, n=k + 1) for k, n in enumerate(['Bearing', 'Seal', 'Gasket'])]
        self.g, self.m = self.supplier('Grainger'), self.supplier('Motion')

    def test_idle_quoting_deal_and_overdue_rfq_reminders(self):
        Deal.objects.filter(pk=self.D).update(created_at=timezone.now() - dt.timedelta(days=2))
        titles = [e['title'] for e in self.get('/api/tracking/attention/')['entries']]
        self.assertIn('Send RFQs to suppliers', titles)
        self.post(f'/api/deals/{self.D}/rfqs/', {'supplier': self.m.id, 'deal_items': [self.its[0]['id']],
                                                 'sent_date': days(-8).isoformat(), 'reply_by': days(-3).isoformat()})
        flags = [e['flags'][0]['text'] for e in self.get('/api/tracking/attention/')['entries'] if e['kind'] == 'rfq']
        self.assertEqual(flags, ['No reply, 3 days past the reply-by date (no reminder sent)'])
        r = SupplierRFQ.objects.get()
        self.post(f'/api/rfqs/{r.id}/followup/', {}, code=200)
        self.assertEqual([e for e in self.get('/api/tracking/attention/')['entries'] if e['kind'] == 'rfq'], [])

    def test_quote_marks_rfq_replied(self):
        self.post(f'/api/deals/{self.D}/rfqs/', {'supplier': self.g.id, 'deal_items': [self.its[0]['id']]})
        self.quote(self.D, self.g)
        r = self.get(f'/api/deals/{self.D}/rfqs/')[0]
        self.assertEqual((r['status'], r['reply_days']), ('replied', 0))

    def test_quote_only_items_in_the_rfq_and_offered_items(self):
        self.post(f'/api/deals/{self.D}/rfqs/', {'supplier': self.g.id, 'deal_items': [self.its[0]['id'], self.its[1]['id']]})
        qg, qm = self.quote(self.D, self.g), self.quote(self.D, self.m)
        self.ok(self.api.post(f"/api/deals/{self.D}/quotes/{qg['id']}/items/", {'deal_item_id': self.its[2]['id'], 'unit_price': 5}, format='json'), 400)
        self.price(self.D, qg, self.its[0], 9)
        self.price(self.D, qm, self.its[2], 4)                 # no RFQ to Motion: anything goes
        new = self.post(f'/api/deals/{self.D}/quote-items/add/', {'description': 'Sleeve H305', 'qty': 10, 'quote': qg['id'], 'unit_price': 6.5})
        self.price(self.D, qg, {'id': new['id']}, 6.2)          # offered by Grainger, so priceable
        rfq = SupplierRFQ.objects.get(supplier=self.g)
        self.assertIn(new['id'], set(rfq.deal_items.values_list('id', flat=True)))
