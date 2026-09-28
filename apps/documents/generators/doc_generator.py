# =============================================================================
# doc_generator.py — Generates Quote, Purchase Order, and Invoice as .xlsx files
#
# Styling is pixel-matched to the SADACO template (MASISA_-_23002626_-_6000095257.xlsx):
#   - Font: Roboto throughout
#   - Row 1: solid green bar (FF6AA84F), 6pt tall — logo anchors here
#   - Row 2: spacer (9.75pt)
#   - Logo image: anchored at E1, 65x65px — place logo.png in modules/assets/
#   - Company name: Roboto 20pt, accent color, no bold — A3:B3
#   - Address lines: Roboto, gray #666666
#   - Doc title row 7: Roboto 20pt bold, accent — A7:D7
#   - Date: Roboto 9pt bold gray #999999 — F7:F8 merged
#   - Doc ref: Roboto 20pt bold, accent — A8:B9 merged
#   - Meta labels: Roboto 11pt bold #434343
#   - Meta values: Roboto, gray #666666
#   - Spacer row 16: 6.75pt
#   - Table header row 17: Roboto 11pt bold, accent color text,
#       medium borders top+bottom in accent color, centered+wrapped
#   - Item rows: ALL rows filled EEF7E3 (light green tint), Roboto
#   - Before totals: thin top border in accent color across all cols
#   - Notes label: Roboto bold #999999, A:C merged
#   - Subtotal label: Roboto gray right-aligned col E; value bold col F
#   - Grand total: Roboto 20pt bold, accent, right-aligned, E:F merged
#   - Column widths: A=2.63, B=47.38, C=6.63, D=10.75, E=13.5, F=12.25
#   - No grid lines
#
# COLOR SCHEME per document:
#   Quote          → dark green  #38761D
#   Invoice        → blue        #1155CC
#   Purchase Order → orange      #FF9900
#
# LOGO SETUP:
#   1. Create folder:  modules/assets/
#   2. Place logo PNG: modules/assets/logo.png
#   (extract from the reference xlsx or use your own SADACO logo file)
# =============================================================================

import os
from datetime import datetime
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.drawing.image import Image as XLImage

def _export_dir():
    """Returns the exports directory, creating it if needed."""
    d = os.path.join(os.path.dirname(__file__), "..", "data", "exports")
    os.makedirs(d, exist_ok=True)
    return os.path.abspath(d)

EXPORT_DIR = _export_dir()
ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")
LOGO_PATH  = os.path.join(ASSETS_DIR, "logo.png")

# Per-document-type color scheme — accent, top-bar fill, item-row fill, border colors
# Extracted from the real SADACO template files.
DOC_COLORS = {
    "quote": {
        "accent":      "FF38761D",   # dark green
        "header_bar":  "FF6AA84F",   # medium green (row 1 fill)
        "item_fill":   "FFEEF7E3",   # light green tint (all rows same)
        "item_alt":    None,         # no alternating — same fill every row
        "border_top":  "FF38761D",   # table header top border
        "border_bot":  "FF38761D",   # table header bottom border
        "sep_border":  "FF38761D",   # thin separator before totals
    },
    "po": {
        "accent":      "FFFF9900",   # orange
        "header_bar":  "FFFF9900",   # orange (row 1 fill)
        "item_fill":   "FFF3F3F3",   # light gray (odd rows)
        "item_alt":    "FFFFFFFF",   # white (even rows)
        "border_top":  "FFFF9900",   # table header top border
        "border_bot":  "FFFF9900",   # table header bottom border
        "sep_border":  "FFFF9900",   # thin separator before totals
    },
    "invoice": {
        "accent":      "FF1155CC",   # dark blue
        "header_bar":  "FF3C78D8",   # mid blue (row 1 fill)
        "item_fill":   "FFCFE2F3",   # light blue (odd rows)
        "item_alt":    "FFFFFFFF",   # white (even rows)
        "border_top":  "FF3C78D8",   # table header top border
        "border_bot":  "FF4A86E8",   # table header bottom border (slightly lighter)
        "sep_border":  "FF1155CC",   # thin separator before totals
    },
}

