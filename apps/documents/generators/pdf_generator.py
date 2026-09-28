# =============================================================================
# modules/pdf_generator.py — PDF generation for SADACO ERP documents
#
# Converts each document type to a pixel-faithful PDF using WeasyPrint.
# The HTML is built inline — no external template files needed.
# Colors, fonts, and layout match the existing xlsx SADACO templates exactly.
#
# Usage:
#   from modules.pdf_generator import generate_pdf
#   pdf_path = generate_pdf(doc_type, db, deal_id, **kwargs)
#
# Supported doc_type values: "quote", "po", "invoice", "delivery_note"
# =============================================================================

import os
import io
import base64
from datetime import datetime

# ── Color scheme (mirrors DOC_COLORS in doc_generator.py) ───────────────────
DOC_STYLES = {
    "quote": {
        "accent":     "#38761D",
        "header_bar": "#6AA84F",
        "item_fill":  "#EEF7E3",
        "item_alt":   None,          # no alternating — same fill every row
        "label":      "Quote (Cotización)",
    },
    "po": {
        "accent":     "#FF9900",
        "header_bar": "#FF9900",
        "item_fill":  "#F3F3F3",
        "item_alt":   "#FFFFFF",
        "label":      "P.O. (O.C.)",
    },
    "invoice": {
        "accent":     "#1155CC",
        "header_bar": "#3C78D8",
        "item_fill":  "#CFE2F3",
        "item_alt":   "#FFFFFF",
        "label":      "Invoice (Factura)",
    },
    "delivery_note": {
        "accent":     "#999999",
        "header_bar": "#CCCCCC",
        "item_fill":  "#F3F3F3",
        "item_alt":   "#FFFFFF",
        "label":      "Delivery Note (Nota de Entrega)",
    },
}

FONT_STACK = "'Roboto', 'DejaVu Sans', Arial, sans-serif"


def _logo_b64(logo_bytes: bytes) -> str | None:
    """Convert raw PNG logo bytes to a base64 data URI for embedding in HTML."""
    if not logo_bytes:
        return None
    try:
        import numpy as np
        from PIL import Image as PILImage
        from scipy.ndimage import label as scipy_label

        src  = PILImage.open(io.BytesIO(logo_bytes)).convert("RGB")
        arr  = np.array(src)

        # Remove black background (same flood-fill logic as xlsx generator)
        exact_black  = (arr[:, :, 0] == 0) & (arr[:, :, 1] == 0) & (arr[:, :, 2] == 0)
        labeled, _   = scipy_label(exact_black)
        corner_label = labeled[0, 0]
        bg_mask      = (labeled == corner_label) if corner_label != 0 else exact_black

        rgba          = np.zeros((*arr.shape[:2], 4), dtype=np.uint8)
        rgba[:, :, :3] = arr
        rgba[:, :, 3]  = 255
        rgba[bg_mask, 3] = 0

        final = PILImage.fromarray(rgba, "RGBA").resize((80, 80), PILImage.LANCZOS)
        buf   = io.BytesIO()
        final.save(buf, format="PNG")
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return None


def _fmt_num(v, decimals=2) -> str:
    try:
        return f"{float(v or 0):,.{decimals}f}"
    except (TypeError, ValueError):
        return "0.00"


def _currency_footer(currency: str, exchange_rate: float) -> str:
    """Return an extra footer line when currency is not USD."""
    if currency and currency.upper() != "USD":
        return (
            f'<p style="font-size:9pt;color:#999;margin:4pt 0 0 0;text-align:right">'
            f'Currency: {currency} &nbsp;|&nbsp; '
            f'Exchange rate: 1 USD = {_fmt_num(exchange_rate, 4)} {currency}'
            f'</p>'
        )
    return ""


# ── Shared HTML header block ──────────────────────────────────────────────────

