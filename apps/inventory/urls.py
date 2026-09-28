from django.urls import path
from . import views

urlpatterns = [
    path('',                         views.StockListCreateView.as_view()),
    path('summary/',                 views.inventory_summary),
    path('low-stock/',               views.low_stock),
    path('<int:pk>/',                views.StockDetailView.as_view()),
    path('<int:pk>/adjust/',         views.adjust_stock),
    path('<int:pk>/history/',        views.stock_history),
    path('deduct/<int:dn_id>/',      views.deduct_on_delivery),
]
