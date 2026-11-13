import re
from pathlib import Path

import pdfplumber
from sqlalchemy import delete, insert, select

from app.models import broker_notes, price_targets

SNAPSHOT = "2026-06-30"
_MAP = {"buy": "positive", "overweight": "positive", "outperform": "positive",
        "hold": "neutral", "equal-weight": "neutral", "market perform": "neutral", "neutral": "neutral",
        "sell": "negative", "underweight": "negative", "underperform": "negative"}
_MONTHS = {m: i for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July",
                                       "August", "September", "October", "November", "December"], 1)}


def normalise_rating(house: str, rating: str) -> str:
    """Map house-specific ratings onto positive/neutral/negative. Scales are NOT comparable
    across houses; this is a coarse direction only (see broker_views flags)."""
    return _MAP[rating.strip().lower()]


def parse_broker_note(text: str, filename: str):
    head = text.splitlines()[0]
    m = re.match(r"^(.+?) \| Equity Research \| .+? \| (\w+) (\d+), (\d{4})$", head)
    if not m:
        return None
    house, mon, day, year = m.groups()
    g = lambda pat: (re.search(pat, text, re.M) or [None, None])[1]  # noqa: E731
    pt = float(g(r"^Price target \([^)]*\) \$([\d,.]+)").replace(",", ""))
    title = text.splitlines()[2]
    headline_pt = re.search(r"PT \$([\d,.]+)", title)
    flags = []
    if headline_pt and float(headline_pt.group(1).replace(",", "")) != pt:
        flags.append("pt_conflict")
    basis = g(r"EPS in this table is on a ([\w-]+) basis")
    return dict(date=f"{year}-{_MONTHS[mon]:02d}-{int(day):02d}", house=house,
                ticker=re.search(r"\(([A-Z]{1,5})\)", text.splitlines()[1]).group(1),
                rating=g(r"^Rating (.+)$"), price_target=pt, analyst=g(r"^Analyst (.+?),"),
                eps_basis=basis, source=filename, flags=flags,
                headline_pt=float(headline_pt.group(1).replace(",", "")) if headline_pt else None)


def load_broker_notes(engine, folder) -> int:
    rows = []
    for f in sorted(Path(folder).glob("*.pdf")):
        text = _full(f)
        if "Equity Research" not in text[:80]:
            continue
        n = parse_broker_note(text, f.name)
        if n:
            n.pop("headline_pt")
            rows.append(n)
    with engine.begin() as c:
        c.execute(delete(broker_notes))
        c.execute(insert(broker_notes), rows)
    return len(rows)


def _full(path) -> str:
    with pdfplumber.open(str(path)) as pdf:
        return "\n".join((p.extract_text() or "") for p in pdf.pages)


def broker_views(engine, ticker: str) -> dict:
    ticker = ticker.upper()
    with engine.connect() as c:
        notes = c.execute(select(broker_notes).where(broker_notes.c.ticker == ticker)
                          .order_by(broker_notes.c.date)).mappings().all()
        cons = c.execute(select(price_targets).where(price_targets.c.ticker == ticker)).mappings().first()
    houses = []
    for n in notes:
        flags = list(n["flags"] or [])
        if n["date"] > SNAPSHOT:
            flags.append("after_portfolio_snapshot")
        houses.append(dict(house=n["house"], date=n["date"], rating=n["rating"],
                           normalised=normalise_rating(n["house"], n["rating"]),
                           price_target=n["price_target"], analyst=n["analyst"],
                           eps_basis=n["eps_basis"], source=n["source"], flags=flags))
    flags = []
    if len({h["house"] for h in houses}) > 1:
        flags.append("ratings_not_comparable")
    if len({h["normalised"] for h in houses}) > 1:
        flags.append("houses_disagree")
    return dict(ticker=ticker, houses=houses, flags=flags,
                consensus=dict(cons) if cons else None)
