"""User CRUD endpoints — mounted at /api/users/."""
from django.urls import path
from . import views

urlpatterns = [
    path('',        views.UserListCreateView.as_view()),
    path('<uuid:pk>/', views.UserDetailView.as_view()),
]
