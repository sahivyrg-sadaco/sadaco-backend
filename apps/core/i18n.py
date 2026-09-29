# =============================================================================
# apps/core/i18n.py — Bilingual support (Spanish / English)
#
# Usage:  from apps.core.i18n import t
#         t("deals.new", lang="es")  →  "Nueva Oferta"
# =============================================================================

STRINGS = {
    # ── Navigation ────────────────────────────────────────────────────────────
    "nav.dashboard":        {"es": "Panel",             "en": "Dashboard"},
    "nav.deals":            {"es": "Ofertas",           "en": "Deals"},
    "nav.clients":          {"es": "Clientes",          "en": "Clients"},
    "nav.suppliers":        {"es": "Proveedores",       "en": "Suppliers"},
    "nav.documents":        {"es": "Documentos",        "en": "Documents"},
    "nav.delivery_notes":   {"es": "Notas de Entrega",  "en": "Delivery Notes"},
    "nav.inventory":        {"es": "Inventario",        "en": "Inventory"},
    "nav.payments":         {"es": "Pagos",             "en": "Payments"},
    "nav.notifications":    {"es": "Notificaciones",    "en": "Notifications"},
    "nav.users":            {"es": "Usuarios",          "en": "Users"},
    "nav.logout":           {"es": "Salir",             "en": "Logout"},

    # ── Auth ──────────────────────────────────────────────────────────────────
    "auth.login":           {"es": "Iniciar Sesión",    "en": "Log In"},
    "auth.email":           {"es": "Correo",            "en": "Email"},
    "auth.password":        {"es": "Contraseña",        "en": "Password"},
    "auth.invalid":         {"es": "Credenciales incorrectas", "en": "Invalid credentials"},
    "auth.unauthorized":    {"es": "No autorizado",     "en": "Unauthorized"},
    "auth.token_expired":   {"es": "Sesión expirada",   "en": "Session expired"},

    # ── Dashboard ─────────────────────────────────────────────────────────────
    "dash.pipeline":        {"es": "Pipeline",          "en": "Pipeline"},
    "dash.total_deals":     {"es": "Total Ofertas",     "en": "Total Deals"},
    "dash.open_deals":      {"es": "Ofertas Activas",   "en": "Open Deals"},
    "dash.invoiced_value":  {"es": "Valor Facturado",   "en": "Invoiced Value"},
    "dash.overdue":         {"es": "Facturas Vencidas", "en": "Overdue Invoices"},

    # ── Deals ─────────────────────────────────────────────────────────────────
    "deals.new":            {"es": "Nueva Oferta",      "en": "New Deal"},
    "deals.reference":      {"es": "Referencia",        "en": "Reference"},
    "deals.client":         {"es": "Cliente",           "en": "Client"},
    "deals.seller":         {"es": "Entidad Vendedora", "en": "Seller Entity"},
    "deals.stage":          {"es": "Etapa",             "en": "Stage"},
    "deals.status":         {"es": "Estado",            "en": "Status"},
    "deals.currency":       {"es": "Moneda",            "en": "Currency"},
    "deals.incoterm":       {"es": "Incoterm",          "en": "Incoterm"},
    "deals.payment_terms":  {"es": "Condiciones de Pago", "en": "Payment Terms"},
    "deals.delivery_time":  {"es": "Tiempo de Entrega", "en": "Delivery Time"},
    "deals.client_ref":     {"es": "Ref. Cliente",      "en": "Client Ref"},
    "deals.notes":          {"es": "Notas",             "en": "Notes"},
    "deals.created":        {"es": "Creada",            "en": "Created"},
    "deals.updated":        {"es": "Actualizada",       "en": "Updated"},
    "deals.items":          {"es": "Ítems",             "en": "Items"},
    "deals.won":            {"es": "Ganada",            "en": "Won"},
    "deals.lost":           {"es": "Perdida",           "en": "Lost"},
    "deals.lost_reason":    {"es": "Motivo de pérdida", "en": "Lost reason"},
    "deals.exchange_rate":  {"es": "Tipo de cambio",    "en": "Exchange rate"},

    # ── Pipeline stages ───────────────────────────────────────────────────────
    "stage.Quoting":        {"es": "Cotizando",         "en": "Quoting"},
    "stage.Negotiating":    {"es": "Negociando",        "en": "Negotiating"},
    "stage.PO Sent":        {"es": "OC Enviada",        "en": "PO Sent"},
    "stage.Invoiced":       {"es": "Facturado",         "en": "Invoiced"},
    "stage.Delivered":      {"es": "Entregado",         "en": "Delivered"},
    "stage.Closed":         {"es": "Cerrado",           "en": "Closed"},
    "stage.Cancelled":      {"es": "Cancelado",         "en": "Cancelled"},

    # ── Deal items ────────────────────────────────────────────────────────────
    "items.description":    {"es": "Descripción",       "en": "Description"},
    "items.part_number":    {"es": "N° de Parte",       "en": "Part Number"},
    "items.brand":          {"es": "Marca",             "en": "Brand"},
    "items.model":          {"es": "Modelo",            "en": "Model"},
    "items.qty":            {"es": "Cantidad",          "en": "Qty"},
    "items.unit":           {"es": "Unidad",            "en": "Unit"},
    "items.unit_cost":      {"es": "Costo Unitario",    "en": "Unit Cost"},
    "items.unit_price":     {"es": "Precio Unitario",   "en": "Unit Price"},
    "items.margin":         {"es": "Margen",            "en": "Margin"},
    "items.total_cost":     {"es": "Costo Total",       "en": "Total Cost"},
    "items.total_price":    {"es": "Precio Total",      "en": "Total Price"},
    "items.add":            {"es": "Agregar Ítem",      "en": "Add Item"},

    # ── Documents ─────────────────────────────────────────────────────────────
    "doc.quote":            {"es": "Cotización",        "en": "Quote"},
    "doc.po":               {"es": "Orden de Compra",   "en": "Purchase Order"},
    "doc.invoice":          {"es": "Factura",           "en": "Invoice"},
    "doc.delivery_note":    {"es": "Nota de Entrega",   "en": "Delivery Note"},
    "doc.generate":         {"es": "Generar",           "en": "Generate"},
    "doc.download_xlsx":    {"es": "Descargar XLSX",    "en": "Download XLSX"},
    "doc.download_pdf":     {"es": "Descargar PDF",     "en": "Download PDF"},
    "doc.upload_drive":     {"es": "Subir a Drive",     "en": "Upload to Drive"},

    # ── Clients / Suppliers ───────────────────────────────────────────────────
    "client.code":          {"es": "Código",            "en": "Code"},
    "client.full_name":     {"es": "Razón Social",      "en": "Full Name"},
    "client.address":       {"es": "Dirección",         "en": "Address"},
    "client.country":       {"es": "País",              "en": "Country"},
    "client.contact":       {"es": "Contacto",          "en": "Contact"},
    "client.email":         {"es": "Correo",            "en": "Email"},
    "client.phone":         {"es": "Teléfono",          "en": "Phone"},

    # ── Payments ──────────────────────────────────────────────────────────────
    "pay.record":           {"es": "Registrar Pago",    "en": "Record Payment"},
    "pay.amount":           {"es": "Monto",             "en": "Amount"},
    "pay.date":             {"es": "Fecha",             "en": "Date"},
    "pay.method":           {"es": "Método",            "en": "Method"},
    "pay.balance":          {"es": "Saldo",             "en": "Balance"},
    "pay.overdue_30":       {"es": "Vencido 30d",       "en": "Overdue 30d"},
    "pay.overdue_60":       {"es": "Vencido 60d",       "en": "Overdue 60d"},
    "pay.overdue_90":       {"es": "Vencido 90d+",      "en": "Overdue 90d+"},

    # ── Inventory ─────────────────────────────────────────────────────────────
    "inv.sku":              {"es": "SKU",               "en": "SKU"},
    "inv.on_hand":          {"es": "En Stock",          "en": "On Hand"},
    "inv.reserved":         {"es": "Reservado",         "en": "Reserved"},
    "inv.reorder":          {"es": "Punto de Reorden",  "en": "Reorder Point"},
    "inv.low_stock":        {"es": "Stock Bajo",        "en": "Low Stock"},
    "inv.adjust":           {"es": "Ajuste",            "en": "Adjustment"},

    # ── Notifications ────────────────────────────────────────────────────────
    "notif.mark_read":      {"es": "Marcar como leída", "en": "Mark as read"},
    "notif.no_new":         {"es": "Sin notificaciones","en": "No notifications"},

    # ── General ──────────────────────────────────────────────────────────────
    "general.save":         {"es": "Guardar",           "en": "Save"},
    "general.cancel":       {"es": "Cancelar",          "en": "Cancel"},
    "general.delete":       {"es": "Eliminar",          "en": "Delete"},
    "general.edit":         {"es": "Editar",            "en": "Edit"},
    "general.view":         {"es": "Ver",               "en": "View"},
    "general.search":       {"es": "Buscar",            "en": "Search"},
    "general.filter":       {"es": "Filtrar",           "en": "Filter"},
    "general.actions":      {"es": "Acciones",          "en": "Actions"},
    "general.confirm":      {"es": "Confirmar",         "en": "Confirm"},
    "general.yes":          {"es": "Sí",                "en": "Yes"},
    "general.no":           {"es": "No",                "en": "No"},
    "general.loading":      {"es": "Cargando...",       "en": "Loading..."},
    "general.error":        {"es": "Error",             "en": "Error"},
    "general.success":      {"es": "Guardado",          "en": "Saved"},
    "general.not_found":    {"es": "No encontrado",     "en": "Not found"},
}


def t(key: str, lang: str = "es") -> str:
    """
    Return translated string for key in the requested language.
    Falls back to English, then to the key itself if not found.
    """
    entry = STRINGS.get(key)
    if not entry:
        return key
    return entry.get(lang) or entry.get("en") or key


def get_all_strings(lang: str = "es") -> dict:
    """Return a flat dict of all translated strings for the given language."""
    return {k: t(k, lang) for k in STRINGS}