FONT_NAME  = "Roboto"
GRAY_TEXT  = "FF666666"
GRAY_LIGHT = "FF999999"
DARK_TEXT  = "FF434343"
BLACK      = "FF000000"

NO_BORDER = Border()


# ── Low-level helpers ─────────────────────────────────────────────────────────

def _f(size=10, bold=False, color=BLACK):
    return Font(name=FONT_NAME, size=size, bold=bold, color=color)

def _a(h="left", wrap=False, v="bottom"):
    return Alignment(horizontal=h, vertical=v, wrap_text=wrap)

def _fill(hex_color):
    return PatternFill("solid", fgColor=hex_color)

def _no_fill():
    return PatternFill(fill_type=None)

def _border_top(style="thin", color="FF000000"):
    s = Side(border_style=style, color=color)
    return Border(top=s)

def _border_tb(style="medium", color="FF000000"):
    s = Side(border_style=style, color=color)
    return Border(top=s, bottom=s)

def _c(ws, row, col, value,
       size=10, bold=False, color=BLACK,
       h="left", wrap=False, v="bottom",
       fill=None, border=None, num_format=None):
    cell = ws.cell(row=row, column=col, value=value)
    cell.font      = _f(size, bold, color)
    cell.alignment = _a(h, wrap, v)
    cell.border    = border if border is not None else NO_BORDER
    cell.fill      = _fill(fill) if fill else _no_fill()
    if num_format:
        cell.number_format = num_format
    return cell

def _m(ws, r1, c1, r2, c2):
    ws.merge_cells(start_row=r1, start_column=c1, end_row=r2, end_column=c2)


# ── Logo insertion ────────────────────────────────────────────────────────────

def _add_logo(ws, logo_bytes: bytes):
    """
    Embed logo_bytes (raw PNG from the DB) into the top-right header area.
    - Uses flood-fill from the image corners to detect the background region
    - Makes background pixels fully transparent (RGBA alpha = 0)
    - Resizes to 80x80px and saves as PNG with transparency
    - Anchors at col E (index 4), row 1 (index 0) with 762000x762000 EMU
    """
    if not logo_bytes:
        return
    try:
        import io
        import numpy as np
        from PIL import Image as PILImage
        from scipy.ndimage import label
        from openpyxl.drawing.spreadsheet_drawing import OneCellAnchor, AnchorMarker
        from openpyxl.drawing.xdr import XDRPositiveSize2D

        src = PILImage.open(io.BytesIO(logo_bytes)).convert("RGB")
        arr = np.array(src)

        # Flood-fill background detection: find connected region of exact-black
        # pixels that touches the top-left corner — much cleaner than a threshold.
        exact_black = (arr[:,:,0] == 0) & (arr[:,:,1] == 0) & (arr[:,:,2] == 0)
        labeled, _ = label(exact_black)
        corner_label = labeled[0, 0]
        bg_mask = (labeled == corner_label) if corner_label != 0 else (exact_black)

        # Build RGBA: copy RGB, set alpha=0 for background pixels
        rgba = np.zeros((arr.shape[0], arr.shape[1], 4), dtype=np.uint8)
        rgba[:,:,:3] = arr
        rgba[:,:,3] = 255
        rgba[bg_mask, 3] = 0

        final = PILImage.fromarray(rgba, "RGBA").resize((79, 79), PILImage.LANCZOS)

        buf = io.BytesIO()
        final.save(buf, format="PNG")
        buf.seek(0)

        img = XLImage(buf)
        # Centered within column F only, spanning rows 2-5
        # Col F width: 1067752 EMU (112px); rows 2-5: 790575 EMU (83px)
        # logo = 752475 EMU (79px), colOff centers it within col F
        size   = XDRPositiveSize2D(cx=752475, cy=752475)
        marker = AnchorMarker(col=5, colOff=157638, row=1, rowOff=19050)
        img.anchor = OneCellAnchor(_from=marker, ext=size)
        ws.add_image(img)
    except Exception:
        pass


