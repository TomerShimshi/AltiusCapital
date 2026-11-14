"""python -m benchmark.report [--agent] [--skip-tests]

Runs the unit tests and the benchmark and writes a reviewer-friendly status report to reports/latest/:
SUMMARY.md (start here), pytest.txt, junit.xml, benchmark.json and, with --agent, sample_answers.md
(plain-language questions answered by the live model, with tools used, models, tokens and sources).
"""
import json
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

from sqlalchemy import text

from app import config
from app.db import get_engine
from app.llm import Ladder, gemini_call
from app.agent import Agent
from app.trace import Tracer
from benchmark import run as bench

OUT = Path("reports/latest")
SAMPLES = [
    "How did Microsoft do last quarter?",
    "What is my biggest risk in the portfolio?",
    "What changed for Apple compared with last year?",
    "Should I sell NVIDIA?",
    "Tell me about Lilly, I'm thinking of buying it.",
    "Do my books match the custodian statements?",
    "What did Tesla say at its Investor Day?",
    "What did ExxonMobil report in Q2 2025?",
    "How much have I made on UNH?",
    "Should I buy Meta?",
]


def _git():
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def run_pytest():
    t0 = time.time()
    p = subprocess.run([sys.executable, "-m", "pytest", "-q", "--junitxml", str(OUT / "junit.xml"),
                        "-p", "no:cacheprovider"], capture_output=True, text=True)
    (OUT / "pytest.txt").write_text(p.stdout + p.stderr)
    root = ET.parse(OUT / "junit.xml").getroot()
    suite = root if root.tag == "testsuite" else root.find("testsuite")
    cases = [(c.get("classname", "").split(".")[-1], c.get("name"), "FAIL" if (c.find("failure") is not None or c.find("error") is not None)
              else ("SKIP" if c.find("skipped") is not None else "PASS")) for c in suite.iter("testcase")]
    return dict(total=len(cases), passed=sum(1 for c in cases if c[2] == "PASS"),
                failed=sum(1 for c in cases if c[2] == "FAIL"), skipped=sum(1 for c in cases if c[2] == "SKIP"),
                seconds=round(time.time() - t0), cases=cases)


def data_status(e):
    with e.connect() as c:
        q = lambda sql: c.execute(text(sql)).all()  # noqa: E731
        return dict(
            by_type=q("select doc_type, count(*), sum(as_of is null) from documents where status='ok' group by doc_type"),
            by_status=q("select status, count(*) from documents group by status"),
            ocr=q("select filename from documents where detail='ocr'"),
            tables={t: q(f"select count(*) from {t}")[0][0] for t in
                    ["documents", "chunks", "positions_books", "trades", "prices", "dividends", "corporate_actions",
                     "fx_rates", "consensus_estimates", "price_targets", "broker_notes", "custodian_positions",
                     "reconciliation"]},
            runs=q("select count(*) from trace_runs")[0][0])


def md_table(head, rows):
    return "\n".join(["| " + " | ".join(head) + " |", "|" + "---|" * len(head)] +
                     ["| " + " | ".join(str(x).replace("|", "/").replace("\n", " ") for x in r) + " |" for r in rows])


