"""Mounted at /api/."""
from django.urls import path

from . import views

urlpatterns = [
    path('deals/<int:pk>/client-quotes/',     views.deal_quotes),
    path('deals/<int:pk>/client-pos/',        views.record_po),
    path('client-quotes/<int:qid>/',          views.quote_detail),
    path('client-quotes/<int:qid>/sent/',     views.quote_sent),
    path('client-quotes/<int:qid>/followup/', views.quote_followup),
    path('client-pos/<int:pid>/',             views.edit_po),
    path('client-pos/<int:pid>/process/',     views.process_po),
    path('client-pos/<int:pid>/reject/',      views.reject_po),
]
