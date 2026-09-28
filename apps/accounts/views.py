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
    """POST /api/auth/token/ — log in with email + password."""
    serializer_class = EmailTokenObtainPairSerializer


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