def main():
    agent_on, tests_on = "--agent" in sys.argv, "--skip-tests" not in sys.argv
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    e = get_engine()
    started = datetime.now().strftime("%Y-%m-%d %H:%M")
    tests = run_pytest() if tests_on else None
    det = bench.run_det(e)
    agent_rows = bench.run_agent(e) if agent_on else []
    bench_details = list(bench.DETAILS)
    samples = []
    if agent_on:
        tr = Tracer(e)
        ag = Agent(e, Ladder(config.GEMINI_MODELS, gemini_call(), tr))
        for q in SAMPLES:
            t0 = time.time()
            samples.append(bench.describe_run(tr, ag.answer(q), q, time.time() - t0))
    ds = data_status(e)
    rows = det + agent_rows
    (OUT / "benchmark.json").write_text(json.dumps(dict(
        generated=started, commit=_git(), cases=[dict(name=n, area=a, passed=ok, detail=d) for n, a, ok, d in rows],
        agent_runs=bench_details, samples=samples), indent=1, default=str))

    L = [f"# System status report", "", f"Generated {started} on commit `{_git()}`. Regenerate with "
         f"`python -m benchmark.report --agent`.", "", "## Headline", ""]
    if tests:
        L.append(f"- **Unit/integration tests:** {tests['passed']}/{tests['total']} passed"
                 f" ({tests['failed']} failed, {tests['skipped']} skipped) in {tests['seconds']}s. Full output: `pytest.txt`.")
    L.append(f"- **Deterministic benchmark (no LLM):** {sum(1 for r in det if r[2])}/{len(det)} passed.")
    if agent_on:
        L.append(f"- **Live-agent benchmark (Gemini free tier):** {sum(1 for r in agent_rows if r[2])}/{len(agent_rows)} passed.")
        allr = bench_details + samples
        L.append(f"- **Plain-language sample questions:** {len(samples)} answered; median "
                 f"{sorted(s['seconds'] for s in samples)[len(samples) // 2]}s, "
                 f"{sum(s['prompt_tokens'] + s['output_tokens'] for s in samples) // max(len(samples), 1):,} tokens each on average "
                 f"(free tier, cost $0). Answers: `sample_answers.md`.")
        L.append(f"- **Model fallbacks during this run:** {sum(len(s['fallbacks']) for s in allr)} across {len(allr)} questions "
                 "(free-tier models time out or are overloaded; the ladder steps down and the answer still arrives).")
    L += ["", "## Data loaded", "",
          f"Documents on file: {sum(r[1] for r in ds['by_status'] if r[0] == 'ok')} ok, "
          f"{sum(r[1] for r in ds['by_status'] if r[0] == 'failed')} failed. "
          f"OCR'd scans: {len(ds['ocr'])} ({', '.join(r[0] for r in ds['ocr'])}).", "",
          md_table(["document type", "count", "without a date"], ds["by_type"]), "",
          md_table(["table", "rows"], list(ds["tables"].items())), "",
          f"Agent runs traced in MySQL so far: {ds['runs']} (each one viewable via \"Show the work\").", "",
          "## Deterministic benchmark", "",
          md_table(["result", "area", "case", "detail"], [("PASS" if ok else "FAIL", a, n, d) for n, a, ok, d in det])]
    if agent_rows:
        L += ["", "## Live-agent benchmark", "",
              md_table(["result", "case", "detail"], [("PASS" if ok else "FAIL", n, d) for n, a, ok, d in agent_rows])]
    if tests:
        L += ["", "## Tests", "", md_table(["file", "test", "result"], tests["cases"])]
    (OUT / "SUMMARY.md").write_text("\n".join(L) + "\n")

    if samples:
        S = ["# Sample answers from the live system", "",
             f"Generated {started}, commit `{_git()}`. Each answer is the agent's real output; the metadata line "
             "shows what it did.", ""]
        for s in samples:
            S += [f"## {s['question']}", "",
                  f"*{s['seconds']}s · models: {', '.join(dict.fromkeys(s['models'])) or 'none'} · tools: "
                  f"{', '.join(s['tools']) or 'none'} · fallbacks: {len(s['fallbacks'])} · tokens: "
                  f"{s['prompt_tokens']} in / {s['output_tokens']} out · trace run {s['run_id']}*", "",
                  s["answer"], "", "**Sources:** " + ("; ".join(s["sources"]) or "none"), ""]
        (OUT / "sample_answers.md").write_text("\n".join(S))
    print((OUT / "SUMMARY.md").read_text()[:1500])
    bad = (tests and tests["failed"]) or any(not r[2] for r in rows)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
