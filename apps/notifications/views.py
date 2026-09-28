"""Notifications endpoints — scoped to the current user."""
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Notification
from .serializers import NotificationSerializer


class NotificationListView(APIView):
    """GET /api/notifications/ — the current user's notifications."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = Notification.objects.filter(user=request.user)
        return Response(NotificationSerializer(qs, many=True).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mark_read(request, pk):
    """POST /api/notifications/{id}/read/"""
    n = Notification.objects.filter(pk=pk, user=request.user).first()
    if not n:
        return Response({'error': 'Not found'}, status=404)
    n.read = True
    n.save(update_fields=['read'])
    return Response(NotificationSerializer(n).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mark_all_read(request):
    """POST /api/notifications/read-all/"""
    updated = Notification.objects.filter(
        user=request.user, read=False,
    ).update(read=True)
    return Response({'marked_read': updated})
