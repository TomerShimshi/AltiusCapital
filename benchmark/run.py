"""python -m benchmark.run [--agent]   (deterministic cases need no LLM; --agent uses the live model ladder)"""
import re
import sys
import time

from app import config
from app.agent import Agent
from app.db import get_engine
from app.llm import Ladder, gemini_call
from app.trace import Tracer
from benchmark.cases import AGENT, DET


def run_det(e):
    rows = []
    for name, area, fn in DET:
        try:
            r = fn(e)
        except Exception as ex:  # noqa: BLE001
            r = f"error: {type(ex).__name__}: {ex}"
        rows.append((name, area, r is True, "" if r is True else str(r)))
    return rows


def run_agent(e):
    tr = Tracer(e)
    agent = Agent(e, Ladder(config.GEMINI_MODELS, gemini_call(), tr))
    rows = []
    for name, q, tools, must, mustnot in AGENT:
        t0 = time.time()
        out = agent.answer(q)
        used = {s["name"] for s in tr.get_run(out["run_id"])["steps"] if s["kind"] == "tool"}
        fails = []
        if not tools <= used:
            fails.append(f"tools {sorted(used)} missing {sorted(tools - used)}")
        fails += [f"missing /{p}/" for p in must if not re.search(p, out["answer"])]
        fails += [f"forbidden /{p}/" for p in mustnot if re.search(p, out["answer"])]
        if tools and not out["citations"]:
            fails.append("no citations")
        rows.append((f"{name}: {q}", "agent", not fails, "; ".join(fails) + f" [{time.time() - t0:.0f}s, run {out['run_id']}]"))
    return rows


if __name__ == "__main__":
    e = get_engine()
    rows = run_det(e) + (run_agent(e) if "--agent" in sys.argv else [])
    for name, area, ok, detail in rows:
        print(("PASS" if ok else "FAIL"), f"[{area}]", name, ("-> " + detail) if detail else "")
    p = sum(1 for r in rows if r[2])
    print(f"\n{p}/{len(rows)} passed")
    sys.exit(0 if p == len(rows) else 1)
