"""Mounted at /api/."""
from django.urls import path

from . import views

urlpatterns = [
    path('deals/<int:pk>/rfqs/',       views.deal_rfqs),
    path('rfqs/<int:rid>/',            views.rfq_detail),
    path('rfqs/<int:rid>/followup/',   views.rfq_followup),
]
