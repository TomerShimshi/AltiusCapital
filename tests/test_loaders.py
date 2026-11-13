from pathlib import Path

import pytest
from sqlalchemy import func, select

from app import config
from app.loaders.spreadsheets import load_spreadsheets
from app.loaders.statements import load_statements, parse_banque_leman, parse_northgate, pdf_text
from app.models import (corporate_actions, custodian_positions, positions_books)

P = config.PORTFOLIO_DIR
pytestmark = pytest.mark.skipif(not P.exists(), reason="portfolio data not present")


def test_spreadsheets_loaded(engine):
    counts = load_spreadsheets(engine, P)
    assert counts["positions_books"] == 8
    with engine.connect() as c:
        jpm = c.execute(select(positions_books.c.quantity).where(positions_books.c.ticker == "JPM")).scalar()
        ca = c.execute(select(corporate_actions)).mappings().all()
    assert jpm == 7520
    assert ca[0]["ticker"] == "NVDA" and ca[0]["ratio"] == "10:1" and ca[0]["effective"] == "2025-06-10"
    assert counts["trades"] > 80 and counts["prices"] > 300


def test_spreadsheets_idempotent(engine):
    load_spreadsheets(engine, P)
    load_spreadsheets(engine, P)
    with engine.connect() as c:
        assert c.execute(select(func.count()).select_from(positions_books)).scalar() == 8


def test_parse_northgate():
    rows = parse_northgate(pdf_text(P / "Northgate statement 2026-06-30.pdf"))
    by = {r["ticker"]: r for r in rows}
    assert len(rows) == 7 and by["JPM"]["quantity"] == 7250 and by["XOM"]["cost_basis"] == 1151480.0
    assert by["NVDA"]["market_value"] == 1976100.0 and rows[0]["account"] == "4471-8820"


def test_parse_banque_leman():
    rows = parse_banque_leman(pdf_text(P / "Banque Leman - releve 30.06.2026.pdf"))
    by = {r["ticker"]: r for r in rows}
    assert by["UNH"]["quantity"] == 2600 and by["COST"]["quantity"] == 900
    assert by["UNH"]["fx_rate"] == 0.7801 and by["UNH"]["currency"] == "CHF"
    assert by["UNH"]["cost_basis"] == 736029.24


def test_load_statements(engine):
    assert load_statements(engine, P) == 9
    with engine.connect() as c:
        assert c.execute(select(func.count()).select_from(custodian_positions)).scalar() == 9
