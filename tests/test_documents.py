import pytest

from app import config
from app.ingest.pipeline import ingest_file
from app.reclassify import reclassify
from app.tools.documents import list_documents
from sqlalchemy import update
from app.models import documents

P = config.PORTFOLIO_DIR
pytestmark = pytest.mark.skipif(not P.exists(), reason="portfolio data not present")
MSFT = ["Microsoft FY25 Q4 Earnings Release.pdf", "MSFT FY26 Q2 earnings release.pdf", "Microsoft Q4 FY26 results.pdf"]


@pytest.fixture()
def loaded(engine):
    for f in MSFT:
        ingest_file(engine, P / f)
    return engine


def test_list_documents_newest_first_with_latest_flag(loaded):
    docs = list_documents(loaded, ticker="msft")
    assert [d["as_of"] for d in docs] == ["2026-07-27", "2026-01-27", "2025-07-25"]
    assert docs[0]["filename"] == "Microsoft Q4 FY26 results.pdf" and docs[0]["latest_of_type"] is True
    assert docs[1]["latest_of_type"] is False and docs[0]["doc_type"] == "earnings_release"


def test_list_documents_filters_and_unknown_ticker(loaded):
    assert list_documents(loaded, ticker="MSFT", doc_type="transcript") == []
    assert list_documents(loaded, ticker="META") == []


def test_undated_documents_are_listed_last_and_marked(loaded):
    with loaded.begin() as c:
        c.execute(update(documents).where(documents.c.filename == MSFT[1]).values(as_of=None))
    docs = list_documents(loaded, ticker="MSFT")
    assert docs[-1]["filename"] == MSFT[1] and docs[-1]["as_of"] is None


def test_reclassify_repairs_type_and_date_from_stored_text(loaded):
    with loaded.begin() as c:
        c.execute(update(documents).values(doc_type="10-K", as_of=None))
    assert reclassify(loaded) == len(MSFT)
    docs = {d["filename"]: d for d in list_documents(loaded, ticker="MSFT")}
    assert docs["Microsoft Q4 FY26 results.pdf"]["doc_type"] == "earnings_release"
    assert docs["Microsoft Q4 FY26 results.pdf"]["as_of"] == "2026-07-27"


DEMO = config.PORTFOLIO_DIR.parent.parent / "demo" / "Microsoft repurchase and Azure expansion Aug 2026.pdf"


def test_new_document_arriving_later_is_dated_findable_and_becomes_latest(loaded):
    from app.retrieval import search_documents
    assert list_documents(loaded, ticker="MSFT")[0]["as_of"] == "2026-07-27"
    r = ingest_file(loaded, DEMO)
    assert r["status"] == "new" and r["ticker"] == "MSFT"
    latest = list_documents(loaded, ticker="MSFT")[0]
    assert latest["filename"] == DEMO.name and latest["as_of"] == "2026-08-12" and latest["latest_of_type"]
    hit = search_documents(loaded, "additional $18.5 billion share repurchase", ticker="MSFT", k=3)
    assert hit[0]["doc"] == DEMO.name
    assert ingest_file(loaded, DEMO)["status"] == "duplicate"
