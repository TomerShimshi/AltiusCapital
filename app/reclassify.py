"""Re-run classification over documents already in the database, using their stored text.

Use after the classifier improves:  python -m app.reclassify
"""
from sqlalchemy import select, update

from app.db import get_engine
from app.ingest.classify import classify
from app.models import chunks, documents


def _head(c, doc_id: int, n: int = 3000) -> str:
    rows = c.execute(select(chunks.c.page, chunks.c.text).where(chunks.c.doc_id == doc_id)
                     .order_by(chunks.c.id).limit(6)).all()
    out, prev = "", None
    for page, text in rows:  # chunks overlap by 100 chars within a page: drop the overlap before joining
        out += text if prev != page else text[100:]
        prev = page
    return out[:n]


def reclassify(engine) -> int:
    n = 0
    with engine.begin() as c:
        for d in c.execute(select(documents.c.id, documents.c.filename).where(documents.c.status == "ok")).all():
            head = _head(c, d.id)
            if not head:
                continue
            meta = classify(head, d.filename)
            c.execute(update(documents).where(documents.c.id == d.id).values(**meta))
            n += 1
    return n


if __name__ == "__main__":
    print(f"reclassified {reclassify(get_engine())} documents")
