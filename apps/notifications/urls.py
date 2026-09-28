from django.urls import path
from . import views

urlpatterns = [
    path('',                 views.NotificationListView.as_view()),
    path('read-all/',        views.mark_all_read),
    path('<int:pk>/read/',   views.mark_read),
]
