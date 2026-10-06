"""Supplier quote views — all mounted under /api/deals/{id}/quotes/."""
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsSalesOrOperationsOrAdmin
from apps.deals.models import Deal
from apps.deals.services import upsert_quote_item, apply_winning_quote

from .models import SupplierQuote, SupplierQuoteItem
from .serializers import SupplierQuoteSerializer, SupplierQuoteItemSerializer


class DealQuoteListCreateView(APIView):
    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsSalesOrOperationsOrAdmin()]
        return [IsAuthenticated()]

    def get(self, request, pk):
        get_object_or_404(Deal, pk=pk)
        qs = SupplierQuote.objects.filter(deal_id=pk).select_related('supplier')
        return Response(SupplierQuoteSerializer(qs, many=True).data)

    def post(self, request, pk):
        deal = get_object_or_404(Deal, pk=pk)
        data = dict(request.data)
        data['deal'] = deal.id
        ser  = SupplierQuoteSerializer(data=data)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data, status=status.HTTP_201_CREATED)


class DealQuoteDetailView(APIView):
    permission_classes = [IsSalesOrOperationsOrAdmin]

    def delete(self, request, pk, qid):
        quote = SupplierQuote.objects.filter(deal_id=pk, pk=qid).first()
        if not quote:
            return Response({'error': 'Not found'}, status=404)
        quote.delete()
        return Response(status=204)


class DealQuoteSelectView(APIView):
    """POST /api/deals/{id}/quotes/{qid}/select/ — mark as winner (no cost push)."""
    permission_classes = [IsSalesOrOperationsOrAdmin]

    def post(self, request, pk, qid):
        quote = SupplierQuote.objects.filter(deal_id=pk, pk=qid).first()
        if not quote:
            return Response({'error': 'Not found'}, status=404)
        SupplierQuote.objects.filter(deal_id=pk).update(selected=False)
        quote.selected = True
        quote.save(update_fields=['selected'])
        return Response(SupplierQuoteSerializer(quote).data)


class DealQuoteApplyView(APIView):
    """
    POST /api/deals/{id}/quotes/{qid}/apply/
    Mark quote as winner AND push its prices onto deal_items.unit_cost.
    """
    permission_classes = [IsSalesOrOperationsOrAdmin]

    def post(self, request, pk, qid):
        if not SupplierQuote.objects.filter(deal_id=pk, pk=qid).exists():
            return Response({'error': 'Not found'}, status=404)
        updated = apply_winning_quote(pk, qid)
        return Response({'updated_items': updated, 'selected': qid})


class DealQuoteItemListCreateView(APIView):
    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsSalesOrOperationsOrAdmin()]
        return [IsAuthenticated()]

    def get(self, request, pk, qid):
        quote = SupplierQuote.objects.filter(deal_id=pk, pk=qid).first()
        if not quote:
            return Response({'error': 'Not found'}, status=404)
        items = SupplierQuoteItem.objects.filter(quote_id=qid)
        return Response(SupplierQuoteItemSerializer(items, many=True).data)

    def post(self, request, pk, qid):
        """Upsert a quote item — body: {deal_item_id, unit_price, lead_time_days?, unit_weight_kg?}."""
        quote = SupplierQuote.objects.filter(deal_id=pk, pk=qid).select_related('supplier').first()
        if not quote:
            return Response({'error': 'Not found'}, status=404)
        # A supplier sent an RFQ on this deal quotes only the items they were asked about
        # (prices already on record before this rule stay editable).
        from apps.rfqs.models import SupplierRFQ
        from apps.quotes.models import SupplierQuoteItem
        rfqs = SupplierRFQ.objects.filter(deal_id=pk, supplier_id=quote.supplier_id) if quote.supplier_id else None
        if rfqs is not None and rfqs.exists():
            item_id = request.data.get('deal_item_id')
            asked = set(rfqs.values_list('deal_items', flat=True))
            already = SupplierQuoteItem.objects.filter(quote_id=qid, deal_item_id=item_id).exists()
            if item_id is not None and int(item_id) not in asked and not already:
                name = quote.supplier.company_name if quote.supplier else 'this supplier'
                return Response({'error': f"That item wasn't in the RFQ sent to {name}, so it can't be priced on their quote."},
                                status=400)
        try:
            extra = {k: request.data[k] for k in ('lead_time_days', 'unit_weight_kg') if k in request.data}
            row_id = upsert_quote_item(
                quote_id=qid,
                deal_item_id=request.data['deal_item_id'],
                unit_price=request.data.get('unit_price', 0),
                **extra,
            )
        except KeyError as e:
            return Response({'error': f'missing field {e}'}, status=400)
        except (ValueError, ArithmeticError):
            return Response({'error': 'Lead time must be whole days and weight a number of kg.'}, status=400)
        qi = SupplierQuoteItem.objects.filter(pk=row_id).first()
        return Response(SupplierQuoteItemSerializer(qi).data,
                        status=status.HTTP_201_CREATED)
