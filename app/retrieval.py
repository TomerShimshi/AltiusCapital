"""Hybrid retrieval: BM25 (exact tokens/numbers) + local sentence-transformer embeddings,
merged by weighted, min-max-normalised score fusion. Index is rebuilt when the chunk set changes."""
import re
import weakref

import numpy as np
from rank_bm25 import BM25Okapi
from sqlalchemy import func, select, update

from app import config
from app.models import chunks, documents

_model = None
_cache = weakref.WeakKeyDictionary()


def _tok(s: str):
    return re.findall(r"[a-z0-9]+(?:[.,][0-9]+)*", s.lower())


def _embedder():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(config.EMBED_MODEL, token=config.HF_TOKEN or None)
    return _model


def _load(engine):
    q = (select(chunks.c.id, chunks.c.page, chunks.c.text, chunks.c.embedding, documents.c.filename,
                documents.c.ticker, documents.c.doc_type, documents.c.as_of, documents.c.house)
         .join(documents, documents.c.id == chunks.c.doc_id).where(documents.c.status == "ok")
         .order_by(chunks.c.id))
    with engine.connect() as c:
        rows = [dict(r) for r in c.execute(q).mappings()]
    missing = [r for r in rows if r["embedding"] is None]
    if missing:
        vecs = _embedder().encode([r["text"] for r in missing], normalize_embeddings=True,
                                  batch_size=32, show_progress_bar=False)
        with engine.begin() as c:
            for r, v in zip(missing, vecs):
                r["embedding"] = np.asarray(v, dtype=np.float32).tobytes()
                c.execute(update(chunks).where(chunks.c.id == r["id"]).values(embedding=r["embedding"]))
    return rows


def _index(engine):
    with engine.connect() as c:
        sig = c.execute(select(func.count(), func.max(chunks.c.id)).select_from(chunks)).one()
        n_emb = c.execute(select(func.count()).select_from(chunks).where(chunks.c.embedding.is_(None))).scalar()
    cached = _cache.get(engine)
    if cached is None or cached[0] != (tuple(sig), n_emb):
        rows = _load(engine)
        bm = BM25Okapi([_tok(r["text"]) for r in rows]) if rows else None
        mat = np.vstack([np.frombuffer(r["embedding"], dtype=np.float32) for r in rows]) if rows else None
        cached = _cache[engine] = ((tuple(sig), n_emb), rows, bm, mat)
    return cached[1:]


def search_documents(engine, query: str, ticker: str = None, k: int = 6) -> list:
    rows, bm, mat = _index(engine)
    if not rows:
        return []
    keep = [i for i, r in enumerate(rows) if not ticker or r["ticker"] == ticker.upper()]
    if not keep:
        return []
    bm_scores = bm.get_scores(_tok(query))
    qv = _embedder().encode([query], normalize_embeddings=True, show_progress_bar=False)[0]
    vec_scores = mat @ qv
    def norm(scores):
        v = np.array([scores[i] for i in keep], dtype=float)
        lo, hi = v.min(), v.max()
        return {i: (scores[i] - lo) / (hi - lo) if hi > lo else 0.0 for i in keep}

    w = 0.7 if re.search(r"\d", query) else 0.4  # numeric queries: exact-token match matters more
    nb, nv = norm(bm_scores), norm(vec_scores)
    fused = {i: w * nb[i] + (1 - w) * nv[i] for i in keep}
    out = []
    for i in sorted(fused, key=fused.get, reverse=True)[:k]:
        r = rows[i]
        out.append(dict(doc=r["filename"], page=r["page"], text=r["text"], ticker=r["ticker"],
                        doc_type=r["doc_type"], as_of=r["as_of"], house=r["house"],
                        score=round(fused[i], 5), score_bm25=float(bm_scores[i]),
                        score_vec=float(vec_scores[i])))
    return out
