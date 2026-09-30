"""Mounted at /api/."""
from django.urls import path

from . import views

urlpatterns = [
    path('deals/<int:pk>/money/',             views.deal_money),
    path('deals/<int:pk>/client-invoices/',   views.create_client_invoice),
    path('deals/<int:pk>/payables/',          views.create_payable),
    path('client-invoices/<int:iid>/',          views.client_invoice_detail),
    path('client-invoices/<int:iid>/payments/', views.client_payment),
    path('client-payments/<int:pid>/',          views.client_payment_delete),
    path('payables/<int:pid>/',               views.payable_detail),
    path('payables/<int:pid>/payments/',      views.payable_payment),
    path('payable-payments/<int:xid>/',       views.payable_payment_delete),
    path('finance/receivables/',              views.receivables),
    path('finance/payables/',                 views.payables),
]