# ── Shared document header (rows 1–16) ───────────────────────────────────────

def _header(ws, seller_entity, doc_title, doc_ref, accent, meta_rows, logo_bytes=None, doc_colors=None):
    """
    Builds the document header exactly matching the SADACO template.

      Row 1  : [A1:F1] solid green bar (6pt) — logo placed at E1
      Row 2  : spacer (9.75pt)
      Row 3  : [A3:B3] Company name 20pt accent
      Row 4  : [A4:B4] Address line 1
      Row 5  : [A5:B5] Address line 2
      Row 6  : spacer (9.75pt)
      Row 7  : [A7:D7] Doc title 20pt bold | [E7] Date label | [F7:F8] Date value
      Row 8  : [A8:B9] Doc ref 20pt bold   | meta rows start C8
      Row 9+ : meta rows continue
      Row 16 : thin spacer (6.75pt)

    Returns 17 (row where table header goes).
    """
    from modules.config import SELLER_ENTITIES
    entity = SELLER_ENTITIES.get(seller_entity, {})

    ws.sheet_view.showGridLines = False

    # Column widths — exact match to template
    ws.column_dimensions["A"].width = 2.63   # narrow gutter — do not change
    ws.column_dimensions["B"].width = 47.38  # description column — do not change
    ws.column_dimensions["C"].width = 9.9    # longest line: '(Cant.)'
    ws.column_dimensions["D"].width = 11.7   # longest line: '(Unidad)'
    ws.column_dimensions["E"].width = 18.4   # longest line: '(Valor Unitario)'
    ws.column_dimensions["F"].width = 15.3   # longest line: '(Valor Total)' 

    # Row heights
    ws.row_dimensions[1].height  = 6.0
    ws.row_dimensions[2].height  = 9.75
    ws.row_dimensions[3].height  = 19.5
    ws.row_dimensions[4].height  = 16.5
    ws.row_dimensions[5].height  = 16.5
    ws.row_dimensions[6].height  = 9.75
    ws.row_dimensions[7].height  = 21.0
    ws.row_dimensions[8].height  = 16.5
    ws.row_dimensions[9].height  = 16.5
    ws.row_dimensions[16].height = 6.75
    for r in range(10, 16):
        ws.row_dimensions[r].height = 16.5

    # ── Row 1: accent top bar ──
    _m(ws, 1, 1, 1, 6)
    bar_color = (doc_colors or {}).get("header_bar", "FF6AA84F")
    ws.cell(row=1, column=1).fill = _fill(bar_color)

    # ── Rows 2–3: Company name — merged A2:F3, style of row 3 (20pt accent, bottom-aligned) ──
    _m(ws, 2, 1, 3, 6)
    _c(ws, 2, 1, seller_entity, size=20, color=accent, v="bottom")

    # ── Rows 4–5: Address ──
    _m(ws, 4, 1, 4, 2); _m(ws, 4, 3, 4, 6)
    _c(ws, 4, 1, entity.get("address_line1", ""), color=GRAY_TEXT, v="bottom")
    _m(ws, 5, 1, 5, 2); _m(ws, 5, 3, 5, 6)
    _c(ws, 5, 1, entity.get("address_line2", ""), color=GRAY_TEXT, v="top")

    # ── Row 6: spacer ──
    _m(ws, 6, 1, 6, 6)

    # ── Row 7: empty merged left (A7:D7) + Date label (E7) + Date value (F7:F8) ──
    _m(ws, 7, 1, 7, 4)
    _c(ws, 7, 5, "Date (Fecha):", bold=True, h="right", v="top")
    _m(ws, 7, 6, 8, 6)
    date_str = datetime.now().strftime("%d de %B, %Y")
    _c(ws, 7, 6, date_str, size=9, bold=True, color=GRAY_LIGHT, v="top", wrap=True)

    # ── Rows 8–9 LEFT: Full doc title with label (A8:B9) ──
    _m(ws, 8, 1, 9, 2)
    _c(ws, 8, 1, doc_title, size=17, bold=True, color=accent, v="top")

    # ── Rows 8–9 RIGHT: Client Ref label (C8) + value (C9:F9) ──
    client_ref_label = meta_rows[0][0] if len(meta_rows) > 0 else "Client Ref. (Ref. Cliente):"
    client_ref_value = meta_rows[0][1] if len(meta_rows) > 0 else ""
    _c(ws, 8, 3, client_ref_label, size=11, bold=True, color=DARK_TEXT, v="bottom")
    _m(ws, 9, 3, 9, 6)
    _c(ws, 9, 3, client_ref_value, color=GRAY_TEXT, v="bottom")

    # ── Row 10 LEFT: "Company:" label (A10:B10) ──
    _m(ws, 10, 1, 10, 2)
    _c(ws, 10, 1, "Company (Compañía):", size=11, bold=True, color=DARK_TEXT, v="bottom")

    # ── Row 10 RIGHT: Delivery Conditions label (C10:F10) ──
    deliv_cond_label = meta_rows[1][0] if len(meta_rows) > 1 else "Delivery Conditions (Condición de Entrega):"
    deliv_cond_value = meta_rows[1][1] if len(meta_rows) > 1 else ""
    _c(ws, 10, 3, deliv_cond_label, size=11, bold=True, color=DARK_TEXT, v="bottom")

    # ── Row 11 LEFT: Client name ──
    client_name = meta_rows[2][1] if len(meta_rows) > 2 else ""
    _c(ws, 11, 1, client_name, bold=True, color=GRAY_TEXT, v="bottom")

    # ── Row 11 RIGHT: Delivery Conditions value ──
    _c(ws, 11, 3, deliv_cond_value, color=GRAY_TEXT, v="bottom")

    # ── Rows 12–15 LEFT: Client address block (A12:B15) ──
    client_addr = meta_rows[3][1] if len(meta_rows) > 3 else ""
    _m(ws, 12, 1, 15, 2)
    _c(ws, 12, 1, client_addr, color=GRAY_TEXT, v="top", wrap=True)

    # ── Row 12 RIGHT: Delivery Time label (C12) ──
    deliv_time_label = meta_rows[4][0] if len(meta_rows) > 4 else "Delivery Time (Tiempo de Entrega):"
    deliv_time_value = meta_rows[4][1] if len(meta_rows) > 4 else ""
    _c(ws, 12, 3, deliv_time_label, size=11, bold=True, color=DARK_TEXT, v="bottom")

    # ── Row 13 RIGHT: Delivery Time value (C13:E13) ──
    _m(ws, 13, 3, 13, 5)
    _c(ws, 13, 3, deliv_time_value, color=GRAY_TEXT, v="bottom")

    # ── Row 14 RIGHT: Payment Terms label (C14) ──
    payment_label = meta_rows[5][0] if len(meta_rows) > 5 else "Payment Type (Tipo de Pago):"
    payment_value = meta_rows[5][1] if len(meta_rows) > 5 else ""
    _c(ws, 14, 3, payment_label, size=11, bold=True, color=DARK_TEXT, v="bottom")

    # ── Row 15 RIGHT: Payment Terms value (C15) ──
    _c(ws, 15, 3, payment_value, color=GRAY_TEXT, v="bottom")

    # ── Logo ──
    _add_logo(ws, logo_bytes)

    return 17


