"""Who can see and change what: owner checks for sales, role rules, login limits."""
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from .base import SadacoTestCase


class AccessTests(SadacoTestCase):
    def jwt(self, user):
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION='Bearer ' + str(RefreshToken.for_user(user).access_token))
        return c

    def setUp(self):
        super().setUp()
        self.D = self.deal()['id']
        it = self.item(self.D, 'Bearing', 10, cost=10, price=20)
        g = self.supplier('Grainger')
        q = self.quote(self.D, g)
        self.award(self.D, it, q, 10, 10)
        self.win(self.D)
        self.order = self.post(f'/api/deals/{self.D}/orders/from-awards/', {})[0]
        self.cost = self.post(f'/api/deals/{self.D}/costs/', {'category': 'forwarder', 'estimate_amount': 50})['costs'][0]

    def test_sales_only_see_their_own_deals(self):
        sales = self.user('sales@test.com', 'sales')
        s = self.jwt(sales)
        own = s.post('/api/deals/', {'client': self.cl.id, 'seller_entity': 'X', 'currency': 'USD'}, format='json').json()
        self.assertEqual(s.get(f"/api/deals/{own['id']}/costs/").status_code, 200)
        urls = [f'/api/deals/{self.D}/', f'/api/deals/{self.D}/costs/', f'/api/deals/{self.D}/money/',
                f'/api/deals/{self.D}/client-quotes/', f'/api/deals/{self.D}/orders/', f"/api/orders/{self.order['id']}/",
                f"/api/orders/{self.order['id']}/payment-plan/", f"/api/costs/{self.cost['id']}/"]
        self.assertEqual({s.get(u).status_code for u in urls}, {404})
        self.assertEqual(s.put(f"/api/costs/{self.cost['id']}/", {'notes': 'x'}, format='json').status_code, 404)
        self.assertEqual(s.get('/api/search/', {'q': '7-0001'}).json()['results'], [])
        self.assertEqual(self.jwt(self.admin).get(f'/api/deals/{self.D}/costs/').status_code, 200)

    def test_role_rules(self):
        fin = self.as_user(self.user('fin@test.com', 'finance'))
        ops = self.as_user(self.user('ops@test.com', 'operations'))
        c = self.cost['id']
        self.assertEqual(fin.post(f'/api/deals/{self.D}/costs/', {'category': 'other', 'estimate_amount': 5}, format='json').status_code, 403)
        self.assertEqual(fin.put(f'/api/costs/{c}/', {'actual_amount': 55, 'invoice_ref': 'B1'}, format='json').status_code, 200)
        self.assertEqual(fin.put(f'/api/costs/{c}/', {'estimate_amount': 1}, format='json').status_code, 403)
        self.assertEqual(fin.delete(f'/api/costs/{c}/').status_code, 403)
        self.assertEqual(ops.put(f'/api/deals/{self.D}/cost-settings/', {'target_margin_pct': 30}, format='json').status_code, 403)
        self.assertEqual(fin.post(f'/api/deals/{self.D}/rfqs/', {'supplier': 1, 'deal_items': []}, format='json').status_code, 403)

    def test_login_limits(self):
        self.user('locked@test.com', 'sales')
        anon = APIClient()
        tries = [anon.post('/api/auth/token/', {'email': 'locked@test.com', 'password': 'wrong'}, format='json').status_code
                 for _ in range(6)]
        self.assertEqual(tries, [401] * 5 + [429])
        right = anon.post('/api/auth/token/', {'email': 'locked@test.com', 'password': 'password-123'}, format='json')
        self.assertEqual(right.status_code, 429)
        other = anon.post('/api/auth/token/', {'email': 'admin@test.com', 'password': 'password-123'}, format='json')
        self.assertEqual(other.status_code, 200)

    def test_health_reports_version(self):
        from django.conf import settings
        self.assertEqual(APIClient().get('/api/health/').json()['version'], settings.APP_VERSION)
