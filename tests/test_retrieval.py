import pytest

from app import config
from app.ingest.pipeline import ingest_file
from app.retrieval import search_documents

P = config.PORTFOLIO_DIR
pytestmark = pytest.mark.skipif(not P.exists(), reason="portfolio data not present")


@pytest.fixture()
def corpus(engine):
    for f in ["Westbrook NVDA downgrade to EW.pdf", "Calder & Rowe NVDA Mar 2026.pdf",
              "MSFT FY26 Q2 earnings release.pdf"]:
        ingest_file(engine, P / f)
    return engine


def test_semantic_query_with_ticker_filter(corpus):
    res = search_documents(corpus, "what is the guidance for next quarter revenue", ticker="NVDA")
    assert res and all(r["ticker"] == "NVDA" for r in res)
    assert {"doc", "page", "text", "score", "doc_type", "as_of"} <= set(res[0])


def test_exact_number_found_by_bm25(corpus):
    res = search_documents(corpus, "$50.2 billion", k=3)
    assert res[0]["doc"] == "Westbrook NVDA downgrade to EW.pdf"
    assert res[0]["score_bm25"] > 0


def test_unknown_ticker_returns_empty(corpus):
    assert search_documents(corpus, "revenue outlook", ticker="META") == []


def test_new_document_becomes_searchable(corpus):
    assert not [r for r in search_documents(corpus, "Microsoft CFO transition", k=3) if r["doc"] == "Microsoft CFO transition.pdf"]
    ingest_file(corpus, P / "Microsoft CFO transition.pdf")
    res = search_documents(corpus, "Microsoft CFO transition", k=3)
    assert any(r["doc"] == "Microsoft CFO transition.pdf" for r in res)