# ── Table header row ──────────────────────────────────────────────────────────

def _table_header(ws, row, accent, border_top=None, border_bot=None):
    """Styled header row: bold accent text, medium top+bottom borders in accent color."""
    ws.row_dimensions[row].height = 30.0
    bt = border_top or accent
    bb = border_bot or accent
    top_side = Side(border_style="medium", color=bt)
    bot_side = Side(border_style="medium", color=bb)
    tb = Border(top=top_side, bottom=bot_side)
    headers = [
        (1, "#"),
        (2, "Description\n(Descripción)"),
        (3, "Qty.\n(Cant.)"),
        (4, "Unit\n(Unidad)"),
        (5, "Unit Price\n(Valor Unitario)"),
        (6, "Total Price\n(Valor Total)"),
    ]
    for col, text in headers:
        _c(ws, row, col, text,
           size=11, bold=True, color=accent,
           h="center", wrap=True, v="center",
           border=tb)


# ── Item rows ─────────────────────────────────────────────────────────────────

def _items(ws, items_list, start_row, item_fill=None, item_alt=None):
    """
    Write item rows. ALL rows get light-green fill (EEF7E3) — no alternating.
    Returns the next empty row number.
    """
    r = start_row
    _base = item_fill or "FFEEF7E3"
    for i, item in enumerate(items_list):
        ws.row_dimensions[r].height = 73.5
        # Alternating: odd rows (i=0,2,4…) use item_fill, even rows use item_alt (or same)
        row_fill = _base if (item_alt is None or i % 2 == 0) else item_alt

        _c(ws, r, 1, item.get("item_number", i + 1),
           h="center", v="center", fill=row_fill)

        _c(ws, r, 2, item.get("description", ""),
           bold=True, h="center", wrap=True, v="center", fill=row_fill)

        _c(ws, r, 3, item.get("qty", 0),
           color=GRAY_TEXT, h="center", v="center",
           fill=row_fill, num_format="#,##0.##")

        _c(ws, r, 4, item.get("unit", ""),
           bold=True, color=GRAY_TEXT, h="center", v="center", fill=row_fill)

        price = item.get("unit_price") or 0
        _c(ws, r, 5, price,
           color=GRAY_TEXT, h="center", v="center",
           fill=row_fill, num_format="#,##0.00")

        total = round(price * (item.get("qty") or 0), 2)
        _c(ws, r, 6, total,
           bold=True, color=GRAY_TEXT, h="right", v="center",
           fill=row_fill, num_format="#,##0.00")
        r += 1
    return r


