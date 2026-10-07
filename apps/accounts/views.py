"""Authentication and user-management views."""
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from apps.core.permissions import IsAdmin
from .models import User
from .serializers import (
    UserSerializer,
    UserCreateSerializer,
    EmailTokenObtainPairSerializer,
)


class EmailTokenObtainPairView(TokenObtainPairView):
    """
    POST /api/auth/token/ — log in with email + password.

    Guessing is limited: after 5 wrong passwords for an account it's locked for
    15 minutes, and any one network address gets 30 failed tries per 15 minutes.
    A successful sign-in clears the account's count.
    """
    serializer_class = EmailTokenObtainPairSerializer
    MAX_PER_ACCOUNT = 5
    MAX_PER_ADDRESS = 30
    WINDOW = 15 * 60

    def post(self, request, *args, **kwargs):
        from django.core.cache import cache
        email = str(request.data.get('email') or '').strip().lower()
        forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
        ip = forwarded.split(',')[0].strip() if forwarded else request.META.get('REMOTE_ADDR', '')
        k_acct, k_ip = f'login-fail:acct:{email}', f'login-fail:ip:{ip}'
        if cache.get(k_acct, 0) >= self.MAX_PER_ACCOUNT or cache.get(k_ip, 0) >= self.MAX_PER_ADDRESS:
            return Response({'detail': 'Too many failed sign-ins. Try again in 15 minutes.'}, status=429)

        def failed():
            for k in (k_acct, k_ip):
                cache.set(k, cache.get(k, 0) + 1, self.WINDOW)
        try:
            response = super().post(request, *args, **kwargs)
        except Exception:
            failed()
            raise
        if response.status_code == 200:
            cache.delete(k_acct)
        else:
            failed()
        return response


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def me(request):
    """GET /api/auth/me/ — return the currently authenticated user."""
    return Response(UserSerializer(request.user).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def set_lang(request):
    """POST /api/auth/set-lang/ — switch the user's UI language."""
    lang = request.data.get('lang')
    if lang not in ('es', 'en'):
        return Response({'error': "lang must be 'es' or 'en'"},
                        status=status.HTTP_400_BAD_REQUEST)
    request.user.lang = lang
    request.user.save(update_fields=['lang'])
    return Response({'lang': lang})


class UserListCreateView(APIView):
    """GET/POST /api/users/ — list all users or create a new one (admin only)."""
    permission_classes = [IsAdmin]

    def get(self, request):
        users = User.objects.all()
        return Response(UserSerializer(users, many=True).data)

    def post(self, request):
        ser = UserCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        user = ser.save()
        return Response(UserSerializer(user).data,
                        status=status.HTTP_201_CREATED)


class UserDetailView(APIView):
    """GET/PUT /api/users/{id}/ — retrieve or update a single user (admin only)."""
    permission_classes = [IsAdmin]

    def get_object(self, pk):
        return User.objects.filter(pk=pk).first()

    def get(self, request, pk):
        user = self.get_object(pk)
        if not user:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
        return Response(UserSerializer(user).data)

    def put(self, request, pk):
        user = self.get_object(pk)
        if not user:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
        ser = UserSerializer(user, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        # Support password change via this endpoint
        pw = request.data.get('password')
        if pw:
            user.set_password(pw)
            user.save(update_fields=['password'])
        return Response(UserSerializer(user).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def change_password(request):
    """POST /api/auth/change-password/ — { current_password, new_password }"""
    current = request.data.get('current_password') or ''
    new     = request.data.get('new_password') or ''
    if not request.user.check_password(current):
        return Response({'error': 'Your current password is not correct.'},
                        status=status.HTTP_400_BAD_REQUEST)
    if len(new) < 8:
        return Response({'error': 'The new password needs at least 8 characters.'},
                        status=status.HTTP_400_BAD_REQUEST)
    if new == current:
        return Response({'error': 'The new password must be different from the current one.'},
                        status=status.HTTP_400_BAD_REQUEST)
    request.user.set_password(new)
    request.user.save(update_fields=['password'])
    return Response({'ok': True})
