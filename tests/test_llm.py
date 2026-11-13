import pytest

from app.llm import AllModelsLimited, Ladder, LLMResult
from app.trace import Tracer


class Err(Exception):
    def __init__(self, code, msg="x"):
        super().__init__(f"{code} {msg}")
        self.code = code


class Fake:
    """call(model, contents, system, tools) -> LLMResult, scripted per model."""
    def __init__(self, script):
        self.script, self.calls = script, []

    def __call__(self, model, contents, system=None, tools=None):
        self.calls.append(model)
        out = self.script[model]
        if isinstance(out, Exception):
            raise out
        return LLMResult(text=out, calls=[], model=model, content=None)


class Clock:
    t = 0.0
    def __call__(self):
        return self.t


@pytest.fixture()
def tr(engine):
    t = Tracer(engine)
    return t, t.start_run("q")


def test_falls_back_on_429_and_traces(tr, engine):
    t, rid = tr
    f = Fake({"a": Err(429), "b": "hello"})
    res = Ladder(["a", "b"], f, t, clock=Clock()).generate(rid, [])
    assert res.text == "hello" and res.model == "b" and f.calls == ["a", "b"]
    steps = t.get_run(rid)["steps"]
    assert [s["kind"] for s in steps] == ["fallback", "model"]
    assert steps[0]["payload"]["code"] == 429 and steps[0]["name"] == "a"
    assert steps[1]["model"] == "b"


def test_cooled_model_skipped_then_retried_after_window(tr):
    t, rid = tr
    f, clock = Fake({"a": Err(429), "b": "ok"}), Clock()
    lad = Ladder(["a", "b"], f, t, clock=clock, cooldown_s=60)
    lad.generate(rid, []); f.calls.clear()
    lad.generate(rid, [])
    assert f.calls == ["b"]            # a is cooling
    clock.t = 61; f.calls.clear()
    lad.generate(rid, [])
    assert f.calls == ["a", "b"]       # window over, a tried again


def test_all_limited_raises_with_retry_after(tr):
    t, rid = tr
    lad = Ladder(["a", "b"], Fake({"a": Err(429), "b": Err(503)}), t, clock=Clock(), cooldown_s=60)
    with pytest.raises(AllModelsLimited) as e:
        lad.generate(rid, [])
    assert 0 < e.value.retry_after_s <= 60
    with pytest.raises(AllModelsLimited):   # second call: nothing even tried
        lad.generate(rid, [])


def test_missing_model_404_cooled_long_and_other_errors_raise(tr):
    t, rid = tr
    f = Fake({"a": Err(404), "b": "ok"})
    lad = Ladder(["a", "b"], f, t, clock=Clock(), cooldown_s=60)
    lad.generate(rid, [])
    assert lad.cooling_until["a"] >= 3600
    with pytest.raises(Err):
        Ladder(["a"], Fake({"a": Err(400)}), t, clock=Clock()).generate(rid, [])
