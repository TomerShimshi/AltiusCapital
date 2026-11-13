from app.trace import Tracer


def test_run_steps_in_order_with_answer(engine):
    t = Tracer(engine)
    rid = t.start_run("Should I sell NVDA?")
    t.step(rid, "model", "gemini-pro", {"reason": "primary"}, model="gemini-pro", ms=12)
    t.step(rid, "tool", "portfolio_exposure", {"args": {}, "result": {"NVDA": 0.11}}, ms=3)
    t.finish_run(rid, "Trim.", [{"doc": "x.pdf", "quote": "q"}])
    run = t.get_run(rid)
    assert run["question"] == "Should I sell NVDA?"
    assert [s["name"] for s in run["steps"]] == ["gemini-pro", "portfolio_exposure"]
    assert run["steps"][1]["payload"]["result"]["NVDA"] == 0.11
    assert run["answer"] == "Trim."
    assert run["citations"][0]["doc"] == "x.pdf"
