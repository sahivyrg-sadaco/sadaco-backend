"""Deal-scoped endpoints. Mounted at /api/deals/."""
from django.urls import path

from . import views
from apps.quotes.views import (
    DealQuoteListCreateView,
    DealQuoteDetailView,
    DealQuoteSelectView,
    DealQuoteApplyView,
    DealQuoteItemListCreateView,
)
from apps.documents.views import (
    DealAttachmentListCreateView,
    GenerateDocumentView,
    DealDeliveryNoteListCreateView,
    DealDeliveryStatusView,
)


urlpatterns = [
    # Deal list / detail
    path('',                      views.DealListCreateView.as_view()),
    path('<int:pk>/',             views.DealDetailView.as_view()),

    # Deal meta
    path('<int:pk>/currency/',    views.DealCurrencyView.as_view()),
    path('<int:pk>/totals/',      views.deal_totals_view),
    path('<int:pk>/timeline/',    views.deal_timeline),
    path('<int:pk>/notes/',       views.deal_add_note),

    # Deal items
    path('<int:pk>/items/',               views.DealItemListCreateView.as_view()),
    path('<int:pk>/items/<int:item_id>/', views.DealItemDetailView.as_view()),

    # Splits
    path('<int:pk>/splits/',
         views.DealSplitListCreateView.as_view()),
    path('<int:pk>/splits/<int:parent_item_id>/<int:quote_id>/',
         views.DealSplitDeleteView.as_view()),

    # Supplier quotes
    path('<int:pk>/quotes/',               DealQuoteListCreateView.as_view()),
    path('<int:pk>/quotes/<int:qid>/',     DealQuoteDetailView.as_view()),
    path('<int:pk>/quotes/<int:qid>/select/', DealQuoteSelectView.as_view()),
    path('<int:pk>/quotes/<int:qid>/apply/',  DealQuoteApplyView.as_view()),
    path('<int:pk>/quotes/<int:qid>/items/',  DealQuoteItemListCreateView.as_view()),

    # Attachments + generation
    path('<int:pk>/attachments/',          DealAttachmentListCreateView.as_view()),
    path('<int:pk>/generate/<str:doc_type>/',  GenerateDocumentView.as_view()),

    # Delivery notes
    path('<int:pk>/delivery-notes/',       DealDeliveryNoteListCreateView.as_view()),
    path('<int:pk>/delivery-status/<str:invoice_ref>/',
         DealDeliveryStatusView.as_view()),
]
