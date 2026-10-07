from decimal import Decimal
from rest_framework import serializers

from .models import Deal, DealItem, DealItemSplit, DealActivity


class DealItemSerializer(serializers.ModelSerializer):
    total_cost            = serializers.SerializerMethodField()
    total_price           = serializers.SerializerMethodField()
    awarded_supplier_name = serializers.SerializerMethodField()

    class Meta:
        model  = DealItem
        fields = [
            'id', 'deal', 'item_number', 'description', 'part_number',
            'brand', 'model_name', 'qty', 'unit',
            'unit_cost', 'margin_pct', 'unit_price',
            'parent_item', 'awarded_quote', 'is_split_child',
            'total_cost', 'total_price', 'awarded_supplier_name',
        ]
        read_only_fields = ['id', 'deal']
        extra_kwargs = {
            'qty':        {'coerce_to_string': False},
            'unit_cost':  {'coerce_to_string': False},
            'unit_price': {'coerce_to_string': False},
            'margin_pct': {'coerce_to_string': False},
        }

    def get_total_cost(self, obj):
        return float(obj.qty or 0) * float(obj.unit_cost or 0)

    def get_total_price(self, obj):
        return float(obj.qty or 0) * float(obj.unit_price or 0)

    def get_awarded_supplier_name(self, obj):
        if obj.awarded_quote and obj.awarded_quote.supplier:
            return obj.awarded_quote.supplier.company_name
        return None


class DealActivitySerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.name', read_only=True, default=None)

    class Meta:
        model  = DealActivity
        fields = ['id', 'deal', 'user', 'user_name',
                  'activity_type', 'description', 'created_at']
        read_only_fields = ['id', 'created_at']


class DealItemSplitSerializer(serializers.ModelSerializer):
    supplier_name    = serializers.SerializerMethodField()
    item_description = serializers.CharField(
        source='parent_item.description', read_only=True,
    )

    class Meta:
        model  = DealItemSplit
        fields = [
            'id', 'parent_item', 'supplier_quote', 'qty_awarded',
            'unit_cost', 'child_item', 'created_at',
            'supplier_name', 'item_description',
        ]
        read_only_fields = ['id', 'created_at', 'child_item']
        extra_kwargs = {
            'qty_awarded': {'coerce_to_string': False},
            'unit_cost':   {'coerce_to_string': False},
        }

    def get_supplier_name(self, obj):
        if obj.supplier_quote and obj.supplier_quote.supplier:
            return obj.supplier_quote.supplier.company_name
        return None


class DealListSerializer(serializers.ModelSerializer):
    """Lightweight serializer used for list views."""
    client_name = serializers.CharField(source='client.full_name', read_only=True)
    client_key  = serializers.CharField(source='client.dropdown_name', read_only=True)
    owner_name  = serializers.CharField(source='owner.name',       read_only=True, default=None)
    # Filled by services.annotate_list_summary(); absent → null.
    total_price     = serializers.SerializerMethodField()
    total_cost      = serializers.SerializerMethodField()
    item_count      = serializers.SerializerMethodField()
    orders_total    = serializers.SerializerMethodField()
    orders_received = serializers.SerializerMethodField()
    next_eta        = serializers.SerializerMethodField()
    economics       = serializers.SerializerMethodField()

    class Meta:
        model  = Deal
        fields = [
            'id', 'reference', 'client', 'client_name', 'client_key', 'client_ref',
            'owner', 'owner_name', 'seller_entity', 'status', 'deal_status',
            'currency', 'exchange_rate', 'created_at',
            'total_price', 'total_cost', 'item_count',
            'orders_total', 'orders_received', 'next_eta', 'economics',
        ]
        extra_kwargs = {'exchange_rate': {'coerce_to_string': False}}

    def _num(self, obj, attr):
        v = getattr(obj, attr, None)
        return round(float(v), 2) if v is not None else None

    def get_total_price(self, obj):     return self._num(obj, 'sum_price')
    def get_total_cost(self, obj):      return self._num(obj, 'sum_cost')
    def get_item_count(self, obj):      return getattr(obj, 'item_count', None)
    def get_orders_total(self, obj):    return getattr(obj, 'orders_total', None) or 0
    def get_orders_received(self, obj): return getattr(obj, 'orders_received', None) or 0

    def get_economics(self, obj):
        """Net margin estimated and actual so far, including extra costs."""
        if not hasattr(obj, 'sum_price'):
            return None
        from apps.costs.services import compute
        try:
            settings_obj = obj.cost_settings
        except Exception:  # no settings row → incoterm default
            settings_obj = False
        if any(p.status == 'processed' for p in obj.client_pos.all()):
            # Partly won deals: work from the lines the client ordered.
            e = compute(obj, costs=list(obj.extra_costs.all()), settings_obj=settings_obj)
        else:
            e = compute(obj, costs=list(obj.extra_costs.all()),
                        goods=float(obj.sum_cost or 0), sell=float(obj.sum_price or 0), settings_obj=settings_obj)
        return {
            'net_margin_est': e['estimate']['net_margin_pct'],
            'net_margin_act': e['actual_so_far']['net_margin_pct'],
            'gross_margin': e['gross_margin_pct'],
            'costs_total': e['costs_total'],
            'costs_invoiced': e['costs_invoiced'],
            'revenue': e['estimate']['revenue'],
        }

    def get_next_eta(self, obj):
        v = getattr(obj, 'next_eta', None)
        return v.isoformat() if hasattr(v, 'isoformat') else v


class DealDetailSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source='client.full_name',     read_only=True)
    client_key  = serializers.CharField(source='client.dropdown_name', read_only=True)
    owner_name  = serializers.CharField(source='owner.name',           read_only=True, default=None)

    class Meta:
        model  = Deal
        fields = [
            'id', 'reference', 'client', 'client_name', 'client_key',
            'owner', 'owner_name', 'seller_entity',
            'status', 'deal_status', 'lost_reason',
            'currency', 'exchange_rate',
            'incoterm', 'port_location', 'payment_terms',
            'delivery_time', 'client_ref', 'notes',
            'drive_folder_id',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'reference', 'drive_folder_id',
                            'created_at', 'updated_at']
        extra_kwargs = {'exchange_rate': {'coerce_to_string': False}}
