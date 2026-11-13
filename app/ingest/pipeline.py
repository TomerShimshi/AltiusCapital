import hashlib
from pathlib import Path

import pdfplumber
from sqlalchemy import insert, select

from app.ingest.classify import classify
from app.ingest.ocr import ocr_pages
from app.models import chunks, documents

MIN_TEXT = 200  # chars on the first pages below which a PDF is treated as a scan
CHUNK, OVERLAP = 800, 100


def _pages(path: Path):
    with pdfplumber.open(str(path)) as pdf:
        pages = [(p.extract_text() or "") for p in pdf.pages]
    if len("".join(pages[:3]).strip()) >= MIN_TEXT:
        return pages, "text"
    return ocr_pages(path), "ocr"


def _chunk(text: str):
    text = text.strip()
    i = 0
    while i < len(text):
        yield text[i:i + CHUNK]
        if i + CHUNK >= len(text):
            break
        i += CHUNK - OVERLAP


def ingest_file(engine, path) -> dict:
    path = Path(path)
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    with engine.connect() as c:
        row = c.execute(select(documents.c.id).where(documents.c.sha256 == sha)).first()
    if row:
        return dict(status="duplicate", doc_id=row[0], chunks=0, doc_type=None, ticker=None)
    try:
        pages, method = _pages(path)
        full = "\n".join(pages)
        if len(full.strip()) < 50:
            raise ValueError("no readable text after OCR")
        meta = classify(full, path.name)
        with engine.begin() as c:
            doc_id = c.execute(insert(documents).values(
                sha256=sha, filename=path.name, status="ok", detail=method, **meta)).inserted_primary_key[0]
            rows = [dict(doc_id=doc_id, page=pn, text=ch) for pn, pg in enumerate(pages, 1) for ch in _chunk(pg)]
            if rows:
                c.execute(insert(chunks), rows)
        return dict(status="new", doc_id=doc_id, chunks=len(rows), **meta)
    except Exception as e:  # surfaced, never silently dropped
        with engine.begin() as c:
            doc_id = c.execute(insert(documents).values(sha256=sha, filename=path.name, status="failed",
                                                        detail=str(e)[:500])).inserted_primary_key[0]
        return dict(status="failed", doc_id=doc_id, chunks=0, doc_type=None, ticker=None, detail=str(e))


def ingest_folder(engine, folder) -> list:
    return [dict(file=p.name, **ingest_file(engine, p)) for p in sorted(Path(folder).glob("*.pdf"))]
