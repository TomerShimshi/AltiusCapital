from sqlalchemy import select

from app.models import documents


def list_documents(engine, ticker: str = None, doc_type: str = None, limit: int = 30) -> list:
    """Documents on file, newest first (undated last). `latest_of_type` marks the newest per ticker and type."""
    q = select(documents).where(documents.c.status == "ok")
    if ticker:
        q = q.where(documents.c.ticker == ticker.strip().upper())
    if doc_type:
        q = q.where(documents.c.doc_type == doc_type)
    with engine.connect() as c:
        rows = [dict(r) for r in c.execute(q).mappings()]
    rows.sort(key=lambda r: (r["as_of"] is None, -int((r["as_of"] or "0").replace("-", "") or 0)))
    seen, out = set(), []
    for r in rows:
        key = (r["ticker"], r["doc_type"])
        out.append(dict(filename=r["filename"], doc_type=r["doc_type"], ticker=r["ticker"], house=r["house"],
                        as_of=r["as_of"], latest_of_type=key not in seen and r["as_of"] is not None))
        seen.add(key)
    return out[:limit]
