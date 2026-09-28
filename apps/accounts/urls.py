"""Auth endpoints — mounted at /api/auth/."""
from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from . import views

urlpatterns = [
    path('token/',         views.EmailTokenObtainPairView.as_view()),
    path('token/refresh/', TokenRefreshView.as_view()),
    path('me/',            views.me),
    path('set-lang/',      views.set_lang),
]