def _html_header(seller_entity: str, doc_title: str, doc_ref: str,
                 meta_rows: list, logo_b64: str | None,
                 accent: str, bar_color: str) -> str:
    """
    Returns the HTML for the top header section (company info, doc title, meta).
    meta_rows: list of (label, value) pairs — same structure as xlsx generator.
    """
    from modules.config import SELLER_ENTITIES
    entity = SELLER_ENTITIES.get(seller_entity, {})
    addr1  = entity.get("address_line1", "")
    addr2  = entity.get("address_line2", "")
    date_s = datetime.now().strftime("%d de %B, %Y")

    client_ref_lbl   = meta_rows[0][0] if len(meta_rows) > 0 else ""
    client_ref_val   = meta_rows[0][1] if len(meta_rows) > 0 else ""
    deliv_cond_lbl   = meta_rows[1][0] if len(meta_rows) > 1 else ""
    deliv_cond_val   = meta_rows[1][1] if len(meta_rows) > 1 else ""
    client_name      = meta_rows[2][1] if len(meta_rows) > 2 else ""
    client_addr      = meta_rows[3][1] if len(meta_rows) > 3 else ""
    deliv_time_lbl   = meta_rows[4][0] if len(meta_rows) > 4 else ""
    deliv_time_val   = meta_rows[4][1] if len(meta_rows) > 4 else ""
    payment_lbl      = meta_rows[5][0] if len(meta_rows) > 5 else ""
    payment_val      = meta_rows[5][1] if len(meta_rows) > 5 else ""

    logo_html = (
        f'<img src="{logo_b64}" style="width:70pt;height:70pt;object-fit:contain">'
        if logo_b64 else ""
    )
    client_addr_html = client_addr.replace("\n", "<br>") if client_addr else "—"

    return f"""
    <!-- Top accent bar -->
    <div style="background:{bar_color};height:8pt;margin-bottom:0"></div>

    <!-- Company + Logo row -->
    <table style="width:100%;border-collapse:collapse;margin-bottom:4pt">
      <tr>
        <td style="width:75%">
          <div style="font-size:18pt;font-weight:bold;color:{accent};padding-top:4pt">
            {seller_entity}
          </div>
          <div style="font-size:9pt;color:#666">{addr1}</div>
          <div style="font-size:9pt;color:#666;margin-bottom:4pt">{addr2}</div>
        </td>
        <td style="width:25%;text-align:right;vertical-align:top;padding-top:4pt">
          {logo_html}
        </td>
      </tr>
    </table>

    <!-- Doc title + Date -->
    <table style="width:100%;border-collapse:collapse;margin-bottom:2pt">
      <tr>
        <td style="width:70%">
          <div style="font-size:15pt;font-weight:bold;color:{accent}">{doc_title}</div>
        </td>
        <td style="width:30%;text-align:right;vertical-align:top">
          <div style="font-size:8pt;color:#999;font-weight:bold">Date (Fecha):</div>
          <div style="font-size:8pt;color:#999">{date_s}</div>
        </td>
      </tr>
    </table>

    <!-- Meta info grid -->
    <table style="width:100%;border-collapse:collapse;margin-bottom:8pt;font-size:8.5pt">
      <tr>
        <td style="width:48%;vertical-align:top;padding-right:8pt">
          <div style="color:#434343;font-weight:bold">Company (Compañía):</div>
          <div style="font-weight:bold;color:#666">{client_name or '—'}</div>
          <div style="color:#666">{client_addr_html}</div>
        </td>
        <td style="width:52%;vertical-align:top">
          <table style="width:100%;border-collapse:collapse">
            <tr>
              <td style="color:#434343;font-weight:bold;padding-bottom:2pt;width:45%">
                {client_ref_lbl}
              </td>
              <td style="color:#666;padding-bottom:2pt">{client_ref_val or '—'}</td>
            </tr>
            <tr>
              <td style="color:#434343;font-weight:bold;padding-bottom:2pt">
                {deliv_cond_lbl}
              </td>
              <td style="color:#666;padding-bottom:2pt">{deliv_cond_val or '—'}</td>
            </tr>
            <tr>
              <td style="color:#434343;font-weight:bold;padding-bottom:2pt">
                {deliv_time_lbl}
              </td>
              <td style="color:#666;padding-bottom:2pt">{deliv_time_val or '—'}</td>
            </tr>
            <tr>
              <td style="color:#434343;font-weight:bold">
                {payment_lbl}
              </td>
              <td style="color:#666">{payment_val or '—'}</td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
    """


# ── Items table ───────────────────────────────────────────────────────────────

