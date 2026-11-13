import pytest

from app import config
from app.loaders.spreadsheets import load_spreadsheets
from app.loaders.statements import load_statements
from app.tools.portfolio import portfolio_exposure, reconcile_positions, split_adjust

P = config.PORTFOLIO_DIR
pytestmark = pytest.mark.skipif(not P.exists(), reason="portfolio data not present")


@pytest.fixture()
def loaded(engine):
    load_spreadsheets(engine, P)
    load_statements(engine, P)
    return engine


def test_split_adjust_nvda(loaded):
    assert split_adjust(loaded, "NVDA", "2024-03-05", 1800, 779.70) == (18000, 77.97)
    assert split_adjust(loaded, "NVDA", "2025-08-20", 4000, 116.34) == (4000, 116.34)
    assert split_adjust(loaded, "AAPL", "2024-02-14", 10, 163.18) == (10, 163.18)


def test_cost_combined_across_entities(loaded):
    pos = portfolio_exposure(loaded)["positions"]
    assert pos["COST"]["quantity"] == 2300
    assert set(pos["COST"]["entities"]) == {"Harbor Oak Holdings LLC", "Harbor Oak 2019 Family Trust"}
    assert pos["COST"]["market_value_usd"] == pytest.approx(2300 * 919.60)


def test_trust_cost_in_usd_and_pnl(loaded):
    unh = portfolio_exposure(loaded)["positions"]["UNH"]
    assert unh["cost_basis_usd"] == pytest.approx(929682.0)
    assert unh["unrealised_pnl_usd"] == pytest.approx(659438.0 - 929682.0)


def test_weights_sum_to_one_and_use_custodian_qty(loaded):
    ex = portfolio_exposure(loaded)
    assert sum(p["weight"] for p in ex["positions"].values()) == pytest.approx(1.0)
    assert ex["positions"]["JPM"]["quantity"] == 7250  # custodian is the record


def test_reconcile_flags(loaded):
    rec = {(r["ticker"], r["entity"]): r for r in reconcile_positions(loaded)}
    jpm = rec[("JPM", "Harbor Oak Holdings LLC")]
    assert (jpm["books"], jpm["custodian"], jpm["diff"]) == (7520, 7250, 270)
    cost_trust = rec[("COST", "Harbor Oak 2019 Family Trust")]
    assert cost_trust["books"] is None and cost_trust["custodian"] == 900
    assert ("AAPL", "Harbor Oak Holdings LLC") not in rec