# ── Totals block ──────────────────────────────────────────────────────────────

def _totals(ws, notes_row, subtotal, freight, accent, sep_border=None, notes_text=""):
    """
    Write Notes + Subtotal / Shipping / Grand Total section.
    A thin accent-colored top border across all cols separates items from totals.
    """
    thin = _border_top(style="thin", color=sep_border or accent)

    # ── Notes row with separator border ──
    ws.row_dimensions[notes_row].height = 24.0
    _m(ws, notes_row, 1, notes_row, 3)
    _c(ws, notes_row, 1, "Notes (Notas):", bold=True, color=GRAY_LIGHT,
       border=thin, v="bottom")
    for col in [2, 3, 4]:
        ws.cell(row=notes_row, column=col).border = thin
    _c(ws, notes_row, 5, "Subtotal",
       color=GRAY_TEXT, h="right", border=thin, v="bottom")
    _c(ws, notes_row, 6, subtotal,
       bold=True, border=thin, v="bottom", num_format="#,##0.00")

    # ── Notes text (row below) ──
    r = notes_row + 1
    ws.row_dimensions[r].height = 40.5 if notes_text else 19.5
    if notes_text:
        _m(ws, r, 1, r, 3)
        _c(ws, r, 1, notes_text, size=9, color=DARK_TEXT, wrap=True, v="top")

    # ── Optional freight ──
    if freight:
        _c(ws, r, 5, "Shipping (Flete)", color=GRAY_TEXT, h="right", v="bottom")
        _c(ws, r, 6, freight, bold=True, color=GRAY_TEXT,
           v="bottom", num_format="#,##0.00")
        r += 1

    # ── Grand total: large, accent, E:F merged ──
    grand = subtotal + (freight or 0)
    ws.row_dimensions[r].height = 40.5
    _m(ws, r, 5, r, 6)
    _c(ws, r, 5, grand, size=20, bold=True, color=accent,
       h="right", v="bottom", num_format="#,##0.00")

    return r + 1


