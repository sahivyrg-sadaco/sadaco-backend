from django.urls import path
from . import views

urlpatterns = [
    path('',                                 views.PaymentCreateView.as_view()),
    path('ar/',                              views.ARView.as_view()),
    path('ar/summary/',                      views.ar_summary),
    path('ar/overdue/',                      views.ar_overdue),
    path('balance/<str:invoice_ref>/',       views.invoice_balance),
    path('history/<str:invoice_ref>/',       views.invoice_history),
]
