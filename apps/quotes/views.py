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


class DealQuoteAddItemView(APIView):
    """
    POST /api/deals/{id}/quote-items/add/
    { description, part_number?, brand?, model_name?, qty, unit?,
      quote?: supplier quote id, unit_price?, lead_time_days?, unit_weight_kg? }

    Adds a line item to the deal from the Supplier quotes tab. When `quote` is
    given, the item counts as offered by that supplier (e.g. an accessory they
    recommend): it's placed on their quote, with their price if given, so it
    can be priced even if their RFQ didn't include it.
    """
    permission_classes = [IsSalesOrOperationsOrAdmin]

    def post(self, request, pk):
        from decimal import Decimal, InvalidOperation
        from django.db import transaction
        from django.db.models import Max
        from apps.costs.services import target_margin
        from apps.deals.models import DealActivity, DealItem
        deal = get_object_or_404(Deal, pk=pk)
        d = request.data
        description = str(d.get('description') or '').strip()
        if not description:
            return Response({'description': ['Describe the item.']}, status=400)
        try:
            qty = Decimal(str(d.get('qty')))
            if qty <= 0:
                raise InvalidOperation
        except (InvalidOperation, ValueError, TypeError):
            return Response({'qty': ['Enter a quantity above zero.']}, status=400)
        quote = None
        if d.get('quote'):
            quote = SupplierQuote.objects.filter(pk=d['quote'], deal=deal).select_related('supplier').first()
            if not quote:
                return Response({'quote': ['That supplier quote is not on this deal.']}, status=400)
        with transaction.atomic():
            n = (DealItem.objects.filter(deal=deal, is_split_child=False).aggregate(m=Max('item_number'))['m'] or 0) + 1
            item = DealItem.objects.create(
                deal=deal, item_number=n, description=description,
                part_number=str(d.get('part_number') or '').strip(), brand=str(d.get('brand') or '').strip(),
                model_name=str(d.get('model_name') or '').strip(), qty=qty, unit=str(d.get('unit') or 'Unit (Unid)'),
                margin_pct=Decimal(str(target_margin(deal)[0] / 100)).quantize(Decimal('0.0001')),
            )
            if quote:
                extra = {k: d[k] for k in ('lead_time_days', 'unit_weight_kg') if d.get(k) not in (None, '')}
                try:
                    upsert_quote_item(quote_id=quote.id, deal_item_id=item.id, unit_price=d.get('unit_price') or 0, **extra)
                except (ValueError, ArithmeticError):
                    transaction.set_rollback(True)
                    return Response({'error': 'Check the price, lead time and weight.'}, status=400)
        who = quote.supplier.company_name if quote and quote.supplier else None
        DealActivity.objects.create(
            deal=deal, user=request.user, activity_type='item',
            description=f'Line {n} added from the Supplier quotes tab: {description[:60]}'
                        + (f' (offered by {who})' if who else '') + '.')
        return Response({'id': item.id, 'item_number': n}, status=status.HTTP_201_CREATED)
