import json
import time

from google.genai import types

from app.llm import AllModelsLimited
from app.retrieval import search_documents
from app.tools.brokers import broker_views
from app.tools.documents import list_documents
from app.tools.portfolio import portfolio_exposure, reconcile_positions
from app.tools.recommend import recommend
from app.trace import Tracer
from sqlalchemy import func, select

from app.models import documents

MAX_STEPS = 6

SYSTEM = """You are an equity research assistant for the investor of the Harbor Oak family office.
The investor is not technical: use plain language, short sentences, no jargon, USD amounts with thousands separators.

GROUNDING RULES (strict)
- All companies, figures, people and events in the documents are fictional. NEVER use your own knowledge of these companies. Use only tool results.
- Every number and claim must come from a tool result and be cited as [source, page] or [source]. If a tool returns no data or no documents, say so plainly ("There are no documents on file for X") and do not give a verdict.
- Prefer tools: portfolio_exposure / reconcile_positions for the investor's holdings and mismatches; broker_views for analyst opinions; search_documents for what company filings, releases and transcripts say; recommend for buy/sell/hold style questions (and call search_documents too for qualitative reasons).
- Dates: every document carries a date (as_of). "Latest", "last quarter" and "recent" mean the newest document by as_of, never your assumption. If unsure which documents exist for a company, call list_documents first, then search. Compare periods by their dates, and say when a document is older than the newest one on file or has no date.
- Broker rating scales are not comparable across houses; say when houses disagree and never average them. Mention flags such as a note contradicting itself or postdating the 30 Jun 2026 snapshot.
- When the books and the custodian statement disagree, say so and say which source you used (the custodian statement is the record).

FOR "should I buy/sell/hold X?" ANSWER IN THIS ORDER
1. Verdict: the action and confidence in one sentence.
2. What the evidence says (brokers side by side, consensus, results vs expectations), with citations.
3. What it means for you: position size, share of portfolio, cost and gain/loss, which account.
4. Why this action, and the alternatives considered and rejected.
5. What would change the call.
6. Assumptions (the position limits used are placeholder assumptions, not the client's policy). One short line: this is analysis, not personalised tax or legal advice.
"""

_S = types.Schema
TOOLS = [types.Tool(function_declarations=[
    types.FunctionDeclaration(name="search_documents",
        description="Search the ingested documents (filings, press releases, transcripts, broker notes, statements). Returns cited text chunks.",
        parameters=_S(type="OBJECT", properties={
            "query": _S(type="STRING", description="what to look for; include exact figures or phrases when known"),
            "ticker": _S(type="STRING", description="optional ticker filter, e.g. NVDA")}, required=["query"])),
    types.FunctionDeclaration(name="list_documents",
        description="Which documents are on file, newest first, with type and date; marks the latest of each type. Use to find 'the latest results/call/10-K' or to compare periods.",
        parameters=_S(type="OBJECT", properties={
            "ticker": _S(type="STRING", description="optional, e.g. MSFT"),
            "doc_type": _S(type="STRING", description="optional: earnings_release, transcript, 10-K, 10-Q, broker_note, presentation_or_event, custodian_statement")})),
    types.FunctionDeclaration(name="portfolio_exposure",
        description="The investor's combined holdings across both accounts: quantity, USD value, weight, cost basis, unrealised P&L. Takes no arguments.",
        parameters=_S(type="OBJECT", properties={})),
    types.FunctionDeclaration(name="reconcile_positions",
        description="Differences between the family office's own books and the custodian statements. Takes no arguments.",
        parameters=_S(type="OBJECT", properties={})),
    types.FunctionDeclaration(name="broker_views",
        description="Analyst ratings and price targets per broker house for a ticker, normalised, plus consensus and flags.",
        parameters=_S(type="OBJECT", properties={"ticker": _S(type="STRING")}, required=["ticker"])),
    types.FunctionDeclaration(name="recommend",
        description="Rules-based hold/trim/add/no-position view for a ticker combining the investor's holding, broker views and consensus, with evidence, rejected alternatives and what would change the call.",
        parameters=_S(type="OBJECT", properties={"ticker": _S(type="STRING")}, required=["ticker"])),
])]


def _search(engine, query, ticker=None):
    res = search_documents(engine, query, ticker=ticker, k=5)
    return [dict(source=r["doc"], page=r["page"], doc_type=r["doc_type"], as_of=r["as_of"],
                 ticker=r["ticker"], text=r["text"][:700]) for r in res] or {"no_documents_found": True}


