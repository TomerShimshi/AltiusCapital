import re
from pathlib import Path

import pdfplumber
from sqlalchemy import delete, insert

from app.models import custodian_positions


def pdf_text(path) -> str:
    with pdfplumber.open(str(path)) as pdf:
        return "\n".join((p.extract_text() or "") for p in pdf.pages)


def _num(s: str) -> float:
    neg = s.startswith("(") or s.startswith("-")
    v = float(re.sub(r"[^\d.]", "", s))
    return -v if neg else v


_NG = re.compile(r"^([A-Z]{1,5})\s+.+?\s+([\d,]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)\s+(\(?-?[\d,.]+\)?)\s+[\d.]+%$")


def parse_northgate(text: str) -> list:
    account = re.search(r"Account:\s*([\d-]+)", text).group(1)
    holder = re.search(r"Account holder:\s*(.+?),", text).group(1)
    as_of = "2026-06-30"
    rows = []
    for line in text.splitlines():
        mt = _NG.match(line.strip())
        if mt:
            t, q, px, mv, cb, _ = mt.groups()
            rows.append(dict(entity=holder, account=account, ticker=t, quantity=_num(q), price=_num(px),
                             market_value=_num(mv), cost_basis=_num(cb), currency="USD", fx_rate=1.0,
                             as_of=as_of))
    return rows


_BL = re.compile(r"^(.+?)\s+(\d[\d']*)\s+([\d.]+)\s+([\d.]+)\s+(-?[\d']+\.\d+)\s+(-?[\d']+\.\d+)\s+(-?[\d']+\.\d+)\s+[\d.]+%$")


def parse_banque_leman(text: str) -> list:
    account = re.search(r"Relation no\.:\s*(\S+)", text).group(1)
    client = re.search(r"Client:\s*(.+)", text).group(1).strip()
    fx = float(re.search(r"USD/CHF at [\d.]+\s+([\d.]+)", text).group(1))
    lines = [l.strip() for l in text.splitlines()]
    rows = []
    for i, line in enumerate(lines):
        mt = _BL.match(line)
        if mt and i + 1 < len(lines) and re.fullmatch(r"[A-Z]{1,5}", lines[i + 1]):
            _, q, px, rate, val, cost, _p = mt.groups()
            px = float(px)
            rows.append(dict(entity=client, account=account, ticker=lines[i + 1], quantity=_num(q),
                             price=px, market_value=round(_num(q) * px, 2), cost_basis=_num(cost),
                             currency="CHF", fx_rate=float(rate), as_of="2026-06-30"))
    return rows


def load_statements(engine, folder) -> int:
    folder = Path(folder)
    parsed = []
    for fname, fn in (("Northgate statement 2026-06-30.pdf", parse_northgate),
                      ("Banque Leman - releve 30.06.2026.pdf", parse_banque_leman)):
        for r in fn(pdf_text(folder / fname)):
            r["source_file"] = fname
            parsed.append(r)
    with engine.begin() as c:
        c.execute(delete(custodian_positions))
        c.execute(insert(custodian_positions), parsed)
    return len(parsed)
