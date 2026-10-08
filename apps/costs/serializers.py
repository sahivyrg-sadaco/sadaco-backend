from rest_framework import serializers

from .models import DealCost


class DealCostSerializer(serializers.ModelSerializer):
    category_label = serializers.CharField(source='get_category_display', read_only=True)
    shipment_label = serializers.SerializerMethodField()

    class Meta:
        model  = DealCost
        fields = [
            'id', 'deal', 'category', 'category_label', 'description', 'payee',
            'amount_type', 'percent', 'percent_base', 'estimate_amount', 'actual_amount',
            'currency', 'fx_rate', 'client_treatment', 'charge_amount',
            'invoice_ref', 'invoice_date', 'overrun_acknowledged', 'notes',
            'shipment', 'shipment_label', 'supplier_order',
            'basis', 'breakdown', 'weight_rate', 'weight_minimum', 'charge_mode',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'deal', 'shipment', 'supplier_order', 'basis', 'breakdown', 'charge_mode',
                            'weight_rate', 'weight_minimum', 'created_at', 'updated_at']
        extra_kwargs = {
            'percent': {'coerce_to_string': False}, 'estimate_amount': {'coerce_to_string': False},
            'actual_amount': {'coerce_to_string': False}, 'fx_rate': {'coerce_to_string': False},
            'charge_amount': {'coerce_to_string': False},
        }

    def get_shipment_label(self, c):
        s = c.shipment
        if not s:
            return None
        who = s.carrier or s.forwarder
        return f'{s.get_leg_display()}' + (f', {who}' if who else '')

    def validate(self, attrs):
        get = lambda k: attrs.get(k, getattr(self.instance, k, None))  # noqa: E731
        deal = self.context.get('deal') or (self.instance.deal if self.instance else None)

        if get('amount_type') == 'percent':
            if not get('percent_base'):
                raise serializers.ValidationError({'percent_base': 'Choose what the percentage applies to.'})
            p = get('percent')
            if p is not None and not (0 <= p <= 100):
                raise serializers.ValidationError({'percent': 'Use a percentage between 0 and 100.'})
        for k in ('estimate_amount', 'actual_amount', 'charge_amount'):
            v = attrs.get(k)
            if v is not None and v < 0:
                raise serializers.ValidationError({k: 'Amounts cannot be negative.'})

        currency = get('currency') or 'USD'
        fx = get('fx_rate')
        if deal and currency not in ('USD', deal.currency) and (fx is None or fx <= 0):
            raise serializers.ValidationError({'fx_rate': f'Enter the rate: 1 USD = how many {currency}.'})
        # A cost row tied to a shipment takes its actual amount from the shipment.
        if self.instance and self.instance.shipment_id and 'actual_amount' in attrs \
                and attrs['actual_amount'] != self.instance.actual_amount:
            raise serializers.ValidationError(
                {'actual_amount': 'This amount comes from the shipment. Change the freight cost on the shipment.'})
        return attrs
