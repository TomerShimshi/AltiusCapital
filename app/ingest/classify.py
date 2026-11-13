import re

_COMPANIES = {"AAPL": ["apple"], "MSFT": ["microsoft"], "NVDA": ["nvidia"], "AMZN": ["amazon"],
              "JPM": ["jpmorgan", "jpm "], "XOM": ["exxon"], "UNH": ["unitedhealth"],
              "COST": ["costco"], "TSLA": ["tesla"], "LLY": ["lilly"]}
_MON = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
        "October", "November", "December"]


def _ticker(text: str, filename: str):
    low = (filename + " " + text[:4000]).lower()
    best, score = None, 0
    for t, keys in _COMPANIES.items():
        s = sum(low.count(k) for k in keys) + (3 if t.lower() in filename.lower().split() else 0)
        if s > score:
            best, score = t, s
    return best


def _date(text: str):
    m = re.search(r"(%s)\s+(\d{1,2}),\s*(\d{4})" % "|".join(_MON), text[:1500])
    if m:
        return f"{m.group(3)}-{_MON.index(m.group(1)) + 1:02d}-{int(m.group(2)):02d}"
    return None


def classify(text: str, filename: str) -> dict:
    head, low = text[:600], text[:3000].lower()
    fl = filename.lower()
    house = None
    m = re.match(r"^(.+?) \| Equity Research", head)
    if m:
        dt, house = "broker_note", m.group(1)
        if house == "Westbrook":
            house = "Westbrook Securities"
    elif "account statement" in low or "relevé" in low or "portfolio statement" in low:
        dt = "custodian_statement"
    elif re.search(r"form 10-k|annual report", low) or "10-k" in fl:
        dt = "10-K"
    elif re.search(r"form 10-q|quarterly report", low) or "10-q" in fl:
        dt = "10-Q"
    elif re.search(r"earnings call|transcript|\boperator\b|conference call", low) or "call" in fl:
        dt = "transcript"
    elif re.search(r"investor day|r&d day|investor overview|stock split", low + fl):
        dt = "presentation_or_event"
    elif re.search(r"reports|announces|results", low + fl):
        dt = "earnings_release"
    else:
        dt = "other"
    ticker = None if dt == "custodian_statement" else _ticker(text, filename)
    return dict(doc_type=dt, ticker=ticker, house=house, as_of=_date(text))
