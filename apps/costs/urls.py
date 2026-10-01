"""Mounted at /api/."""
from django.urls import path

from . import views

urlpatterns = [
    path('deals/<int:pk>/costs/',         views.deal_costs),
    path('deals/<int:pk>/costs/typical/', views.add_typical),
    path('deals/<int:pk>/cost-settings/', views.cost_settings),
    path('costs/<int:cid>/',              views.cost_detail),
    path('deals/<int:pk>/freight-estimate/', views.freight_estimate),
]
