from django.urls import path
from . import views

urlpatterns = [
    path('kpis/',               views.kpis),
    path('revenue-by-client/',  views.revenue_by_client),
    path('monthly/',            views.monthly),
    path('pipeline/',           views.pipeline),
    path('margin-by-client/',   views.margin_by_client),
]
