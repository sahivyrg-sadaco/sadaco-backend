"""Mounted at /api/."""
from django.urls import path

from . import views

urlpatterns = [
    path('overrides/', views.overrides),
    path('clients/<int:cid>/credit/',         views.client_credit),
    path('clients/<int:cid>/credit/refund/',  views.client_credit_refund),
    path('clients/<int:cid>/credit/apply/',   views.client_credit_apply),
    path('client-credit/<str:group>/',        views.client_credit_undo),
    path('deals/<int:pk>/money/',             views.deal_money),
    path('deals/<int:pk>/client-invoices/',   views.create_client_invoice),
    path('deals/<int:pk>/payables/',          views.create_payable),
    path('client-invoices/<int:iid>/',          views.client_invoice_detail),
    path('client-invoices/<int:iid>/payments/', views.client_payment),
    path('client-invoices/<int:iid>/credit-note/', views.credit_note),
    path('client-payments/<int:pid>/',          views.client_payment_delete),
    path('payables/<int:pid>/',               views.payable_detail),
    path('payables/<int:pid>/payments/',      views.payable_payment),
    path('payable-payments/<int:xid>/',       views.payable_payment_delete),
    path('finance/receivables/',              views.receivables),
    path('finance/payables/',                 views.payables),
    path('<str:owner>/<int:oid>/payment-plan/', views.payment_plan),
]
