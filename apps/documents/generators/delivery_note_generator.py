# =============================================================================
# delivery_note_generator.py — Delivery Note (Nota de Entrega) workflow
#
# Layout matches the SADACO Delivery Note PDF template:
#   - Gray top bar (row 1), logo col F rows 2-5
#   - Company name 20pt gray, address gray
#   - Title: "Delivery Note (Nota de Entrega): {ref}" 20pt bold gray
#   - Date right (F7:F8)
#   - Left block: Company label → client name → client address (rows 10-15)
#   - Right block: Client Ref (C8) → Receiver box with gray fill (C10:F15)
#   - Table: # | Description | Qty. | Unit  (NO price columns)
#   - Item rows: alternating gray/white
#   - Footer: thin gray separator, Notes left, Name/Signature/Date lines right
#
# COLOR SCHEME: neutral gray — no accent color
#   Top bar:      #CCCCCC
#   Header text:  #666666 (gray)
#   Table border: #999999
#   Item odd row: #F3F3F3
#   Receiver box: #DDDDDD
#
# WORKFLOW FUNCTIONS (for Colab notebook):
#   show_invoice_delivery_status(db, deal_id)  → print remaining quantities
#   select_items_for_delivery(db, deal_id, invoice_ref, selections)
#   generate_delivery_note(db, delivery_note_id)  → xlsx file path
# =============================================================================

import os
from datetime import datetime
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.drawing.image import Image as XLImage

def _export_dir():
    d = os.path.join(os.path.dirname(__file__), "..", "data", "exports")
    os.makedirs(d, exist_ok=True)
    return os.path.abspath(d)

EXPORT_DIR = _export_dir()
ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")

# Gray color scheme
GRAY_ACCENT  = "FF999999"   # title, table header text + border
GRAY_BAR     = "FFCCCCCC"   # top bar fill
GRAY_TEXT    = "FF666666"   # body text
GRAY_LIGHT   = "FF999999"   # light labels
DARK_TEXT    = "FF434343"   # bold labels
BLACK        = "FF000000"
ITEM_ODD     = "FFF3F3F3"   # alternating row fill
RECEIVER_BOX = "FFDDDDDD"   # receiver signature box fill

FONT_NAME = "Roboto"
NO_BORDER = Border()


# ── Low-level helpers (mirror doc_generator) ─────────────────────────────────

def _f(size=10, bold=False, color=BLACK):
    return Font(name=FONT_NAME, size=size, bold=bold, color=color)

def _a(h="left", wrap=False, v="bottom"):
    return Alignment(horizontal=h, vertical=v, wrap_text=wrap)

def _fill(hex_color):
    return PatternFill("solid", fgColor=hex_color)

def _no_fill():
    return PatternFill(fill_type=None)

def _border_top(style="thin", color=GRAY_ACCENT):
    s = Side(border_style=style, color=color)
    return Border(top=s)

def _border_tb(style="medium", color=GRAY_ACCENT):
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
    """Same positioning as other docs: col F, rows 2-5, centered."""
    if not logo_bytes:
        return
    try:
        import io, numpy as np
        from PIL import Image as PILImage
        from scipy.ndimage import label
        from openpyxl.drawing.spreadsheet_drawing import OneCellAnchor, AnchorMarker
        from openpyxl.drawing.xdr import XDRPositiveSize2D

        src = PILImage.open(io.BytesIO(logo_bytes)).convert("RGB")
        arr = np.array(src)
        exact_black = (arr[:,:,0] == 0) & (arr[:,:,1] == 0) & (arr[:,:,2] == 0)
        labeled, _ = label(exact_black)
        corner_label = labeled[0, 0]
        bg_mask = (labeled == corner_label) if corner_label != 0 else exact_black
        rgba = np.zeros((arr.shape[0], arr.shape[1], 4), dtype=np.uint8)
        rgba[:,:,:3] = arr
        rgba[:,:,3] = 255
        rgba[bg_mask, 3] = 0
        final = PILImage.fromarray(rgba, "RGBA").resize((79, 79), PILImage.LANCZOS)

        buf = io.BytesIO()
        final.save(buf, format="PNG")
        buf.seek(0)

        img    = XLImage(buf)
        size   = XDRPositiveSize2D(cx=752475, cy=752475)
        marker = AnchorMarker(col=5, colOff=157638, row=1, rowOff=19050)
        img.anchor = OneCellAnchor(_from=marker, ext=size)
        ws.add_image(img)
    except Exception:
        pass


