"""Generate the invented demo document (fictional) used to show live ingestion.

Needs reportlab (dev only, not in requirements.txt):  pip install reportlab
"""
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

LINES = [
    ("Microsoft Corporation", 14, True),
    ("Microsoft Announces Increased Share Repurchase Authorization and Azure Capacity Expansion", 12, True),
    ("REDMOND, WASHINGTON - August 12, 2026 - Microsoft Corporation (Nasdaq: MSFT) today announced that its", 10, False),
    ("Board of Directors approved an additional $18.5 billion share repurchase authorization, and that the", 10, False),
    ("company will add 1.2 gigawatts of Azure data-center capacity over the next four quarters.", 10, False),
    ("", 10, False),
    ("- Additional repurchase authorization: $18.5 billion, on top of the program announced in fiscal 2025.", 10, False),
    ("- Azure capital expenditure for the expansion: approximately $9.4 billion in fiscal 2027.", 10, False),
    ("- Management now expects fiscal 2027 first-quarter Azure growth of 28% to 30% in constant currency,", 10, False),
    ("  versus 30% reported in the fourth quarter of fiscal 2026.", 10, False),
    ("- Capacity constraints are expected to ease gradually, with full effect in the second half of fiscal 2027.", 10, False),
    ("", 10, False),
    ("\"We are investing ahead of demand while returning more capital to shareholders,\" said the Chief Financial", 10, False),
    ("Officer. The company does not expect this announcement to change its dividend policy.", 10, False),
    ("", 10, False),
    ("Forward-looking statements: this document is fictional and was created to demonstrate document ingestion.", 8, False),
]


def make(path="demo/Microsoft repurchase and Azure expansion Aug 2026.pdf"):
    c = canvas.Canvas(path, pagesize=letter)
    y = 740
    for text, size, bold in LINES:
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        c.drawString(50, y, text)
        y -= size + 6
    c.save()
    return path


if __name__ == "__main__":
    print(make())
