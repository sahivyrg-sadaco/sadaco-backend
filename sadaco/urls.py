"""Root URL configuration for SADACO ERP/CRM."""
from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse
from django.db import connection


def health(request):
    """Health check — returns DB connectivity status."""
    try:
        with connection.cursor() as c:
            c.execute('SELECT 1')
            c.fetchone()
        return JsonResponse({'status': 'ok', 'db': 'connected'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'db': str(e)}, status=503)


urlpatterns = [
    path('admin/',                     admin.site.urls),
    path('api/health/',                health),
    path('api/auth/',                  include('apps.accounts.urls')),
    path('api/config/',                include('apps.core.urls')),
    path('api/clients/',               include('apps.clients.urls')),
    path('api/suppliers/',             include('apps.suppliers.urls')),
    path('api/deals/',                 include('apps.deals.urls')),
    path('api/',                       include('apps.documents.urls')),
    path('api/payments/',              include('apps.payments.urls')),
    path('api/inventory/',             include('apps.inventory.urls')),
    path('api/notifications/',         include('apps.notifications.urls')),
    path('api/analytics/',             include('apps.analytics.urls')),
    path('api/users/',                 include('apps.accounts.user_urls')),
]