DISPATCH = {
    "search_documents": _search,
    "list_documents": lambda e, ticker=None, doc_type=None: list_documents(e, ticker, doc_type),
    "portfolio_exposure": lambda e: portfolio_exposure(e),
    "reconcile_positions": lambda e: reconcile_positions(e),
    "broker_views": lambda e, ticker: broker_views(e, ticker),
    "recommend": lambda e, ticker: recommend(e, ticker),
}


def _citations(name, result):
    out = []
    if name == "search_documents" and isinstance(result, list):
        out = [dict(source=r["source"], page=r["page"], quote=r["text"][:200]) for r in result]
    elif name == "broker_views":
        out = [dict(source=h["source"], quote=f"{h['house']}: {h['rating']}, PT {h['price_target']}") for h in result.get("houses", [])]
    elif name == "recommend":
        out = [dict(source=e["source"], quote=e["detail"]) for e in result.get("evidence", [])]
    elif name == "portfolio_exposure":
        srcs = {s for p in result["positions"].values() for s in p["sources"]}
        out = [dict(source=s, quote="custodian statement position") for s in sorted(srcs)]
    elif name == "reconcile_positions":
        out = [dict(source=r["source"], quote=f"{r['ticker']} books {r['books']} vs custodian {r['custodian']}") for r in result]
    return out


def _json(o):
    return json.loads(json.dumps(o, default=str))


def _system(engine) -> str:
    with engine.connect() as c:
        newest = c.execute(select(func.max(documents.c.as_of)).where(documents.c.status == "ok")).scalar()
    return SYSTEM + (f"\nDATA DATES: positions and prices are as of 30 Jun 2026; the newest document on file is dated "
                     f"{newest}. You have no other source of today's date.\n" if newest else "")


class Agent:
    def __init__(self, engine, ladder):
        self.engine, self.ladder, self.tracer = engine, ladder, Tracer(engine)

    def answer(self, question: str) -> dict:
        rid = self.tracer.start_run(question)
        contents = [types.Content(role="user", parts=[types.Part(text=question)])]
        cites, text = [], None
        try:
            for _ in range(MAX_STEPS):
                res = self.ladder.generate(rid, contents, system=_system(self.engine), tools=TOOLS)
                if not res.calls:
                    text = res.text.strip() or "I could not produce an answer."
                    break
                contents.append(res.content or types.Content(role="model", parts=[
                    types.Part(function_call=types.FunctionCall(name=c["name"], args=c["args"])) for c in res.calls]))
                parts = []
                for c in res.calls:
                    t0 = time.time()
                    try:
                        result = _json(DISPATCH[c["name"]](self.engine, **c["args"]))
                    except Exception as e:  # noqa: BLE001
                        result = {"error": f"{type(e).__name__}: {e}"}
                    cites += _citations(c["name"], result) if "error" not in result else []
                    self.tracer.step(rid, "tool", c["name"], dict(args=c["args"], result=result),
                                     ms=int((time.time() - t0) * 1000))
                    parts.append(types.Part.from_function_response(name=c["name"], response={"result": result}))
                contents.append(types.Content(role="user", parts=parts))
            else:
                # Step budget spent: force one last tool-free call so the evidence gathered is not wasted.
                contents.append(types.Content(role="user", parts=[types.Part(text=(
                    "Stop searching. Answer now using only what you have retrieved, in the usual structure. "
                    "Say plainly what you could not find."))]))
                res = self.ladder.generate(rid, contents, system=_system(self.engine), tools=None)
                text = res.text.strip() if not res.calls and res.text.strip() else (
                    "I could not finish this question within the step limit; please try a narrower question.")
        except AllModelsLimited as e:
            text = (f"The AI service is rate-limited right now (free tier). Please try again in about "
                    f"{int(e.retry_after_s)} seconds.")
            self.tracer.step(rid, "error", "AllModelsLimited", dict(retry_after_s=e.retry_after_s))
        seen, uniq = set(), []
        for c in cites:
            k = (c["source"], c.get("quote"))
            if k not in seen:
                seen.add(k); uniq.append(c)
        self.tracer.finish_run(rid, text, uniq)
        return dict(run_id=rid, answer=text, citations=uniq)