# ── Document header (rows 1-16) ───────────────────────────────────────────────

def _header(ws, seller_entity, doc_title, doc_ref, meta_rows, logo_bytes=None):
    """
    Builds the delivery note header.
    Identical structure to other docs but gray color scheme.
    meta_rows = [
        (client_ref_label, client_ref_value),   # C8 / C9:F9
        (delivery_cond_label, delivery_cond_val),# C10 / C11
        ("", client_name),                       # A11
        ("", client_addr),                       # A12:B15
        (delivery_time_label, delivery_time_val),# C12 / C13
        (payment_label, payment_val),            # C14 / C15
    ]
    """
    from modules.config import SELLER_ENTITIES
    entity = SELLER_ENTITIES.get(seller_entity, {})

    ws.sheet_view.showGridLines = False

    # Column widths — same as other docs
    ws.column_dimensions["A"].width = 2.63
    ws.column_dimensions["B"].width = 47.38
    ws.column_dimensions["C"].width = 9.9
    ws.column_dimensions["D"].width = 11.7
    ws.column_dimensions["E"].width = 18.4
    ws.column_dimensions["F"].width = 15.3

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

    # ── Row 1: gray top bar ──
    _m(ws, 1, 1, 1, 6)
    ws.cell(row=1, column=1).fill = _fill(GRAY_BAR)

    # ── Rows 2-3: Company name (A2:F3 merged) ──
    _m(ws, 2, 1, 3, 6)
    _c(ws, 2, 1, seller_entity, size=20, color=GRAY_TEXT, v="bottom")

    # ── Rows 4-5: Address ──
    _m(ws, 4, 1, 4, 2); _m(ws, 4, 3, 4, 6)
    _c(ws, 4, 1, entity.get("address_line1", ""), color=GRAY_TEXT, v="bottom")
    _m(ws, 5, 1, 5, 2); _m(ws, 5, 3, 5, 6)
    _c(ws, 5, 1, entity.get("address_line2", ""), color=GRAY_TEXT, v="top")

    # ── Row 6: spacer ──
    _m(ws, 6, 1, 6, 6)

    # ── Row 7: label only "Delivery Note (Nota de Entrega):" at 17pt, ref is in A8 ──
    _m(ws, 7, 1, 7, 4)
    _c(ws, 7, 1, "Delivery Note (Nota de Entrega):", size=17, bold=True, color=GRAY_ACCENT, v="bottom")
    _c(ws, 7, 5, "Date (Fecha):", bold=True, h="right", v="top")

    # ── Date value: F7:F8 merged ──
    _m(ws, 7, 6, 8, 6)
    date_str = datetime.now().strftime("%d de %B, %Y")
    _c(ws, 7, 6, date_str, size=9, bold=True, color=GRAY_LIGHT, v="top", wrap=True)

    # ── Rows 8-9: Doc ref (A8:B9) ──
    _m(ws, 8, 1, 9, 2)
    _c(ws, 8, 1, doc_ref, size=17, bold=True, color=GRAY_ACCENT, v="top")

    # ── C8: Client Ref label ──
    client_ref_label = meta_rows[0][0] if len(meta_rows) > 0 else "Client Ref. (Ref. Cliente):"
    client_ref_value = meta_rows[0][1] if len(meta_rows) > 0 else ""
    _c(ws, 8, 3, client_ref_label, size=11, bold=True, color=DARK_TEXT, v="bottom")
    _m(ws, 9, 3, 9, 6)
    _c(ws, 9, 3, client_ref_value, color=GRAY_TEXT, v="bottom")

    # ── Row 10 LEFT: "Company:" label ──
    _m(ws, 10, 1, 10, 2)
    _c(ws, 10, 1, "Company (Compañía):", size=11, bold=True, color=DARK_TEXT, v="bottom")

    # ── Row 10 RIGHT: "Receiver (Recibido por):" label — spans C10:F10 ──
    _m(ws, 10, 3, 10, 6)
    _c(ws, 10, 3, "Receiver (Recibido por):", size=11, bold=True, color=DARK_TEXT, v="bottom")

    # ── Row 11 LEFT: Client name ──
    client_name = meta_rows[2][1] if len(meta_rows) > 2 else ""
    _c(ws, 11, 1, client_name, bold=True, color=GRAY_TEXT, v="bottom")

    # ── Rows 11-15 RIGHT: Receiver signature box (gray fill) ──
    _m(ws, 11, 3, 15, 6)
    ws.cell(row=11, column=3).fill = _fill(RECEIVER_BOX)

    # ── Rows 12-15 LEFT: Client address block ──
    client_addr = meta_rows[3][1] if len(meta_rows) > 3 else ""
    _m(ws, 12, 1, 15, 2)
    _c(ws, 12, 1, client_addr, color=GRAY_TEXT, v="top", wrap=True)

    # ── Logo ──
    _add_logo(ws, logo_bytes)

    return 17


