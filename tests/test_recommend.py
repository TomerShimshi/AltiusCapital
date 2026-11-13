import pytest

from app import config
from app.loaders.spreadsheets import load_spreadsheets
from app.loaders.statements import load_statements
from app.policy import DEFAULT_POLICY
from app.tools.brokers import load_broker_notes
from app.tools.recommend import recommend

P = config.PORTFOLIO_DIR
pytestmark = pytest.mark.skipif(not P.exists(), reason="portfolio data not present")


@pytest.fixture()
def db(engine):
    load_spreadsheets(engine, P); load_statements(engine, P); load_broker_notes(engine, P)
    return engine


def test_over_cap_position_is_trim_with_rule_and_assumption(db):
    r = recommend(db, "MSFT")
    assert r["action"] == "trim" and "position_over_cap" in r["rules_fired"]
    assert r["facts"]["weight"] > DEFAULT_POLICY["max_position_weight"]
    assert any("assumption" in a.lower() for a in r["assumptions"])
    assert r["rejected_alternatives"] and r["would_change_if"]


def test_custom_policy_changes_decision(db):
    loose = recommend(db, "MSFT", policy=dict(DEFAULT_POLICY, max_position_weight=0.5))
    assert "position_over_cap" not in loose["rules_fired"] and loose["action"] != "trim"


def test_unh_negative_view_and_loss_reported_as_facts(db):
    r = recommend(db, "UNH")
    assert {"negative_broker_view", "unrealised_loss"} <= set(r["rules_fired"])
    assert r["facts"]["unrealised_pnl_usd"] == pytest.approx(659438.0 - 929682.0)
    assert any("Halvard" in e["source"] for e in r["evidence"])


def test_not_held_name_gets_no_position_action(db):
    r = recommend(db, "TSLA")
    assert r["action"].startswith("no_position_") and r["facts"].get("weight") is None


def test_conflicting_sources_lower_confidence(db):
    r = recommend(db, "NVDA")
    assert r["confidence"] in ("low", "medium") and "houses_disagree" in r["conflicts"]
    assert any("houses_disagree" in w or "disagree" in w for w in r["would_change_if"])


def test_unknown_ticker_has_no_data(db):
    r = recommend(db, "META")
    assert r["action"] == "no_data" and r["evidence"] == []
