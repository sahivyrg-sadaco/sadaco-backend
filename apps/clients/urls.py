from django.urls import path

from . import views
from apps.documents.views import (
    ClientAttachmentListCreateView,
)


urlpatterns = [
    path('',              views.ClientListCreateView.as_view()),
    path('<int:pk>/',     views.ClientDetailView.as_view()),

    # Client-scoped attachments (handled by documents app)
    path('<int:pk>/attachments/',
         ClientAttachmentListCreateView.as_view()),
]
