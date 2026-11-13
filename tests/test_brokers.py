import pytest

from app import config
from app.loaders.spreadsheets import load_spreadsheets
from app.tools.brokers import broker_views, load_broker_notes, normalise_rating

P = config.PORTFOLIO_DIR
pytestmark = pytest.mark.skipif(not P.exists(), reason="portfolio data not present")


@pytest.mark.parametrize("house,rating,expected", [
    ("Calder & Rowe", "Buy", "positive"), ("Westbrook Securities", "Overweight", "positive"),
    ("Calder & Rowe", "Hold", "neutral"), ("Westbrook Securities", "Equal-weight", "neutral"),
    ("Halvard Research", "Market Perform", "neutral"), ("Halvard Research", "Underperform", "negative"),
    ("Westbrook Securities", "Underweight", "negative"), ("Calder & Rowe", "Sell", "negative")])
def test_normalise_rating(house, rating, expected):
    assert normalise_rating(house, rating) == expected


@pytest.fixture()
def loaded(engine):
    load_spreadsheets(engine, P)
    assert load_broker_notes(engine, P) == 7
    return engine


def test_nvda_views_disagree_and_flag_conflict(loaded):
    v = broker_views(loaded, "NVDA")
    by = {h["house"]: h for h in v["houses"]}
    assert by["Calder & Rowe"]["normalised"] == "positive" and by["Calder & Rowe"]["price_target"] == 240
    assert by["Westbrook Securities"]["normalised"] == "neutral" and by["Westbrook Securities"]["price_target"] == 155
    assert "pt_conflict" in by["Calder & Rowe"]["flags"]
    assert by["Calder & Rowe"]["eps_basis"] == "GAAP" and by["Westbrook Securities"]["eps_basis"] == "non-GAAP"
    assert v["consensus"]["consensus_pt"] == 133 and v["consensus"]["last_price"] == 141.15
    assert "ratings_not_comparable" in v["flags"]


def test_lly_three_houses_and_unknown_ticker(loaded):
    assert len(broker_views(loaded, "LLY")["houses"]) == 3
    assert broker_views(loaded, "META")["houses"] == []


def test_unh_note_after_snapshot_flagged(loaded):
    h = broker_views(loaded, "UNH")["houses"][0]
    assert h["normalised"] == "negative" and "after_portfolio_snapshot" in h["flags"]
