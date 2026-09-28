"""
Documents URLs — only the standalone attachment delete endpoint.
Client- and deal-scoped attachment URLs live in their respective apps
(and import views from here).
"""
from django.urls import path

from . import views

urlpatterns = [
    path('attachments/<int:pk>/', views.AttachmentDeleteView.as_view()),
]
