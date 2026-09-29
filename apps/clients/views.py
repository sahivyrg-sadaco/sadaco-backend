"""Client CRUD + attachment endpoints."""
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsSalesOrAdmin
from .models import Client
from .serializers import ClientSerializer


class ClientListCreateView(APIView):
    """
    GET  /api/clients/  → list all clients (auth required)
    POST /api/clients/  → create a client (sales or admin)
    """
    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsSalesOrAdmin()]
        return [IsAuthenticated()]

    def get(self, request):
        clients = Client.objects.all()
        return Response(ClientSerializer(clients, many=True).data)

    def post(self, request):
        ser = ClientSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data, status=status.HTTP_201_CREATED)


class ClientDetailView(APIView):
    """
    GET    /api/clients/{id}/
    PUT    /api/clients/{id}/
    DELETE /api/clients/{id}/
    """
    def get_permissions(self):
        if self.request.method in ('PUT', 'DELETE'):
            return [IsSalesOrAdmin()]
        return [IsAuthenticated()]

    def get_object(self, pk):
        return Client.objects.filter(pk=pk).first()

    def get(self, request, pk):
        client = self.get_object(pk)
        if not client:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
        return Response(ClientSerializer(client).data)

    def put(self, request, pk):
        client = self.get_object(pk)
        if not client:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
        ser = ClientSerializer(client, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data)

    def delete(self, request, pk):
        client = self.get_object(pk)
        if not client:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
        client.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