def _html_items_table(items_list: list, accent: str,
                      item_fill: str, item_alt: str | None,
                      show_prices: bool = True) -> str:
    """Build the items table HTML (with or without price columns)."""
    if show_prices:
        headers = ["#", "Description (Descripción)", "Qty.", "Unit", "Unit Price", "Total Price"]
        widths  = ["4%", "46%", "8%", "10%", "16%", "16%"]
    else:
        headers = ["#", "Description (Descripción)", "Qty.", "Unit"]
        widths  = ["5%", "55%", "20%", "20%"]

    header_cells = "".join(
        f'<th style="text-align:center;padding:5pt 4pt;font-size:8.5pt;'
        f'border-top:2pt solid {accent};border-bottom:2pt solid {accent};'
        f'color:{accent};white-space:pre-line;width:{widths[i]}">{h}</th>'
        for i, h in enumerate(headers)
    )
    rows_html = ""
    for idx, item in enumerate(items_list):
        fill = item_fill if (item_alt is None or idx % 2 == 0) else item_alt
        price    = float(item.get("unit_price") or 0)
        qty      = float(item.get("qty") or 0)
        total    = price * qty
        desc     = item.get("description", "")
        part_no  = item.get("part_number") or ""
        brand    = item.get("brand") or ""
        desc_sub = " · ".join(filter(None, [part_no, brand]))

        desc_cell = (
            f'<div style="font-weight:bold">{desc}</div>'
            + (f'<div style="font-size:7.5pt;color:#888">{desc_sub}</div>' if desc_sub else "")
        )

        if show_prices:
            row_cells = f"""
              <td style="text-align:center;padding:4pt;color:#666;font-size:8.5pt">{item.get('item_number', idx+1)}</td>
              <td style="padding:4pt;font-size:8.5pt">{desc_cell}</td>
              <td style="text-align:center;padding:4pt;color:#666;font-size:8.5pt">{_fmt_num(qty, 4).rstrip('0').rstrip('.')}</td>
              <td style="text-align:center;padding:4pt;color:#666;font-size:8.5pt;font-weight:bold">{item.get('unit','')}</td>
              <td style="text-align:right;padding:4pt;color:#666;font-size:8.5pt">{_fmt_num(price)}</td>
              <td style="text-align:right;padding:4pt;font-weight:bold;font-size:8.5pt">{_fmt_num(total)}</td>
            """
        else:
            row_cells = f"""
              <td style="text-align:center;padding:4pt;color:#666;font-size:8.5pt">{item.get('item_number', idx+1)}</td>
              <td style="padding:4pt;font-size:8.5pt">{desc_cell}</td>
              <td style="text-align:center;padding:4pt;color:#666;font-size:8.5pt">{_fmt_num(qty, 4).rstrip('0').rstrip('.')}</td>
              <td style="text-align:center;padding:4pt;color:#666;font-size:8.5pt;font-weight:bold">{item.get('unit','')}</td>
            """
        rows_html += f'<tr style="background:{fill}">{row_cells}</tr>\n'

    return f"""
    <table style="width:100%;border-collapse:collapse;margin-bottom:4pt">
      <thead><tr>{header_cells}</tr></thead>
      <tbody>{rows_html}</tbody>
    </table>
    """


# ── Totals block ──────────────────────────────────────────────────────────────

def _html_totals(subtotal: float, freight: float | None,
                 accent: str, notes_text: str = "") -> str:
    grand     = subtotal + (freight or 0)
    freight_row = (
        f'<tr><td style="text-align:right;color:#666;padding:2pt 4pt;font-size:8.5pt">'
        f'Shipping (Flete)</td>'
        f'<td style="text-align:right;font-weight:bold;padding:2pt 4pt;font-size:8.5pt">'
        f'{_fmt_num(freight)}</td></tr>'
        if freight else ""
    )
    notes_html = (
        f'<div style="font-size:8pt;color:#434343;margin-top:4pt">'
        f'<span style="font-weight:bold;color:#999">Notes: </span>{notes_text}</div>'
        if notes_text else ""
    )
    return f"""
    <hr style="border:none;border-top:1pt solid {accent};margin:4pt 0">
    <table style="width:100%;border-collapse:collapse">
      <tr>
        <td style="width:60%;vertical-align:top">{notes_html}</td>
        <td style="width:40%">
          <table style="width:100%;border-collapse:collapse">
            <tr>
              <td style="text-align:right;color:#666;padding:2pt 4pt;font-size:8.5pt">Subtotal</td>
              <td style="text-align:right;font-weight:bold;padding:2pt 4pt;font-size:8.5pt">{_fmt_num(subtotal)}</td>
            </tr>
            {freight_row}
            <tr>
              <td colspan="2" style="text-align:right;padding-top:4pt">
                <span style="font-size:18pt;font-weight:bold;color:{accent}">{_fmt_num(grand)}</span>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
    """