# ── PUBLIC FUNCTIONS ──────────────────────────────────────────────────────────

def generate_quote(db, deal_id: int, freight: float = None,
                   notes: str = "") -> str:
    """
    Generate a Quote (Cotización) Excel file matching the SADACO template.
    Accent color: dark green #38761D.
    Returns the local file path.
    """
    deal = db.get_deal_by_id(deal_id)
    if not deal:
        raise ValueError(f"Deal ID {deal_id} not found.")

    items_list = [dict(i) for i in db.get_deal_items(deal_id)]
    ref        = deal["reference"]


    wb = Workbook()
    ws = wb.active
    ws.title = "Quote"

    client_addr = "\n".join(filter(None, [
        (deal["client_addr1"] or "") if "client_addr1" in deal.keys() else "",
        (deal["client_addr2"] or "") if "client_addr2" in deal.keys() else "",
    ]))
    meta = [
        ("Client Ref. (Ref. Cliente):",                 deal["client_ref"] or ""),
        ("Delivery Conditions (Condición de Entrega):", f"{deal['incoterm'] or ''} {deal['port_location'] or ''}".strip()),
        ("", deal["client_name"] or ""),
        ("", client_addr),
        ("Delivery Time (Tiempo de Entrega):",          deal["delivery_time"] or ""),
        ("Payment Type (Tipo de Pago):",                deal["payment_terms"] or ""),
    ]

    yy = datetime.now().strftime("%y")
    doc_title  = f"Quote (Cotización): {ref}/{yy}"
    logo_bytes = db.get_asset("logo")
    dc = DOC_COLORS["quote"]
    table_start = _header(ws, deal["seller_entity"],
                          doc_title, ref, dc["accent"], meta, logo_bytes, dc)
    _table_header(ws, table_start, dc["accent"], dc["border_top"], dc["border_bot"])
    next_row = _items(ws, items_list, table_start + 1, dc["item_fill"], dc["item_alt"])

    subtotal = sum((i.get("unit_price") or 0) * (i.get("qty") or 0)
                   for i in items_list)
    _totals(ws, next_row, subtotal, freight, dc["accent"], dc["sep_border"], notes)

    os.makedirs(EXPORT_DIR, exist_ok=True)
    today    = datetime.now().strftime("%Y-%m-%d")
    filename = f"QUOTE_{ref}_{today}.xlsx"
    filepath = os.path.join(EXPORT_DIR, filename)
    wb.save(filepath)
    print(f"✅ Quote generated: {filename}")
    return filepath


