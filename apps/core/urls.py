from django.urls import path
from . import views

urlpatterns = [
    path('seller-entities/',  views.seller_entities),
    path('payment-terms/',    views.payment_terms),
    path('incoterms/',        views.incoterms),
    path('locations/',        views.locations),
    path('currencies/',       views.currencies),
    path('units/',            views.units),
    path('pipeline-stages/',  views.pipeline_stages),
    path('options/<str:kind>/', views.add_option),
]