# ── Full document HTML wrapper ────────────────────────────────────────────────

def _wrap_html(body: str) -> str:
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  @page {{
    size: A4;
    margin: 14mm 14mm 14mm 14mm;
  }}
  body {{
    font-family: {FONT_STACK};
    font-size: 9pt;
    color: #1a1a1a;
    margin: 0;
    padding: 0;
  }}
  table {{ border-collapse: collapse; }}
  th, td {{ padding: 2pt 4pt; vertical-align: top; }}
</style>
</head>
<body>{body}</body>
</html>"""


# ── PUBLIC: generate PDF ──────────────────────────────────────────────────────

def generate_pdf(doc_type: str, db, deal_id: int,
                 supplier_quote_id: int = None,
                 freight: float = None,
                 notes: str = "",
                 invoice_number: str = None,
                 delivery_note_id: int = None) -> str:
    """
    Generate a PDF for the given doc_type and deal.
    Mirrors the xlsx generator functions in doc_generator.py.

    Args:
        doc_type          : "quote" | "po" | "invoice" | "delivery_note"
        db                : Database instance
        deal_id           : The deal to generate for
        supplier_quote_id : Required for doc_type="po"
        freight           : Optional freight cost
        notes             : Optional notes text
        invoice_number    : Optional custom invoice ref (invoice only)
        delivery_note_id  : Required for doc_type="delivery_note"

    Returns:
        Absolute path to the generated PDF file.
    """
    try:
        import weasyprint
    except ImportError:
        raise RuntimeError(
            "WeasyPrint is not installed.\n"
            "Run: !pip install weasyprint\n"
            "On Colab also run: !apt-get install -y libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b"
        )

    style = DOC_STYLES.get(doc_type)
    if not style:
        raise ValueError(f"Unknown doc_type '{doc_type}'. Use: quote, po, invoice, delivery_note")

    deal = db.get_deal_by_id(deal_id)
    if not deal:
        raise ValueError(f"Deal ID {deal_id} not found.")

    deal   = dict(deal)
    accent = style["accent"]
    bar    = style["header_bar"]
    yy     = datetime.now().strftime("%y")
    today  = datetime.now().strftime("%Y-%m-%d")
    ref    = deal["reference"]

    logo_bytes = db.get_asset("logo")
    logo_b64   = _logo_b64(logo_bytes)

    currency      = deal.get("currency") or "USD"
    exchange_rate = float(deal.get("exchange_rate") or 1)

    client_addr = "\n".join(filter(None, [
        deal.get("client_addr1") or "",
        deal.get("client_addr2") or "",
    ]))

    # ── Build per-doc-type content ─────────────────────────────────────────
    body = ""

    if doc_type == "quote":
        items_list = [dict(i) for i in db.get_deal_items(deal_id)]
        doc_title  = f"Quote (Cotización): {ref}/{yy}"
        meta = [
            ("Client Ref. (Ref. Cliente):",                deal.get("client_ref") or ""),
            ("Delivery Conditions (Condición de Entrega):", f"{deal.get('incoterm') or ''} {deal.get('port_location') or ''}".strip()),
            ("", deal.get("client_name") or ""),
            ("", client_addr),
            ("Delivery Time (Tiempo de Entrega):",          deal.get("delivery_time") or ""),
            ("Payment Type (Tipo de Pago):",                deal.get("payment_terms") or ""),
        ]
        subtotal = sum(float(i.get("unit_price") or 0) * float(i.get("qty") or 0) for i in items_list)
        body = (
            _html_header(deal["seller_entity"], doc_title, ref, meta, logo_b64, accent, bar)
            + _html_items_table(items_list, accent, style["item_fill"], style["item_alt"])
            + _html_totals(subtotal, freight, accent, notes)
            + _currency_footer(currency, exchange_rate)
        )
        filename = f"QUOTE_{ref}_{today}.pdf"

    elif doc_type == "po":
        if not supplier_quote_id:
            raise ValueError("supplier_quote_id is required for PO generation.")
        items     = db.get_deal_items(deal_id)
        qi_map    = {qi["deal_item_id"]: dict(qi) for qi in db.get_quote_items(supplier_quote_id)}
        quotes    = db.get_supplier_quotes(deal_id)
        quote     = next((dict(q) for q in quotes if q["id"] == supplier_quote_id), {})
        supplier  = db.get_supplier_by_id(quote.get("supplier_id")) if quote.get("supplier_id") else None
        sup_name  = (supplier["company_name"] if supplier else quote.get("supplier_name", "")) or ""
        doc_title = f"P.O. (O.C.): {ref}/{yy}"
        meta = [
            ("Supplier's Quote # (Ref.):",   quote.get("supplier_ref") or ""),
            ("Delivery Conditions:",         f"{quote.get('incoterm','') or ''} {quote.get('location','') or ''}".strip()),
            ("", sup_name),
            ("", ""),
            ("Est. Delivery Time:",          f"{quote.get('lead_time_days','') or ''} days"),
            ("Payment Type (Tipo de Pago):", quote.get("payment_terms") or deal.get("payment_terms") or ""),
        ]
        items_list = []
        for item in items:
            d  = dict(item)
            qi = qi_map.get(d["id"], {})
            items_list.append({
                "item_number": d["item_number"],
                "description": d["description"],
                "part_number": d.get("part_number"),
                "brand":       d.get("brand"),
                "qty":         d["qty"],
                "unit":        d.get("unit"),
                "unit_price":  qi.get("unit_price") or d.get("unit_cost") or 0,
            })
        subtotal = sum(float(i.get("unit_price") or 0) * float(i.get("qty") or 0) for i in items_list)
        body = (
            _html_header(deal["seller_entity"], doc_title, ref, meta, logo_b64, accent, bar)
            + _html_items_table(items_list, accent, style["item_fill"], style["item_alt"])
            + _html_totals(subtotal, freight, accent, notes)
            + _currency_footer(currency, exchange_rate)
        )
        safe_sup = sup_name.replace(" ", "_")[:20]
        filename = f"PO_{ref}_{safe_sup}_{today}.pdf"

    elif doc_type == "invoice":
        from modules.config import SELLER_ENTITIES
        items_list = [dict(i) for i in db.get_deal_items(deal_id)]
        inv_ref    = invoice_number or ref
        doc_title  = f"Invoice (Factura): {inv_ref}/{yy}"
        entity_info = SELLER_ENTITIES.get(deal["seller_entity"], {})
        bank        = entity_info.get("bank_accounts", {}).get(currency, {})
        meta = [
            ("Client Ref. (Ref. Cliente):",  deal.get("client_ref") or ""),
            ("Delivery Conditions:",          f"{deal.get('incoterm') or ''} {deal.get('port_location') or ''}".strip()),
            ("", deal.get("client_name") or ""),
            ("", client_addr),
            ("Delivery Time:",               deal.get("delivery_time") or ""),
            ("Payment Type (Tipo de Pago):", deal.get("payment_terms") or ""),
        ]
        subtotal = sum(float(i.get("unit_price") or 0) * float(i.get("qty") or 0) for i in items_list)
        grand    = subtotal + (freight or 0)
        bank_block = f"""
        <div style="margin-top:8pt;font-size:8pt;color:#434343">
          <div style="font-weight:bold;color:#666;margin-bottom:2pt">
            Bank Instructions (Instrucciones Bancarias): {currency}
          </div>
          <div>Beneficiary: {bank.get('beneficiary','—')}</div>
          <div>Bank: {bank.get('bank','—')}</div>
          <div>SWIFT: {bank.get('swift','—')}</div>
          <div>Account: {bank.get('account','—')}</div>
        </div>
        """
        totals_block = f"""
        <hr style="border:none;border-top:1pt solid {accent};margin:4pt 0">
        <table style="width:100%;border-collapse:collapse">
          <tr>
            <td style="width:60%;vertical-align:top">{bank_block}</td>
            <td style="width:40%">
              <table style="width:100%;border-collapse:collapse">
                <tr>
                  <td style="text-align:right;color:#666;padding:2pt 4pt;font-size:8.5pt">Subtotal</td>
                  <td style="text-align:right;font-weight:bold;padding:2pt 4pt;font-size:8.5pt">{_fmt_num(subtotal)}</td>
                </tr>
                {"<tr><td style='text-align:right;color:#666;padding:2pt 4pt;font-size:8.5pt'>Shipping (Flete)</td><td style='text-align:right;font-weight:bold;padding:2pt 4pt;font-size:8.5pt'>" + _fmt_num(freight) + "</td></tr>" if freight else ""}
                <tr>
                  <td colspan="2" style="text-align:right;padding-top:4pt">
                    <span style="font-size:18pt;font-weight:bold;color:{accent}">{_fmt_num(grand)}</span>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
        </table>
        """
        body = (
            _html_header(deal["seller_entity"], doc_title, inv_ref, meta, logo_b64, accent, bar)
            + _html_items_table(items_list, accent, style["item_fill"], style["item_alt"])
            + totals_block
            + _currency_footer(currency, exchange_rate)
        )
        filename = f"INVOICE_{ref}_{today}.pdf"

    elif doc_type == "delivery_note":
        if not delivery_note_id:
            raise ValueError("delivery_note_id is required for delivery note generation.")
        dn       = db.get_delivery_note(delivery_note_id)
        dn_items = db.get_delivery_note_items(delivery_note_id)
        if not dn:
            raise ValueError(f"Delivery note {delivery_note_id} not found.")
        dn = dict(dn)
        doc_title = f"Delivery Note (Nota de Entrega): {dn['reference']}"
        meta = [
            ("Delivery Ref.:",                dn["reference"]),
            ("Invoice Ref.:",                 dn["invoice_ref"]),
            ("", dn.get("client_name") or ""),
            ("", (dn.get("client_addr1") or "") + "\n" + (dn.get("client_addr2") or "")),
            ("Delivery Conditions:",          f"{dn.get('incoterm') or ''} {dn.get('port_location') or ''}".strip()),
            ("Notes:",                        dn.get("notes") or ""),
        ]
        items_list = [dict(i) for i in dn_items]
        # Delivery note uses qty_delivered as qty, no prices
        for i in items_list:
            i["qty"] = i.get("qty_delivered", 0)

        receiver_block = f"""
        <div style="margin-top:12pt;border:1pt solid #ccc;border-radius:4pt;padding:8pt;font-size:8.5pt">
          <div style="font-weight:bold;color:#666;margin-bottom:6pt">
            Received by / Recibido por:
          </div>
          <table style="width:100%;border-collapse:collapse">
            <tr>
              <td style="width:33%;border-bottom:1pt solid #999;padding-bottom:20pt;padding-right:8pt">
                <div style="color:#999;font-size:7.5pt">Name / Nombre</div>
              </td>
              <td style="width:33%;border-bottom:1pt solid #999;padding-bottom:20pt;padding-right:8pt">
                <div style="color:#999;font-size:7.5pt">Signature / Firma</div>
              </td>
              <td style="width:34%;border-bottom:1pt solid #999;padding-bottom:20pt">
                <div style="color:#999;font-size:7.5pt">Date / Fecha</div>
              </td>
            </tr>
          </table>
        </div>
        """
        body = (
            _html_header(dn.get("seller_entity", deal["seller_entity"]),
                         doc_title, dn["reference"], meta, logo_b64, accent, bar)
            + _html_items_table(items_list, accent, style["item_fill"], style["item_alt"],
                                show_prices=False)
            + receiver_block
        )
        filename = f"DN_{dn['reference'].replace('/', '-')}_{today}.pdf"

    # ── Write PDF ────────────────────────────────────────────────────────────
    from modules.doc_generator import _export_dir
    export_dir = _export_dir()
    filepath   = os.path.join(export_dir, filename)

    html_doc = weasyprint.HTML(string=_wrap_html(body))
    html_doc.write_pdf(filepath)
    print(f"✅ PDF generated: {filename}")
    return filepath
