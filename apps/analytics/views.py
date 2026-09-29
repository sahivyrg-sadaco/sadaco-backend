"""Analytics endpoints — all accept ?period=...&from=...&to=...."""
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from . import services


def _params(request):
    """Extract common period params; restrict sales users to own deals."""
    return {
        'period':    request.query_params.get('period',    'year'),
        'date_from': request.query_params.get('from'),
        'date_to':   request.query_params.get('to'),
        'owner_id':  (request.user.id
                       if getattr(request.user, 'role', None) == 'sales'
                       else None),
    }


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def kpis(request):
    return Response(services.kpi_summary(**_params(request)))


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def revenue_by_client(request):
    return Response(services.revenue_by_client(**_params(request)))


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def monthly(request):
    return Response(services.monthly_invoicing(**_params(request)))


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def pipeline(request):
    # pipeline_by_stage only takes owner_id
    p = _params(request)
    return Response(services.pipeline_by_stage(owner_id=p['owner_id']))


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def margin_by_client(request):
    return Response(services.margin_by_client(**_params(request)))
