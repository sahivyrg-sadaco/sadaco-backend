from rest_framework import serializers
from .models import Payment


class PaymentSerializer(serializers.ModelSerializer):
    recorded_by_name = serializers.CharField(
        source='recorded_by.name', read_only=True, default=None,
    )

    class Meta:
        model  = Payment
        fields = [
            'id', 'invoice_ref', 'deal', 'amount', 'currency',
            'payment_date', 'method', 'notes',
            'recorded_by', 'recorded_by_name', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']
        extra_kwargs = {'amount': {'coerce_to_string': False}}
