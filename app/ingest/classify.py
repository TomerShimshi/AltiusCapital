import difflib
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


_DATE = re.compile(r"([A-Za-z]{3,9})\s*(\d{1,2})\s*[,.]\s*(20\d\d)")


def _month(word: str):
    m = difflib.get_close_matches(word.capitalize(), _MON, n=1, cutoff=0.8)  # tolerates OCR noise ("Ganuary")
    return _MON.index(m[0]) + 1 if m else None


def _dates(text: str):
    for w, d, y in _DATE.findall(text):
        mo = _month(w)
        if mo and 1 <= int(d) <= 31:
            yield f"{y}-{mo:02d}-{int(d):02d}"


def _date(text: str, doc_type: str = ""):
    if doc_type == "custodian_statement":  # the statement date is the end of its period, not a stray date
        m = re.search(r"(?:period|p[ée]riode)[^\n]*?[–-]\s*([^\n]+)", text[:1500], re.I)
        if m:
            end = next(_dates(m.group(1)), None)
            if end:
                return end
        swiss = re.findall(r"\b(\d{2})\.(\d{2})\.(20\d\d)\b", m.group(1) if m else text[:1500])  # dd.mm.yyyy
        if swiss:
            d, mo, y = swiss[-1]
            return f"{y}-{mo}-{d}"
    found = list(_dates(text[:1500]))
    if not found:
        return None
    return found[-1] if doc_type == "custodian_statement" else found[0]  # statements: period end


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
    elif re.search(r"transcri\w+|earnings call", head.lower()) or "call" in fl:
        dt = "transcript"
    elif re.search(r"investor day|r&d day|investor overview|stock split", head.lower() + fl):
        dt = "presentation_or_event"
    elif re.search(r"\b(reports|announces)\b.{0,80}(results|earnings)|operating results|financial results", head.lower()) \
            and not re.search(r"form 10-[kq]", head.lower()):
        dt = "earnings_release"
    elif re.search(r"form 10-k|annual report", head.lower()) or "10-k" in fl:
        dt = "10-K"
    elif re.search(r"form 10-q|quarterly report", head.lower()) or "10-q" in fl:
        dt = "10-Q"
    elif re.search(r"\boperator\b", low):
        dt = "transcript"
    elif re.search(r"reports|announces|results", low + fl):
        dt = "earnings_release"
    else:
        dt = "other"
    ticker = None if dt == "custodian_statement" else _ticker(text, filename)
    return dict(doc_type=dt, ticker=ticker, house=house, as_of=_date(text, dt))
