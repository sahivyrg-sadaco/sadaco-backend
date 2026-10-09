"""Mounted at /api/."""
from django.urls import path

from . import views

urlpatterns = [
    path('deals/<int:pk>/orders/',             views.DealOrdersView.as_view()),
    path('deals/<int:pk>/orders/from-awards/', views.DealOrdersFromAwardsView.as_view()),
    path('deals/<int:pk>/shipments/',          views.DealShipmentsView.as_view()),
    path('orders/<int:oid>/',                  views.OrderDetailView.as_view()),
    path('shipments/<int:sid>/',               views.ShipmentDetailView.as_view()),
    path('tracking/board/',                    views.tracking_board),
    path('orders/ship-to/',                    views.ship_to_suggestions),
    path('deals/<int:pk>/reminders/',          views.deal_reminders),
    path('tracking/attention/',                views.tracking_attention),
]
