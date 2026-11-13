"""Benchmark cases. Expected values are computed independently from the source files
(statements, spreadsheets), not from the code under test. `check` returns True or a failure detail."""
from sqlalchemy import func, select

from app.models import consensus_estimates, documents
from app.retrieval import search_documents
from app.tools.brokers import broker_views, normalise_rating
from app.tools.portfolio import portfolio_exposure, reconcile_positions, split_adjust
from app.tools.recommend import recommend

# Independent ground truth (hand-checked against the Northgate / Banque Leman statements)
TOTAL_SECURITIES = 13_171_947.50 + 2600 * 253.63 + 900 * 919.60   # LLC securities + Trust UNH + Trust COST


def eq(a, b, tol=0.01):
    return True if abs(a - b) <= tol else f"got {a}, expected {b}"


def _pos(e, t):
    return portfolio_exposure(e)["positions"][t]


def _rec(e, k, **m):
    r = {(x["ticker"], x["entity"]): x for x in reconcile_positions(e)}
    return r.get((k[0], k[1]))


DET = [  # (name, trap_or_area, check(engine))
    ("COST held in both accounts is combined: 2,300 shares", "two custodians", lambda e: eq(_pos(e, "COST")["quantity"], 2300)),
    ("COST combined market value", "two custodians", lambda e: eq(_pos(e, "COST")["market_value_usd"], 2300 * 919.60)),
    ("JPM quantity follows the custodian (7,250), not the books (7,520)", "books vs custodian", lambda e: eq(_pos(e, "JPM")["quantity"], 7250)),
    ("Reconciliation flags JPM 7,520 vs 7,250", "books vs custodian", lambda e: (lambda r: True if r and (r["books"], r["custodian"], r["diff"]) == (7520, 7250, 270) else f"got {r}")(_rec(e, ("JPM", "Harbor Oak Holdings LLC")))),
    ("Reconciliation flags Trust COST missing from the books", "books vs custodian", lambda e: (lambda r: True if r and r["books"] is None and r["custodian"] == 900 else f"got {r}")(_rec(e, ("COST", "Harbor Oak 2019 Family Trust")))),
    ("NVDA pre-split trade 1,800 @ 779.70 becomes 18,000 @ 77.97", "stock split", lambda e: True if split_adjust(e, "NVDA", "2024-03-05", 1800, 779.70) == (18000, 77.97) else "wrong adjustment"),
    ("NVDA post-split trade is not adjusted", "stock split", lambda e: True if split_adjust(e, "NVDA", "2025-08-20", 4000, 116.34) == (4000, 116.34) else "adjusted wrongly"),
    ("Trust UNH cost in USD from blotter (929,682) and loss (-270,244)", "CHF account", lambda e: (lambda p: True if abs(p["cost_basis_usd"] - 929682) < 1 and abs(p["unrealised_pnl_usd"] + 270244) < 1 else f"got {p['cost_basis_usd']}, {p['unrealised_pnl_usd']}")(_pos(e, "UNH"))),
    ("Total listed securities value across both accounts", "aggregation", lambda e: eq(portfolio_exposure(e)["totals"]["market_value_usd"], TOTAL_SECURITIES)),
    ("Weights sum to 100%", "aggregation", lambda e: eq(sum(p["weight"] for p in portfolio_exposure(e)["positions"].values()), 1.0, 1e-9)),
    ("MSFT is the largest position (17.8%)", "aggregation", lambda e: True if max(portfolio_exposure(e)["positions"].items(), key=lambda kv: kv[1]["weight"])[0] == "MSFT" else "not MSFT"),
    ("Rating scales normalise (Overweight=Buy, Equal-weight=Hold, Underweight=Sell)", "rating scales", lambda e: True if [normalise_rating("x", r) for r in ("Overweight", "Equal-weight", "Underweight")] == ["positive", "neutral", "negative"] else "mismatch"),
    ("NVDA: Calder & Rowe PT 240 vs Westbrook 155, houses disagree", "broker conflict", lambda e: (lambda v: True if {h["house"]: h["price_target"] for h in v["houses"]} == {"Calder & Rowe": 240, "Westbrook Securities": 155} and "houses_disagree" in v["flags"] else f"got {v['houses']}")(broker_views(e, "NVDA"))),
    ("C&R NVDA note flagged: headline PT $165 vs rating box $240", "self-contradicting note", lambda e: True if any("pt_conflict" in h["flags"] for h in broker_views(e, "NVDA")["houses"]) else "no flag"),
    ("EPS basis differs by house (GAAP vs non-GAAP) on NVDA", "EPS basis", lambda e: True if {h["eps_basis"] for h in broker_views(e, "NVDA")["houses"]} == {"GAAP", "non-GAAP"} else "not detected"),
    ("LLY has three houses on file", "considering names", lambda e: True if len(broker_views(e, "LLY")["houses"]) == 3 else "not 3"),
    ("UNH Halvard note postdates the 30 Jun snapshot and is flagged", "stale/new data", lambda e: True if "after_portfolio_snapshot" in broker_views(e, "UNH")["houses"][0]["flags"] else "no flag"),
    ("Vendor EPS text '$4.82' (UNH Q1 2025) loaded as a number", "dirty spreadsheet", lambda e: eq(e.connect().execute(select(consensus_estimates.c.eps_cons).where(consensus_estimates.c.ticker == "UNH", consensus_estimates.c.period == "Q1 2025")).scalar(), 4.82)),
    ("All PDFs ingested (57 unique), none failed", "ingestion", lambda e: (lambda c: True if c == (57, 0) else f"got ok/failed {c}")((e.connect().execute(select(func.count()).select_from(documents).where(documents.c.status == "ok")).scalar(), e.connect().execute(select(func.count()).select_from(documents).where(documents.c.status == "failed")).scalar()))),
    ("Scans read by OCR and classified (AMZN call, UNH release, XOM release)", "OCR", lambda e: (lambda d: True if d == {"Doc_2026-02-06_scan.pdf": "AMZN", "scan_20260730_1142.pdf": "UNH", "ExxonMobil 2Q25 earnings.pdf": "XOM"} else f"got {d}")({r[0]: r[1] for r in e.connect().execute(select(documents.c.filename, documents.c.ticker).where(documents.c.detail == "ocr")).all()})),
    ("Exact-figure search '$50.2 billion' returns exactly the two documents that contain it (company release + Westbrook note)", "retrieval", lambda e: (lambda d: True if d == {"NVIDIA Announces Financial Results for First Quarter Fiscal 2027.pdf", "Westbrook NVDA downgrade to EW.pdf"} else f"got {d}")({r["doc"] for r in search_documents(e, "$50.2 billion", k=2)})),
    ("Search for a ticker with no documents returns nothing", "no hallucination", lambda e: True if search_documents(e, "revenue outlook", ticker="META") == [] else "returned something"),
    ("Recommendation for unknown ticker META is no_data", "no hallucination", lambda e: True if recommend(e, "META")["action"] == "no_data" else "gave a verdict"),
    ("MSFT over the 15% cap -> trim, rule position_over_cap", "decision", lambda e: (lambda r: True if r["action"] == "trim" and "position_over_cap" in r["rules_fired"] else f"got {r['action']}")(recommend(e, "MSFT"))),
    ("TSLA (not held, Underweight) -> no_position_avoid", "decision", lambda e: True if recommend(e, "TSLA")["action"] == "no_position_avoid" else "wrong action"),
    ("NVDA recommendation has low confidence (self-contradicting source)", "calibration", lambda e: True if recommend(e, "NVDA")["confidence"] == "low" else "overconfident"),
]

# Live-agent cases: need a Gemini key; scored from the final answer and the trace.
AGENT = [  # (name, question, tools_expected, answer_must_match_all (regex), answer_must_not_match (regex))
    ("Holdings in one name across accounts", "How many Costco shares do I own in total?", {"portfolio_exposure"}, [r"2,?300"], []),
    ("Books vs custodian", "Do my own records match the bank statements?", {"reconcile_positions"}, [r"JPM", r"7,?520", r"7,?250"], []),
    ("Unknown company", "Should I buy Meta?", set(), [r"(?i)no (documents|data|information)|not (on file|in the)|cannot|can't|don't have"], [r"(?i)\bI recommend (buying|selling)|verdict: (buy|sell)"]),
    ("Broker disagreement shown", "Should I sell NVIDIA?", {"recommend"}, [r"Westbrook", r"Calder", r"(?i)disagree|conflict|mixed|contradict"], []),
    ("Most bullish broker", "Which broker is most bullish on Lilly, and what is their price target?", {"broker_views"}, [r"Calder", r"890"], []),
]
