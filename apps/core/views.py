"""Config endpoints — expose business constants to the frontend."""
from django.conf import settings
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import ConfigOption


def _with_added(kind, defaults):
    """Defaults first, in their set order, then options people added, A to Z."""
    added = ConfigOption.objects.filter(kind=kind).values_list('value', flat=True)
    seen = {d.casefold() for d in defaults}
    return list(defaults) + sorted((v for v in added if v.casefold() not in seen), key=str.casefold)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def seller_entities(request):
    return Response(settings.SELLER_ENTITIES)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def payment_terms(request):
    return Response(_with_added('payment_terms', settings.PAYMENT_TERMS))


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def incoterms(request):
    return Response(settings.INCOTERMS)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def locations(request):
    return Response(_with_added('locations', settings.LOCATIONS))


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def currencies(request):
    return Response(settings.CURRENCIES)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def units(request):
    return Response(_with_added('units', settings.UNITS))


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def pipeline_stages(request):
    return Response(settings.PIPELINE_STAGES)


DEFAULTS = {'units': 'UNITS', 'payment_terms': 'PAYMENT_TERMS', 'locations': 'LOCATIONS'}


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def add_option(request, kind):
    """
    POST /api/config/options/{kind}/  { value }  → { value, list }
    Adds a unit, payment term or delivery point for everyone. If it already
    exists (ignoring case), returns the existing spelling instead of a copy.
    """
    if kind not in DEFAULTS:
        return Response({'error': 'This list cannot be extended.'}, status=400)
    value = ' '.join(str(request.data.get('value') or '').split())
    if not value:
        return Response({'error': 'Enter a value.'}, status=400)
    limit = ConfigOption.MAX_LENGTH[kind]
    if len(value) > limit:
        return Response({'error': f'Keep it under {limit} characters.'}, status=400)

    current = _with_added(kind, getattr(settings, DEFAULTS[kind]))
    match = next((v for v in current if v.casefold() == value.casefold()), None)
    if not match:
        ConfigOption.objects.create(kind=kind, value=value, created_by=request.user)
        match = value
        current = _with_added(kind, getattr(settings, DEFAULTS[kind]))
    return Response({'value': match, 'list': current}, status=201)