def generate_purchase_order(db, deal_id: int, supplier_quote_id: int,
                             freight: float = None, notes: str = "") -> str:
    """
    Generate a Purchase Order Excel file matching the SADACO template.
    Accent color: orange #FF9900.
    Returns the local file path.
    """
    deal = db.get_deal_by_id(deal_id)
    if not deal:
        raise ValueError(f"Deal ID {deal_id} not found.")

    items      = db.get_deal_items(deal_id)
    qi_map     = {qi["deal_item_id"]: dict(qi)
                  for qi in db.get_quote_items(supplier_quote_id)}
    quotes     = db.get_supplier_quotes(deal_id)
    quote      = next((dict(q) for q in quotes if q["id"] == supplier_quote_id), {})
    supplier   = db.get_supplier_by_id(quote.get("supplier_id")) \
                 if quote.get("supplier_id") else None
    sup_name   = (supplier["company_name"] if supplier
                  else quote.get("supplier_name", "")) or ""

    ref    = deal["reference"]


    wb = Workbook()
    ws = wb.active
    ws.title = "Purchase Order"

    meta = [
        ("Supplier's Quote # (Ref.):",   quote.get("supplier_ref", "") or ""),
        ("Delivery Conditions:",         f"{quote.get('incoterm','') or ''} {quote.get('location','') or ''}".strip()),
        ("", sup_name),
        ("", ""),
        ("Est. Delivery Time:",          f"{quote.get('lead_time_days','') or ''} days"),
        ("Payment Type (Tipo de Pago):", quote.get("payment_terms") or deal["payment_terms"] or ""),
    ]

    yy = datetime.now().strftime("%y")
    doc_title  = f"P.O. (O.C.): {ref}/{yy}"
    logo_bytes = db.get_asset("logo")
    dc = DOC_COLORS["po"]
    table_start = _header(ws, deal["seller_entity"],
                          doc_title, ref, dc["accent"], meta, logo_bytes, dc)
    _table_header(ws, table_start, dc["accent"], dc["border_top"], dc["border_bot"])

    items_list = []
    for item in items:
        d  = dict(item)
        qi = qi_map.get(d["id"], {})
        items_list.append({
            "item_number": d["item_number"],
            "description": d["description"],
            "qty":         d["qty"],
            "unit":        d["unit"],
            "unit_price":  qi.get("unit_price") or d.get("unit_cost") or 0,
        })

    next_row = _items(ws, items_list, table_start + 1, dc["item_fill"], dc["item_alt"])
    subtotal = sum((i.get("unit_price") or 0) * (i.get("qty") or 0)
                   for i in items_list)
    _totals(ws, next_row, subtotal, freight, dc["accent"], dc["sep_border"], notes)

    os.makedirs(EXPORT_DIR, exist_ok=True)
    today    = datetime.now().strftime("%Y-%m-%d")
    safe_sup = sup_name.replace(" ", "_")[:20]
    filename = f"PO_{ref}_{safe_sup}_{today}.xlsx"
    filepath = os.path.join(EXPORT_DIR, filename)
    wb.save(filepath)
    print(f"✅ Purchase Order generated: {filename}")
    return filepath