# ── Table header (4 columns — no price) ─────────────────────────────────────

def _table_header(ws, row):
    ws.row_dimensions[row].height = 30.0
    tb = _border_tb(style="medium", color=GRAY_ACCENT)
    headers = [
        (1, "#"),
        (2, "Description\n(Descripción)"),
        (3, "Qty.\n(Cant.)"),
        (4, "Unit\n(Unidad)"),
    ]
    # Merge E:F for Unit column so it's visible
    _m(ws, row, 4, row, 6)
    for col, text in headers:
        _c(ws, row, col, text,
           size=11, bold=True, color=GRAY_ACCENT,
           h="center", wrap=True, v="center",
           border=tb)
    # Apply border to merged E:F cells too
    for col in [5, 6]:
        ws.cell(row=row, column=col).border = tb


# ── Item rows ─────────────────────────────────────────────────────────────────

def _items(ws, items_list, start_row):
    r = start_row
    for i, item in enumerate(items_list):
        ws.row_dimensions[r].height = 73.5
        row_fill = ITEM_ODD if i % 2 == 0 else None

        _c(ws, r, 1, item.get("item_number", i + 1),
           h="center", v="center", fill=row_fill)
        _c(ws, r, 2, item.get("description", ""),
           bold=True, h="center", wrap=True, v="center", fill=row_fill)
        _c(ws, r, 3, item.get("qty_delivered", 0),
           color=GRAY_TEXT, h="center", v="center",
           fill=row_fill, num_format="#,##0.##")

        # Unit spans D:F
        _m(ws, r, 4, r, 6)
        _c(ws, r, 4, item.get("unit", ""),
           bold=True, color=GRAY_TEXT, h="center", v="center", fill=row_fill)
        r += 1
    return r


# ── Footer ────────────────────────────────────────────────────────────────────

