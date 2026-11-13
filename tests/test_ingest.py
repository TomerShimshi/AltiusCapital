import shutil
import threading
import time

import pytest
from sqlalchemy import func, select

from app import config
from app.ingest.classify import classify
from app.ingest.ocr import ocr_pdf
from app.ingest.pipeline import ingest_file, ingest_folder
from app.ingest.watcher import watch
from app.loaders.statements import pdf_text
from app.models import chunks, documents

P = config.PORTFOLIO_DIR
pytestmark = pytest.mark.skipif(not P.exists(), reason="portfolio data not present")


def test_duplicate_detected_by_content(engine):
    a = ingest_file(engine, P / "MSFT FY26 Q2 earnings release.pdf")
    b = ingest_file(engine, P / "Microsoft FY26 Q2 (1).pdf")
    assert a["status"] == "new" and b["status"] == "duplicate" and b["doc_id"] == a["doc_id"]
    with engine.connect() as c:
        n = c.execute(select(func.count()).select_from(chunks).where(chunks.c.doc_id == a["doc_id"])).scalar()
    assert n == a["chunks"] > 0
    assert ingest_file(engine, P / "MSFT FY26 Q2 earnings release.pdf")["status"] == "duplicate"


def test_classify_broker_note():
    f = "Westbrook NVDA downgrade to EW.pdf"
    c = classify(pdf_text(P / f), f)
    assert (c["doc_type"], c["ticker"], c["house"], c["as_of"]) == (
        "broker_note", "NVDA", "Westbrook Securities", "2026-05-29")


def test_classify_misc():
    for f, dt, tk in [("Amazon 10-Q Q1 2026.pdf", "10-Q", "AMZN"), ("NVIDIA 10-K fiscal 2026.pdf", "10-K", "NVDA"),
                      ("Apple Q1 FY26 call.pdf", "transcript", "AAPL"),
                      ("Northgate statement 2026-06-30.pdf", "custodian_statement", None)]:
        c = classify(pdf_text(P / f), f)
        assert c["doc_type"] == dt and c["ticker"] == tk, f


def test_ocr_scan_readable_and_classified(engine):
    text = ocr_pdf(P / "scan_20260730_1142.pdf")
    assert "UnitedHealth" in text and "second quarter" in text.lower()
    r = ingest_file(engine, P / "scan_20260730_1142.pdf")
    assert r["status"] == "new" and r["ticker"] == "UNH" and r["chunks"] > 0


def test_ingest_folder_all_files(engine):
    res = ingest_folder(engine, P)
    st = [r["status"] for r in res]
    assert st.count("failed") == 0 and st.count("duplicate") == 1
    with engine.connect() as c:
        assert c.execute(select(func.count()).select_from(documents)).scalar() == len(res) - 1


def test_watcher_ingests_new_file(engine, tmp_path):
    stop = threading.Event()
    t = threading.Thread(target=watch, args=(engine, tmp_path, 0.5, stop), daemon=True)
    t.start()
    shutil.copy(P / "Microsoft CFO transition.pdf", tmp_path / "late arrival.pdf")
    deadline = time.time() + 10
    n = 0
    while time.time() < deadline and n == 0:
        time.sleep(0.5)
        with engine.connect() as c:
            n = c.execute(select(func.count()).select_from(documents)).scalar()
    stop.set()
    assert n == 1