def generate_invoice(db, deal_id: int, invoice_number: str = None,
                     freight: float = None, notes: str = "") -> str:
    """
    Generate a commercial Invoice Excel file matching the SADACO template.
    Accent color: blue #1155CC. Includes bank payment instructions block.
    Returns the local file path.
    """
    from modules.config import SELLER_ENTITIES

    deal = db.get_deal_by_id(deal_id)
    if not deal:
        raise ValueError(f"Deal ID {deal_id} not found.")

    items_list  = [dict(i) for i in db.get_deal_items(deal_id)]
    currency    = deal["currency"] or "USD"
    ref         = deal["reference"]
    inv_ref     = invoice_number or ref
    inv_title   = f"Invoice (Factura): {inv_ref}"

    entity_info = SELLER_ENTITIES.get(deal["seller_entity"], {})
    bank        = entity_info.get("bank_accounts", {}).get(currency, {})

    wb = Workbook()
    ws = wb.active
    ws.title = "Invoice"

    inv_client_addr = "\n".join(filter(None, [
        (deal["client_addr1"] or "") if "client_addr1" in deal.keys() else "",
        (deal["client_addr2"] or "") if "client_addr2" in deal.keys() else "",
    ]))
    meta = [
        ("Client Ref. (Ref. Cliente):",                 deal["client_ref"] or ""),
        ("Delivery Conditions:",                         f"{deal['incoterm'] or ''} {deal['port_location'] or ''}".strip()),
        ("", deal["client_name"] or ""),
        ("", inv_client_addr),
        ("Delivery Time:",                               deal["delivery_time"] or ""),
        ("Payment Type (Tipo de Pago):",                deal["payment_terms"] or ""),
    ]

    yy = datetime.now().strftime("%y")
    inv_title_with_year = f"{inv_title}/{yy}"
    logo_bytes = db.get_asset("logo")
    dc = DOC_COLORS["invoice"]
    table_start = _header(ws, deal["seller_entity"],
                          inv_title_with_year, inv_ref, dc["accent"], meta, logo_bytes, dc)
    _table_header(ws, table_start, dc["accent"], dc["border_top"], dc["border_bot"])
    next_row = _items(ws, items_list, table_start + 1, dc["item_fill"], dc["item_alt"])

    subtotal = sum((i.get("unit_price") or 0) * (i.get("qty") or 0)
                   for i in items_list)
    thin = _border_top(style="thin", color=dc["sep_border"])

    # ── Bank instructions header row ──
    r = next_row
    ws.row_dimensions[r].height = 24.0
    _m(ws, r, 1, r, 2)
    _c(ws, r, 1, "Bank Instructions (Instrucciones Bancarias):",
       bold=True, color=GRAY_TEXT, border=thin)
    ws.cell(row=r, column=2).border = thin
    _c(ws, r, 3, currency, bold=True, color=GRAY_TEXT, border=thin)
    ws.cell(row=r, column=4).border = thin
    _c(ws, r, 5, "Subtotal", color=GRAY_TEXT, h="right", border=thin, v="bottom")
    _c(ws, r, 6, subtotal, bold=True, border=thin, v="bottom", num_format="#,##0.00")

    # ── Bank detail text block (rows r+1 to r+3, cols A:C) ──
    r2 = r + 1
    ws.row_dimensions[r2].height = 70.0
    _m(ws, r2, 1, r2 + 2, 3)
    bank_text = (
        f"Beneficiary: {bank.get('beneficiary', '')}\n"
        f"Bank: {bank.get('bank', '')}\n"
        f"SWIFT: {bank.get('swift', '')}\n"
        f"Account: {bank.get('account', '')}"
    )
    bc = ws.cell(row=r2, column=1, value=bank_text)
    bc.font      = Font(name=FONT_NAME, size=10, color=DARK_TEXT)
    bc.alignment = Alignment(wrap_text=True, vertical="top")
    bc.border    = NO_BORDER

    # ── Freight + grand total (right side) ──
    rr = r + 1
    if freight:
        ws.row_dimensions[rr].height = 19.5
        _c(ws, rr, 5, "Shipping (Flete)", color=GRAY_TEXT, h="right", v="bottom")
        _c(ws, rr, 6, freight, bold=True, color=GRAY_TEXT,
           v="bottom", num_format="#,##0.00")
        rr += 1

    grand = subtotal + (freight or 0)
    ws.row_dimensions[rr].height = 40.5
    _m(ws, rr, 5, rr, 6)
    _c(ws, rr, 5, grand, size=20, bold=True, color=dc["accent"],
       h="right", v="bottom", num_format="#,##0.00")

    # ── Optional notes ──
    if notes:
        rn = r2 + 3
        ws.row_dimensions[rn].height = 30.0
        _m(ws, rn, 1, rn, 4)
        _c(ws, rn, 1, notes, size=9, color=DARK_TEXT, wrap=True, v="top")

    os.makedirs(EXPORT_DIR, exist_ok=True)
    today    = datetime.now().strftime("%Y-%m-%d")
    filename = f"INVOICE_{ref}_{today}.xlsx"
    filepath = os.path.join(EXPORT_DIR, filename)
    wb.save(filepath)

    # Record invoiced quantities in DB so delivery notes can track stock
    # Store the bare reference (e.g. "54-0001/26") — normalized in DB method
    db.record_invoiced_items(deal_id, f"{inv_ref}/{yy}")

    print(f"✅ Invoice generated: {filename}")
    return filepath