def _footer(ws, notes_row, notes_text=""):
    """
    Notes (left) + Name / Signature / Date signature lines (right).
    Separated from items by a thin gray line.
    """
    thin = _border_top(style="thin", color=GRAY_ACCENT)

    # ── Separator + Notes label ──
    ws.row_dimensions[notes_row].height = 24.0
    _m(ws, notes_row, 1, notes_row, 3)
    _c(ws, notes_row, 1, "Notes (Notas):", bold=True, color=GRAY_LIGHT,
       border=thin, v="bottom")
    for col in [2, 3, 4, 5, 6]:
        ws.cell(row=notes_row, column=col).border = thin

    # ── Notes text ──
    r = notes_row + 1
    if notes_text:
        ws.row_dimensions[r].height = 30.0
        _m(ws, r, 1, r, 3)
        _c(ws, r, 1, notes_text, size=9, color=DARK_TEXT, wrap=True, v="top")
    else:
        ws.row_dimensions[r].height = 19.5

    # ── Signature lines (right side D:F) ──
    sig_rows = [
        (r,     "Name: ______________________________________"),
        (r + 2, "Signature: __________________________________"),
        (r + 3, "Date: _______________________________________"),
    ]
    for sig_r, text in sig_rows:
        ws.row_dimensions[sig_r].height = 19.5
        _m(ws, sig_r, 4, sig_r, 6)
        _c(ws, sig_r, 4, text, bold=True, color=DARK_TEXT, v="bottom")


# ── PUBLIC: show delivery status ─────────────────────────────────────────────

def show_invoice_delivery_status(db, deal_id: int, invoice_ref: str = None):
    """
    Print a table showing, for each item on an invoice:
      - Total qty invoiced
      - Qty already delivered across all previous delivery notes
      - Qty remaining to deliver

    Args:
        db          : Database instance
        deal_id     : The deal ID
        invoice_ref : e.g. "54-0001/26" — if None, lists all invoices for the deal

    Usage in Colab:
        show_invoice_delivery_status(db, deal_id=3)
        show_invoice_delivery_status(db, deal_id=3, invoice_ref="54-0001/26")
    """
    if invoice_ref is None:
        invoices = db.get_invoices_for_deal(deal_id)
        if not invoices:
            print("⚠️  No invoices found for this deal. Generate an invoice first.")
            return
        print(f"\n  Invoices for deal {deal_id}:")
        print(f"  {'Invoice Ref':<25} {'Items':>6} {'Total Qty':>10}  Created")
        print("  " + "─" * 60)
        for inv in invoices:
            print(f"  {inv['invoice_ref']:<25} {inv['item_count']:>6} "
                  f"{inv['total_qty']:>10.1f}  {str(inv['created_at'])[:19]}")
        print(f"\n  ↑ Copy one of these refs into INVOICE_REF above.")
        return

    invoice_ref = db._normalize_invoice_ref(invoice_ref)
    rows = db.get_delivery_status(deal_id, invoice_ref)
    if not rows:
        print(f"⚠️  No invoiced items found for {invoice_ref}.")
        return

    print(f"\n  Delivery status — Invoice: {invoice_ref}")
    print(f"  {'ID':<6} {'#':<4} {'Description':<38} {'Invoiced':>10} {'Delivered':>10} {'Remaining':>10}")
    print("  " + "─" * 82)

    has_remaining = False
    for row in rows:
        desc = str(row["description"]).replace("\n", " ")[:38]
        remaining = row['qty_remaining']
        flag = " ◀ deliverable" if remaining > 0 else ""
        if remaining > 0:
            has_remaining = True
        print(f"  {row['deal_item_id']:<6} {row['item_number']:<4} {desc:<38} "
              f"{row['qty_invoiced']:>10.2f} "
              f"{row['qty_delivered']:>10.2f} "
              f"{row['qty_remaining']:>10.2f}{flag}")

    # Print a ready-to-copy SELECTIONS dict using the real IDs
    print()
    if has_remaining:
        print("  ── Copy this into the SELECTIONS cell and fill in your quantities ──")
        print()
        print("  SELECTIONS = {")
        for row in rows:
            if row['qty_remaining'] > 0:
                desc_short = str(row["description"]).replace("\n", " ")[:35]
                print(f"      {row['deal_item_id']}: 0,  # {desc_short} (max: {row['qty_remaining']:.2f})")
        print("  }")
    else:
        print("  ✅ All items fully delivered — nothing remaining.")
    print()
    return rows


