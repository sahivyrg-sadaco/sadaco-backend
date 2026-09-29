"""Config endpoints — expose business constants to the frontend."""
from django.conf import settings
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def seller_entities(request):
    return Response(settings.SELLER_ENTITIES)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def payment_terms(request):
    return Response(settings.PAYMENT_TERMS)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def incoterms(request):
    return Response(settings.INCOTERMS)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def locations(request):
    return Response(settings.LOCATIONS)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def currencies(request):
    return Response(settings.CURRENCIES)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def units(request):
    return Response(settings.UNITS)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def pipeline_stages(request):
    return Response(settings.PIPELINE_STAGES)
