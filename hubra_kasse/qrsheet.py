"""The sheet for the fridge: one QR code per product, as a PDF.

Scanning a code opens the club app on the tab with that product, and one tap
ticks it. The link comes from the club app itself (it knows its own address).
"""

from __future__ import annotations

import base64
import io

from jinja2 import Environment, select_autoescape

_env = Environment(autoescape=select_autoescape(default=True))

_SHEET = _env.from_string(
    """<!doctype html><html><head><meta charset="utf-8"><style>
@page { size: A4; margin: 14mm; }
body { font-family: sans-serif; color: #1c1630; margin: 0; }
h1 { font-size: 18pt; margin: 0 0 2mm; }
p.hint { font-size: 10pt; color: #555; margin: 0 0 8mm; }
.grid { font-size: 0; }
.card { display: inline-block; vertical-align: top; box-sizing: border-box;
        margin: 0 4mm 4mm 0; font-size: 11pt; width: 55mm; border: 0.3mm solid #ccc; border-radius: 3mm; padding: 4mm;
        text-align: center; page-break-inside: avoid; }
.card img { width: 40mm; height: 40mm; }
.name { font-size: 13pt; font-weight: bold; margin-top: 2mm; }
.price { font-size: 11pt; color: #444; }
</style></head><body>
<h1>{{ title }}</h1>
<p class="hint">{{ hint }}</p>
<div class="grid">
{% for p in products %}
<div class="card"><img src="{{ p.qr }}" alt=""><div class="name">{{ p.name }}</div>
<div class="price">CHF {{ p.price }}</div></div>
{% endfor %}
</div></body></html>"""
)


def qr_data_uri(text: str) -> str:
    import qrcode
    import qrcode.image.svg

    img = qrcode.make(text, image_factory=qrcode.image.svg.SvgPathImage, border=1)
    buf = io.BytesIO()
    img.save(buf)
    return "data:image/svg+xml;base64," + base64.b64encode(buf.getvalue()).decode()


def sheet(products, link: str, german: bool) -> bytes:
    """*link* ends where the product id goes, e.g. ``https://…/app/kasse/tab?tick=``."""
    from weasyprint import HTML
    from weasyprint.urls import URLFetcher

    html = _SHEET.render(
        title="Strichliste" if german else "Tab",
        hint=(
            "Code scannen und tippen: das Getränk kommt auf deine Strichliste."
            if german
            else "Scan the code and tap: it goes on your tab."
        ),
        products=[
            {
                "name": p.name,
                "price": f"{p.price:.2f}",
                "qr": qr_data_uri(f"{link}{p.id}"),
            }
            for p in products
        ],
    )
    # Self-contained: the codes are data: URIs, nothing else is loaded.
    return HTML(
        string=html, url_fetcher=URLFetcher(allowed_protocols={"data"})
    ).write_pdf()