# ── PUBLIC: create delivery note from selections ──────────────────────────────

def create_delivery_note(db, deal_id: int, invoice_ref: str,
                          selections: dict,
                          notes: str = "",
                          receiver_name: str = "") -> tuple:
    """
    Create a delivery note record and return (delivery_note_id, reference).

    Args:
        db          : Database instance
        deal_id     : The deal ID
        invoice_ref : e.g. "54-0001/26"
        selections  : dict of {deal_item_id: qty_to_deliver}
                      e.g. {3: 5.0, 4: 10.0}
                      Pass 0 or omit an item to skip it.
        notes       : Optional notes text
        receiver_name : Pre-filled receiver name

    Returns:
        (delivery_note_id, reference)  e.g. (1, "54-0001/26-1")

    Raises:
        ValueError if qty exceeds remaining for any item.

    Usage in Colab:
        # First check status:
        show_invoice_delivery_status(db, deal_id, "54-0001/26")

        # Then create note with your selections:
        dn_id, ref = create_delivery_note(
            db, deal_id, "54-0001/26",
            selections={3: 5, 4: 10},
            notes="Entrega parcial — lote 1"
        )
    """
    # Normalize the invoice_ref in case user passed a full title string
    invoice_ref = db._normalize_invoice_ref(invoice_ref)
    items = [
        {"deal_item_id": item_id, "qty_delivered": qty}
        for item_id, qty in selections.items()
        if qty > 0
    ]
    if not items:
        raise ValueError("No items selected (all quantities are 0).")

    dn_id, ref = db.create_delivery_note(
        deal_id, invoice_ref, items, notes, receiver_name
    )
    print(f"✅ Delivery note created: {ref} (ID: {dn_id})")
    return dn_id, ref


# ── PUBLIC: interactive delivery note creation ───────────────────────────────

def create_delivery_note_interactive(db, deal_id: int, invoice_ref: str,
                                      notes: str = "", receiver_name: str = "") -> tuple:
    """
    Interactive version of create_delivery_note for Colab.
    Fetches available items from the DB and prompts for each quantity via input().
    No need to manually edit a SELECTIONS dict.

    Usage in Colab:
        dn_id, dn_ref = create_delivery_note_interactive(db, DEAL_ID, INVOICE_REF)
    """
    invoice_ref = db._normalize_invoice_ref(invoice_ref)
    rows = db.get_delivery_status(deal_id, invoice_ref)

    if not rows:
        print(f"⚠️  No invoiced items found for '{invoice_ref}'.")
        print("    Run show_invoice_delivery_status(db, DEAL_ID) to check available invoices.")
        return None, None

    deliverable = [r for r in rows if r['qty_remaining'] > 0]
    if not deliverable:
        print("✅ All items on this invoice have already been fully delivered.")
        return None, None

    print(f"\n  Creating delivery note for invoice: {invoice_ref}")
    print(f"  Enter quantity to deliver for each item (0 = skip):\n")

    selections = {}
    for row in deliverable:
        desc = str(row['description']).replace('\n', ' / ')[:60]
        max_qty = row['qty_remaining']
        while True:
            try:
                raw = input(f"  [{row['deal_item_id']}] {desc}\n"
                            f"      Max remaining: {max_qty:.2f} → Qty to deliver: ").strip()
                qty = float(raw) if raw else 0.0
                if qty < 0:
                    print("      ⚠️  Enter a positive number or 0 to skip.")
                    continue
                if qty > max_qty + 1e-9:
                    print(f"      ⚠️  Cannot exceed {max_qty:.2f}. Try again.")
                    continue
                selections[row['deal_item_id']] = qty
                break
            except ValueError:
                print("      ⚠️  Please enter a number.")

    chosen = {k: v for k, v in selections.items() if v > 0}
    if not chosen:
        print("\n  No quantities entered — delivery note not created.")
        return None, None

    print("\n  ── Summary ──────────────────────────────────────────────────")
    status_map = {r['deal_item_id']: r for r in rows}
    for item_id, qty in chosen.items():
        row = status_map[item_id]
        desc = str(row['description']).replace('\n', ' / ')[:50]
        print(f"  • [{item_id}] {desc}: {qty:.2f} {row['unit'].split(chr(10))[0]}")

    print()
    confirm = input("  Confirm? (yes / no): ").strip().lower()
    if confirm not in ('yes', 'y', 'si', 'sí'):
        print("  Cancelled.")
        return None, None

    dn_id, ref = db.create_delivery_note(
        deal_id, invoice_ref,
        [{"deal_item_id": k, "qty_delivered": v} for k, v in chosen.items()],
        notes, receiver_name
    )
    print(f"\n✅ Delivery note created: {ref}  (ID: {dn_id})")
    print("   Run the next cell to generate the Excel file.")
    return dn_id, ref


