"""Exports for the billing module: Excel workbooks (openpyxl) and RTL print
views (HTML the browser prints or saves as PDF). Server-side so every device
gets the same document.
"""

from __future__ import annotations

import html
from io import BytesIO
from typing import Any, Iterable

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

Row = dict[str, Any]


def xlsx(sheets: list[tuple[str, list[str], Iterable[list[Any]]]]) -> bytes:
    """[(sheet title, headers, rows)] -> xlsx bytes, RTL sheets with bold headers."""
    wb = Workbook()
    wb.remove(wb.active)
    for title, headers, rows in sheets:
        ws = wb.create_sheet(title[:31] or "Sheet")
        ws.sheet_view.rightToLeft = True
        ws.append(headers)
        for cell in ws[1]:
            cell.font = Font(bold=True)
            cell.fill = PatternFill("solid", fgColor="E8EEF9")
            cell.alignment = Alignment(horizontal="right")
        widths = [len(str(h)) for h in headers]
        for r in rows:
            r = list(r)
            ws.append(r)
            for i, v in enumerate(r):
                if i < len(widths):
                    widths[i] = max(widths[i], min(60, len(str(v if v is not None else ""))))
        for i, w in enumerate(widths, start=1):
            ws.column_dimensions[get_column_letter(i)].width = w + 2
        ws.freeze_panes = "A2"
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


_CSS = """
body{font-family:Heebo,Arial,sans-serif;direction:rtl;color:#0f172a;margin:0;padding:32px;background:#fff}
h1{font-size:22px;margin:0 0 4px}h2{font-size:15px;margin:24px 0 8px;color:#334155}
.muted{color:#64748b;font-size:12px}.head{display:flex;justify-content:space-between;align-items:flex-start;border-bottom:2px solid #e2e8f0;padding-bottom:12px;margin-bottom:16px}
table{width:100%;border-collapse:collapse;font-size:13px}th{text-align:right;background:#f1f5f9;padding:8px;border-bottom:1px solid #cbd5e1;font-weight:600}
td{padding:8px;border-bottom:1px solid #e2e8f0;vertical-align:top}.num{direction:ltr;text-align:left;white-space:nowrap}
.totals{margin-top:16px;margin-inline-start:auto;width:320px}.totals td{border:0;padding:4px 8px}.totals .grand{font-weight:700;font-size:15px;border-top:2px solid #0f172a}
.badge{display:inline-block;border-radius:999px;padding:2px 10px;font-size:12px;background:#f1f5f9}
@media print{body{padding:12mm}.noprint{display:none}}
.noprint{position:fixed;top:12px;left:12px}.noprint button{padding:8px 14px;border-radius:8px;border:1px solid #cbd5e1;background:#fff;cursor:pointer}
"""


def _e(v: Any) -> str:
    return html.escape("" if v is None else str(v))


def _ils(v: Any) -> str:
    try:
        return f"₪{float(v or 0):,.2f}"
    except (TypeError, ValueError):
        return "₪0.00"


def page(title: str, body: str) -> str:
    return (f"<!doctype html><html lang='he' dir='rtl'><head><meta charset='utf-8'><title>{_e(title)}</title>"
            f"<link href='https://fonts.googleapis.com/css2?family=Heebo:wght@400;600;700&display=swap' rel='stylesheet'>"
            f"<style>{_CSS}</style></head><body>"
            f"<div class='noprint'><button onclick='window.print()'>הדפסה / שמירה כ-PDF</button></div>{body}</body></html>")


def charge_html(charge: Row, lines: list[Row], customer: Row, business: Row, period_label: str) -> str:
    biz = "".join(f"<div class='muted'>{_e(business.get(k))}</div>" for k in ("address", "phone", "email") if business.get(k))
    vat_id = f"<div class='muted'>ע.מ. / ח.פ. {_e(business['vat_id'])}</div>" if business.get("vat_id") else ""
    status = {"draft": "טיוטה", "issued": "הופק", "paid": "שולם", "cancelled": "בוטל"}.get(charge.get("status", ""), charge.get("status", ""))
    rows = "".join(
        f"<tr><td>{_e(l.get('description'))}</td><td class='num'>{float(l.get('quantity') or 0):g}</td>"
        f"<td class='num'>{_ils(l.get('unit_price'))}</td><td class='num'>{_ils(l.get('total'))}</td></tr>" for l in lines)
    body = f"""
<div class='head'>
  <div><h1>{_e(business.get('name') or 'חיוב חודשי')}</h1>{vat_id}{biz}</div>
  <div style='text-align:left'><div class='muted'>חיוב לתקופה</div><div style='font-size:18px;font-weight:700'>{_e(period_label)}</div>
  <div class='muted'>מספר {_e(charge.get('id'))}</div><span class='badge'>{status}</span></div>
</div>
<h2>לכבוד</h2>
<div><strong>{_e(customer.get('name'))}</strong></div>
<div class='muted'>{_e(customer.get('contact_person'))} {_e(customer.get('phone'))} {_e(customer.get('email'))}</div>
<div class='muted'>{_e(customer.get('address'))}</div>
<h2>פירוט</h2>
<table><thead><tr><th>תיאור</th><th>כמות</th><th>מחיר יחידה</th><th>סה"כ</th></tr></thead><tbody>{rows}</tbody></table>
<table class='totals'>
  <tr><td>סכום לפני מע"מ</td><td class='num'>{_ils(charge.get('subtotal'))}</td></tr>
  <tr><td>מע"מ {float(charge.get('vat_pct') or 0):g}%</td><td class='num'>{_ils(charge.get('vat'))}</td></tr>
  <tr class='grand'><td>סה"כ לתשלום</td><td class='num'>{_ils(charge.get('total'))}</td></tr>
</table>
{f"<h2>הערות</h2><div>{_e(charge.get('notes'))}</div>" if charge.get('notes') else ''}
"""
    return page(f"חיוב {customer.get('name', '')} {period_label}", body)


def hours_html(report: Row, customer_name: str, start: str, end: str, business: Row) -> str:
    rows = "".join(
        f"<tr><td class='num'>{_e(r['entry_date'])}</td><td>{_e(r.get('ticket_number'))} · {_e(r['ticket_title'])}</td><td>{_e(r['employee_name'])}</td>"
        f"<td>{_e(r['description'])}</td><td class='num'>{r['minutes'] // 60}:{r['minutes'] % 60:02d}</td></tr>" for r in report["entries"])
    emp = "".join(f"<tr><td>{_e(x['employee_name'])}</td><td class='num'>{x['minutes'] // 60}:{x['minutes'] % 60:02d}</td></tr>" for x in report["by_employee"])
    tm = report["total_minutes"]
    body = f"""
<div class='head'>
  <div><h1>דוח שעות טיפול</h1><div class='muted'>{_e(business.get('name', ''))}</div></div>
  <div style='text-align:left'><div><strong>{_e(customer_name)}</strong></div><div class='muted'>{_e(start)} עד {_e(end)}</div>
  <div style='font-size:18px;font-weight:700'>{tm // 60}:{tm % 60:02d} שעות</div></div>
</div>
<table><thead><tr><th>תאריך</th><th>קריאה</th><th>מטפל</th><th>תיאור</th><th>זמן</th></tr></thead><tbody>{rows}</tbody></table>
<h2>לפי מטפל</h2><table class='totals'>{emp}</table>
"""
    return page(f"דוח שעות {customer_name}", body)
