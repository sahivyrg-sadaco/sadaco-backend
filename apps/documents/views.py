"""
Documents views:
- Client and deal attachments (upload, list, delete)
- Document generation (Quote / PO / Invoice / Delivery Note → xlsx + pdf)
- Delivery notes and delivery status
"""
import mimetypes
import os

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.views import APIView

from apps.clients.models import Client
from apps.core.permissions import (
    IsSalesOrAdmin, IsOperationsOrAdmin, IsSalesOrOperationsOrAdmin,
)
from apps.deals.models import Deal

from .models import (
    FileAttachment, DeliveryNote,
)
from .serializers import (
    FileAttachmentSerializer, DeliveryNoteSerializer,
)


# ── Client attachments ───────────────────────────────────────────────────────

class ClientAttachmentListCreateView(APIView):
    """
    GET  /api/clients/{id}/attachments/
    POST /api/clients/{id}/attachments/  (multipart: field name 'file')
    """
    parser_classes = [MultiPartParser, FormParser]

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsSalesOrAdmin()]
        return [IsAuthenticated()]

    def get(self, request, pk):
        get_object_or_404(Client, pk=pk)
        qs = FileAttachment.objects.filter(client_id=pk)
        return Response(FileAttachmentSerializer(qs, many=True).data)

    def post(self, request, pk):
        client   = get_object_or_404(Client, pk=pk)
        upload   = request.FILES.get('file')
        doc_type = request.data.get('doc_type', 'Attachment')
        if not upload:
            return Response({'error': 'file is required'},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            from . import drive_service
            subfolder = request.data.get('subfolder', 'General')
            folder_id = drive_service.get_client_folder(client.id, subfolder)
            meta = drive_service.upload_file(
                upload.read(),
                upload.name,
                upload.content_type or 'application/octet-stream',
                folder_id,
            )
        except Exception as e:
            return Response(
                {'error': f'Drive upload failed: {e}'},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        att = FileAttachment.objects.create(
            drive_file_id   = meta['drive_file_id'],
            file_name       = meta['file_name'],
            web_view_link   = meta['web_view_link'],
            drive_folder_id = folder_id,
            mime_type       = upload.content_type or '',
            file_size_bytes = meta.get('file_size_bytes'),
            client          = client,
            doc_type        = doc_type,
            generated_by    = request.user,
        )
        return Response(FileAttachmentSerializer(att).data,
                        status=status.HTTP_201_CREATED)


# ── Deal attachments ─────────────────────────────────────────────────────────

class DealAttachmentListCreateView(APIView):
    """
    GET  /api/deals/{id}/attachments/
    POST /api/deals/{id}/attachments/  (multipart: field name 'file')
    """
    parser_classes = [MultiPartParser, FormParser]

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsSalesOrOperationsOrAdmin()]
        return [IsAuthenticated()]

    def get(self, request, pk):
        get_object_or_404(Deal, pk=pk)
        qs = FileAttachment.objects.filter(deal_id=pk)
        return Response(FileAttachmentSerializer(qs, many=True).data)

    def post(self, request, pk):
        deal     = get_object_or_404(Deal, pk=pk)
        upload   = request.FILES.get('file')
        doc_type = request.data.get('doc_type', 'Attachment')
        if not upload:
            return Response({'error': 'file is required'},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            from . import drive_service
            folder_id = drive_service.get_deal_folder(deal.id)
            meta = drive_service.upload_file(
                upload.read(),
                upload.name,
                upload.content_type or 'application/octet-stream',
                folder_id,
            )
        except Exception as e:
            return Response(
                {'error': f'Drive upload failed: {e}'},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        att = FileAttachment.objects.create(
            drive_file_id   = meta['drive_file_id'],
            file_name       = meta['file_name'],
            web_view_link   = meta['web_view_link'],
            drive_folder_id = folder_id,
            mime_type       = upload.content_type or '',
            file_size_bytes = meta.get('file_size_bytes'),
            deal            = deal,
            doc_type        = doc_type,
            generated_by    = request.user,
        )
        return Response(FileAttachmentSerializer(att).data,
                        status=status.HTTP_201_CREATED)


class AttachmentDeleteView(APIView):
    """DELETE /api/attachments/{id}/ — removes both Drive file and DB row."""
    permission_classes = [IsSalesOrOperationsOrAdmin]

    def delete(self, request, pk):
        att = FileAttachment.objects.filter(pk=pk).first()
        if not att:
            return Response({'error': 'Not found'}, status=404)
        try:
            from . import drive_service
            drive_service.delete_file(att.drive_file_id)
        except Exception:
            pass  # Still remove DB row even if Drive fails
        att.delete()
        return Response(status=204)


# ── Document generation ──────────────────────────────────────────────────────

DOC_TYPE_MAP = {
    'quote':          'Quote',
    'po':             'PO',
    'invoice':        'Invoice',
    'delivery_note':  'Delivery Note',
}


class GenerateDocumentView(APIView):
    """
    POST /api/deals/{id}/generate/{doc_type}/

    doc_type ∈ {quote, po, invoice, delivery_note}.
    Generates xlsx + pdf, uploads both to Drive, creates FileAttachment rows.
    """
    permission_classes = [IsSalesOrOperationsOrAdmin]

    def post(self, request, pk, doc_type):
        deal = get_object_or_404(Deal, pk=pk)

        if doc_type not in DOC_TYPE_MAP:
            return Response(
                {'error': f'Unknown doc_type: {doc_type}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            from .generators.db_adapter import DjangoDBAdapter
            from .generators import doc_generator, pdf_generator
            from . import drive_service
        except ImportError as e:
            return Response(
                {'error': f'Generator imports failed: {e}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        db        = DjangoDBAdapter()
        freight   = request.data.get('freight')
        notes     = request.data.get('notes', '')
        extra     = {}

        try:
            # 1) Generate xlsx
            if doc_type == 'quote':
                xlsx_path = doc_generator.generate_quote(
                    db, deal.id, freight=freight, notes=notes,
                )
            elif doc_type == 'po':
                quote_id = request.data.get('supplier_quote_id')
                if not quote_id:
                    return Response(
                        {'error': 'supplier_quote_id required for PO'},
                        status=400,
                    )
                xlsx_path = doc_generator.generate_purchase_order(
                    db, deal.id, int(quote_id), freight=freight, notes=notes,
                )
                extra['supplier_quote_id'] = int(quote_id)
            elif doc_type == 'invoice':
                invoice_ref = request.data.get('invoice_number') or request.data.get('invoice_ref')
                xlsx_path = doc_generator.generate_invoice(
                    db, deal.id, invoice_number=invoice_ref,
                    freight=freight, notes=notes,
                )
                if invoice_ref:
                    db.record_invoiced_items(deal.id, invoice_ref)
            else:  # delivery_note
                dn_id = request.data.get('delivery_note_id')
                if not dn_id:
                    return Response(
                        {'error': 'delivery_note_id required for delivery_note'},
                        status=400,
                    )
                from .generators import delivery_note_generator
                xlsx_path = delivery_note_generator.generate_delivery_note(
                    db, int(dn_id),
                )

            # 2) Generate matching PDF
            pdf_path = pdf_generator.generate_pdf(
                doc_type=DOC_TYPE_MAP[doc_type],
                db=db, deal_id=deal.id,
                **extra,
            )
        except Exception as e:
            return Response(
                {'error': f'Generation failed: {e}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # 3) Upload both to Drive and create DB rows
        try:
            folder_id = drive_service.get_deal_folder(deal.id)
        except Exception as e:
            return Response(
                {'error': f'Could not resolve Drive folder: {e}'},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        result = {'success': True}
        for key, path in (('xlsx', xlsx_path), ('pdf', pdf_path)):
            if not path or not os.path.exists(path):
                continue
            fname = os.path.basename(path)
            mime, _ = mimetypes.guess_type(fname)
            mime = mime or (
                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                if key == 'xlsx' else 'application/pdf'
            )
            with open(path, 'rb') as f:
                file_bytes = f.read()
            try:
                meta = drive_service.upload_file(file_bytes, fname, mime, folder_id)
            except Exception as e:
                result[key] = {'error': f'Drive upload failed: {e}'}
                continue

            att = FileAttachment.objects.create(
                drive_file_id   = meta['drive_file_id'],
                file_name       = meta['file_name'],
                web_view_link   = meta['web_view_link'],
                drive_folder_id = folder_id,
                mime_type       = mime,
                file_size_bytes = meta.get('file_size_bytes'),
                deal            = deal,
                doc_type        = DOC_TYPE_MAP[doc_type],
                generated_by    = request.user,
            )
            result[key] = {
                'web_view_link': att.web_view_link,
                'attachment_id': att.id,
                'file_name':     att.file_name,
            }

        return Response(result)


# ── Delivery notes ───────────────────────────────────────────────────────────

class DealDeliveryNoteListCreateView(APIView):
    """
    GET  /api/deals/{id}/delivery-notes/
    POST /api/deals/{id}/delivery-notes/  (body: invoice_ref, selections=[...])
    """
    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsOperationsOrAdmin()]
        return [IsAuthenticated()]

    def get(self, request, pk):
        get_object_or_404(Deal, pk=pk)
        qs = DeliveryNote.objects.filter(deal_id=pk)
        return Response(DeliveryNoteSerializer(qs, many=True).data)

    def post(self, request, pk):
        deal = get_object_or_404(Deal, pk=pk)
        invoice_ref   = request.data.get('invoice_ref')
        selections    = request.data.get('selections') or []
        receiver_name = request.data.get('receiver_name', '')
        notes         = request.data.get('notes', '')
        if not invoice_ref or not selections:
            return Response(
                {'error': 'invoice_ref and selections are required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from .generators.db_adapter import DjangoDBAdapter
        db = DjangoDBAdapter()
        dn_id, ref = db.create_delivery_note(
            deal.id, invoice_ref, selections,
            receiver_name=receiver_name, notes=notes,
            user_id=request.user.id,
        )
        dn = DeliveryNote.objects.filter(pk=dn_id).first()
        return Response(DeliveryNoteSerializer(dn).data,
                        status=status.HTTP_201_CREATED)


class DealDeliveryStatusView(APIView):
    """GET /api/deals/{id}/delivery-status/{invoice_ref}/"""
    permission_classes = [IsAuthenticated]

    def get(self, request, pk, invoice_ref):
        get_object_or_404(Deal, pk=pk)
        from .generators.db_adapter import DjangoDBAdapter
        db = DjangoDBAdapter()
        return Response(db.get_delivery_status(pk, invoice_ref))
