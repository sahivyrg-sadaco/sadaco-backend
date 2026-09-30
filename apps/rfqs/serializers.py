from django.utils import timezone
from rest_framework import serializers

from apps.deals.models import DealItem
from .models import SupplierRFQ


class SupplierRFQSerializer(serializers.ModelSerializer):
    supplier_name    = serializers.SerializerMethodField()
    supplier_email   = serializers.SerializerMethodField()
    supplier_contact = serializers.SerializerMethodField()
    status_label     = serializers.CharField(source='get_status_display', read_only=True)
    deal_items       = serializers.PrimaryKeyRelatedField(many=True, queryset=DealItem.objects.all())
    days_waiting     = serializers.SerializerMethodField()
    reply_days       = serializers.SerializerMethodField()
    flags            = serializers.SerializerMethodField()

    class Meta:
        model  = SupplierRFQ
        fields = [
            'id', 'deal', 'supplier', 'supplier_name', 'supplier_email', 'supplier_contact',
            'deal_items', 'status', 'status_label', 'language', 'sent_to', 'subject', 'body',
            'sent_date', 'reply_by', 'replied_date', 'supplier_quote',
            'followup_count', 'last_followup_date', 'notes',
            'days_waiting', 'reply_days', 'flags', 'created_at',
        ]
        read_only_fields = ['id', 'deal', 'replied_date', 'supplier_quote', 'followup_count',
                            'last_followup_date', 'created_at']

    def get_supplier_name(self, r):
        return r.supplier.company_name if r.supplier else None

    def get_supplier_email(self, r):
        return r.supplier.email if r.supplier else None

    def get_supplier_contact(self, r):
        return r.supplier.contact_name if r.supplier else None

    def get_days_waiting(self, r):
        return (timezone.localdate() - r.sent_date).days if r.status == 'awaiting' else None

    def get_reply_days(self, r):
        return (r.replied_date - r.sent_date).days if r.replied_date else None

    def get_flags(self, r):
        from .services import rfq_flags
        return [{'level': l, 'text': t} for l, t in rfq_flags(r, timezone.localdate())]

    def validate(self, attrs):
        deal = self.context.get('deal') or (self.instance.deal if self.instance else None)
        for it in attrs.get('deal_items', []):
            if deal and it.deal_id != deal.id:
                raise serializers.ValidationError({'deal_items': 'An item belongs to another deal.'})
        sent = attrs.get('sent_date', getattr(self.instance, 'sent_date', None))
        by = attrs.get('reply_by', getattr(self.instance, 'reply_by', None))
        if sent and by and by < sent:
            raise serializers.ValidationError({'reply_by': 'The reply-by date is before the date sent.'})
        return attrs