# ── PUBLIC: generate xlsx ─────────────────────────────────────────────────────

def generate_delivery_note(db, delivery_note_id: int, dm=None) -> str:
    """
    Generate a Delivery Note Excel file from a saved delivery note record.

    Args:
        db                 : Database instance
        delivery_note_id   : ID returned by create_delivery_note()
        dm                 : Optional DriveManager — if provided, auto-uploads to
                             the Delivery_Notes folder in Google Drive

    Returns:
        str: local file path of the generated .xlsx

    Usage in Colab:
        path = generate_delivery_note(db, dn_id)          # local only
        path = generate_delivery_note(db, dn_id, dm=dm)   # local + Drive upload
    """
    dn = db.get_delivery_note(delivery_note_id)
    if not dn:
        raise ValueError(f"Delivery note ID {delivery_note_id} not found.")

    dn_items   = db.get_delivery_note_items(delivery_note_id)
    logo_bytes = db.get_asset("logo")

    ref       = dn["reference"]          # e.g. "54-0001/26-1"
    doc_title = f"Delivery Note (Nota de Entrega): {ref}"

    # Build meta rows — same structure as other docs
    client_addr = "\n".join(filter(None, [
        (dn["client_addr1"] or "") if "client_addr1" in dn.keys() else "",
        (dn["client_addr2"] or "") if "client_addr2" in dn.keys() else "",
    ]))
    meta = [
        ("Client Ref. (Ref. Cliente):",  dn["client_ref"] or ""),
        ("", ""),                         # no delivery conditions on delivery notes
        ("", dn["client_name"] or ""),
        ("", client_addr),
        ("", ""),
        ("", ""),
    ]

    wb = Workbook()
    ws = wb.active
    ws.title = "Delivery Note"

    table_start = _header(ws, dn["seller_entity"], doc_title, ref, meta, logo_bytes)
    _table_header(ws, table_start)

    items_list = [dict(row) for row in dn_items]
    next_row   = _items(ws, items_list, table_start + 1)
    _footer(ws, next_row, dn["notes"] or "")

    os.makedirs(EXPORT_DIR, exist_ok=True)
    today    = datetime.now().strftime("%Y-%m-%d")
    # Clean reference for use as filename (strip long prefixes, replace special chars)
    safe_ref = ref.replace("Invoice (Factura): ", "").replace("P.O. (O.C.): ", "")
    safe_ref = safe_ref.replace("/", "-").replace(" ", "_").replace(":", "")
    filename = f"DN_{safe_ref}_{today}.xlsx"
    filepath = os.path.join(EXPORT_DIR, filename)
    wb.save(filepath)
    print(f"✅ Delivery Note generated: {filename}")

    # Auto-upload to Google Drive if DriveManager is provided
    if dm is not None:
        try:
            url = dm.upload_document(db, dn["deal_id"], "DeliveryNote", filepath)
            print(f"☁️  Uploaded to Drive: {url}")
        except Exception as e:
            print(f"⚠️  Drive upload failed: {e}")

    return filepath
