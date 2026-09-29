"""
DjangoDBAdapter — dict-returning shim for the Flask-era document generators.

The generator modules (doc_generator.py, delivery_note_generator.py,
pdf_generator.py) expect a `db` object that returns dict-like rows for
deals, items, suppliers, quotes, and delivery notes. This class provides
that interface on top of the Django ORM so the generators can be dropped
in verbatim.
"""
import re
from decimal import Decimal

from apps.clients.models import Client
from apps.deals.models import Deal, DealItem
from apps.documents.models import (
    Asset, InvoicedItem, DeliveryNote, DeliveryNoteItem,
)
from apps.quotes.models import SupplierQuote, SupplierQuoteItem
from apps.suppliers.models import Supplier


def _d(obj, fields=None):
    """Model instance → plain dict."""
    if obj is None:
        return None
    if fields:
        return {f: getattr(obj, f, None) for f in fields}
    data = {}
    for f in obj._meta.concrete_fields:
        v = getattr(obj, f.attname, None)
        if isinstance(v, Decimal):
            v = float(v)
        data[f.name] = v
    return data


class DjangoDBAdapter:
    """
    All read/write helpers the Flask generators expect. Methods return
    dicts (or list-of-dicts) to match psycopg2 RealDictCursor behavior.
    """

    # ── Deals ────────────────────────────────────────────────────────────────

    def get_deal_by_id(self, deal_id):
        deal = Deal.objects.select_related('client').filter(pk=deal_id).first()
        if not deal:
            return None
        d = _d(deal)
        c = deal.client
        d.update({
            'client_name':   c.full_name,
            'client_key':    c.dropdown_name,
            'client_addr1':  c.address_line1 or '',
            'client_addr2':  c.address_line2 or '',
            'client_contact': c.contact_name or '',
            'client_email':  c.contact_email or '',
        })
        return d

    def get_deal_items(self, deal_id):
        items = DealItem.objects.filter(deal_id=deal_id, is_split_child=False)
        result = []
        for i in items:
            d = _d(i)
            d['model'] = d.pop('model_name', '')
            result.append(d)
        return result

    # ── Suppliers ────────────────────────────────────────────────────────────

    def get_supplier_by_id(self, supplier_id):
        s = Supplier.objects.filter(pk=supplier_id).first()
        return _d(s) if s else None

    # ── Quotes ───────────────────────────────────────────────────────────────

    def get_supplier_quotes(self, deal_id):
        qs = SupplierQuote.objects.filter(deal_id=deal_id).select_related('supplier')
        out = []
        for q in qs:
            d = _d(q)
            d['supplier_name'] = q.supplier.company_name if q.supplier else ''
            out.append(d)
        return out

    def get_quote_items(self, quote_id):
        return [_d(qi) for qi in SupplierQuoteItem.objects.filter(quote_id=quote_id)]

    # ── Assets (logo, etc.) ──────────────────────────────────────────────────

    def get_asset(self, key: str):
        a = Asset.objects.filter(pk=key).first()
        return bytes(a.data) if a else None

    def set_asset(self, key: str, data: bytes, mime_type: str = 'image/png'):
        Asset.objects.update_or_create(
            key=key,
            defaults={'data': data, 'mime_type': mime_type},
        )

    # ── Invoicing ────────────────────────────────────────────────────────────

    @staticmethod
    def _normalize_invoice_ref(invoice_ref: str) -> str:
        if not invoice_ref:
            return invoice_ref
        return re.sub(r'\s+', '', str(invoice_ref)).upper()

    def record_invoiced_items(self, deal_id: int, invoice_ref: str):
        """Mark all current (non-split-child) deal items as invoiced."""
        ref = self._normalize_invoice_ref(invoice_ref)
        items = DealItem.objects.filter(deal_id=deal_id, is_split_child=False)
        rows = []
        for i in items:
            if not InvoicedItem.objects.filter(
                deal_id=deal_id, deal_item_id=i.id, invoice_ref=ref,
            ).exists():
                rows.append(InvoicedItem(
                    deal_id=deal_id, deal_item_id=i.id,
                    invoice_ref=ref, qty_invoiced=i.qty,
                ))
        if rows:
            InvoicedItem.objects.bulk_create(rows)

    def get_invoiced_items(self, deal_id: int, invoice_ref: str):
        ref = self._normalize_invoice_ref(invoice_ref)
        qs = InvoicedItem.objects.filter(deal_id=deal_id, invoice_ref=ref)
        return [_d(i) for i in qs]

    def get_invoices_for_deal(self, deal_id: int):
        """Distinct invoice_refs for a deal."""
        qs = (InvoicedItem.objects.filter(deal_id=deal_id)
              .values_list('invoice_ref', flat=True).distinct())
        return list(qs)

    # ── Delivery status ──────────────────────────────────────────────────────

    def get_delivery_status(self, deal_id: int, invoice_ref: str):
        """
        For each invoiced item, return qty_invoiced, qty_delivered, remaining.
        """
        ref = self._normalize_invoice_ref(invoice_ref)
        result = []
        inv_rows = InvoicedItem.objects.filter(deal_id=deal_id, invoice_ref=ref)
        for ii in inv_rows:
            item = DealItem.objects.filter(pk=ii.deal_item_id).first()
            if not item:
                continue
            delivered = sum(
                float(dni.qty_delivered) for dni in DeliveryNoteItem.objects.filter(
                    deal_item_id=ii.deal_item_id,
                    delivery_note__invoice_ref=ref,
                )
            )
            result.append({
                'deal_item_id':  ii.deal_item_id,
                'description':   item.description,
                'unit':          item.unit or '',
                'qty_invoiced':  float(ii.qty_invoiced),
                'qty_delivered': delivered,
                'qty_remaining': float(ii.qty_invoiced) - delivered,
            })
        return result

    # ── Delivery notes ───────────────────────────────────────────────────────

    def create_delivery_note(self, deal_id: int, invoice_ref: str,
                             selections: list, receiver_name: str = '',
                             notes: str = '', user_id=None) -> tuple:
        """
        selections: [{deal_item_id, qty_delivered}, ...]
        Returns: (delivery_note_id, reference)
        """
        ref       = self._normalize_invoice_ref(invoice_ref)
        prev      = DeliveryNote.objects.filter(deal_id=deal_id,
                                                invoice_ref=ref).count()
        sequence  = prev + 1
        dn_ref    = f'DN-{ref}-{sequence:02d}'

        dn = DeliveryNote.objects.create(
            deal_id=deal_id, invoice_ref=ref, sequence=sequence,
            reference=dn_ref, receiver_name=receiver_name, notes=notes,
            created_by_id=user_id,
        )
        for sel in selections:
            qty = float(sel.get('qty_delivered') or 0)
            if qty <= 0:
                continue
            DeliveryNoteItem.objects.create(
                delivery_note=dn,
                deal_item_id=sel['deal_item_id'],
                qty_delivered=qty,
            )
        return dn.id, dn_ref

    def get_delivery_note(self, delivery_note_id: int):
        dn = DeliveryNote.objects.select_related('deal', 'deal__client') \
                                  .filter(pk=delivery_note_id).first()
        if not dn:
            return None
        d = _d(dn)
        if dn.deal:
            d['deal_reference'] = dn.deal.reference
            if dn.deal.client:
                d['client_name']  = dn.deal.client.full_name
                d['client_addr1'] = dn.deal.client.address_line1 or ''
                d['client_addr2'] = dn.deal.client.address_line2 or ''
            d['seller_entity'] = dn.deal.seller_entity
        return d

    def get_delivery_note_items(self, delivery_note_id: int):
        rows = DeliveryNoteItem.objects.filter(
            delivery_note_id=delivery_note_id,
        ).select_related('deal_item')
        out = []
        for r in rows:
            out.append({
                'deal_item_id':  r.deal_item_id,
                'description':   r.deal_item.description,
                'unit':          r.deal_item.unit or '',
                'qty_delivered': float(r.qty_delivered),
            })
        return out

    def get_delivery_notes_for_deal(self, deal_id: int):
        return [_d(dn) for dn in DeliveryNote.objects.filter(deal_id=deal_id)]
