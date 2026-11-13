import pytest

from app.agent import MAX_STEPS, Agent
from app.llm import AllModelsLimited, LLMResult
from app.loaders.spreadsheets import load_spreadsheets
from app.loaders.statements import load_statements
from app import config
from app.trace import Tracer

P = config.PORTFOLIO_DIR


class ScriptedLadder:
    def __init__(self, script):
        self.script, self.i, self.seen = script, 0, []

    def generate(self, run_id, contents, system=None, tools=None):
        self.seen.append(len(contents))
        out = self.script[min(self.i, len(self.script) - 1)]
        self.i += 1
        if isinstance(out, Exception):
            raise out
        return out


def call(name, **args):
    return LLMResult(text="", calls=[dict(name=name, args=args)], model="fake")


def final(text):
    return LLMResult(text=text, calls=[], model="fake")


@pytest.fixture()
def db(engine):
    if P.exists():
        load_spreadsheets(engine, P); load_statements(engine, P)
    return engine


@pytest.mark.skipif(not P.exists(), reason="portfolio data not present")
def test_tool_call_then_answer_with_citations_and_trace(db):
    lad = ScriptedLadder([call("portfolio_exposure"), final("You hold 2,300 COST shares.")])
    out = Agent(db, lad).answer("What do I own in Costco?")
    assert out["answer"].startswith("You hold")
    assert any("Northgate" in c["source"] or "Banque" in c["source"] for c in out["citations"])
    run = Tracer(db).get_run(out["run_id"])
    assert [s["kind"] for s in run["steps"]] == ["tool"] and run["steps"][0]["name"] == "portfolio_exposure"
    assert run["answer"] == out["answer"]


def test_unknown_ticker_tool_result_is_no_data(db):
    lad = ScriptedLadder([call("recommend", ticker="META"), final("No documents on file for META.")])
    out = Agent(db, lad).answer("Should I buy Meta?")
    step = Tracer(db).get_run(out["run_id"])["steps"][0]
    assert step["payload"]["result"]["action"] == "no_data"


def test_bad_tool_args_do_not_crash(db):
    lad = ScriptedLadder([call("recommend", wrong="x"), call("nonexistent_tool"), final("Sorry, could not.")])
    out = Agent(db, lad).answer("?")
    steps = Tracer(db).get_run(out["run_id"])["steps"]
    assert all("error" in s["payload"]["result"] for s in steps) and out["answer"]


def test_all_models_limited_gives_friendly_message_and_trace(db):
    out = Agent(db, ScriptedLadder([AllModelsLimited(42)])).answer("hi")
    assert "rate" in out["answer"].lower() and "42" in out["answer"]
    steps = Tracer(db).get_run(out["run_id"])["steps"]
    assert steps[-1]["kind"] == "error"


def test_step_cap(db):
    lad = ScriptedLadder([call("reconcile_positions")])  # never stops calling tools
    out = Agent(db, lad).answer("loop")
    assert lad.i <= MAX_STEPS + 1 and "could not finish" in out["answer"].lower()
