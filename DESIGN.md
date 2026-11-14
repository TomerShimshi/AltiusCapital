# Design

## What I built, and why
A chat agent over MySQL with two kinds of knowledge, because the questions are two kinds:
- **Numbers about the investor's own holdings** (exposure, P&L, mismatches) live in structured tables and
  are computed by deterministic tools. A language model must not do this arithmetic or recall it from text.
- **What documents say** (filings, releases, transcripts, broker notes) is retrieved with hybrid search:
  BM25 for exact figures and tickers, local sentence-transformer embeddings for meaning, fused with a
  numeric-aware weighting (a query containing digits leans on BM25).

The headline question is "buy or sell?". Family offices decide against a policy, not an optimiser, so the
`recommend` tool is rules-first: position cap and drift, broker/consensus evidence, and the investor's cost and
P&L produce hold/trim/add (or buy/avoid for unheld names) with confidence, rejected alternatives and
"what would change the call". The model only explains the result. No investment policy was supplied, so the
15% cap / 3% band are **placeholder assumptions**, shown in every answer.

## The agent's tools
| Tool | What it does | Why the agent needs it |
|---|---|---|
| `search_documents` | Hybrid retrieval with source, page and as-of date | Qualitative reasons and exact figures, with citations |
| `portfolio_exposure` | Combined holdings, USD value, weight, cost, P&L across both accounts | Answers about "my" position without model arithmetic |
| `reconcile_positions` | Books vs custodian differences | The two sources disagree; surface it, never pick silently |
| `broker_views` | Ratings per house, normalised, with flags and consensus | Scales are not comparable; show disagreement, don't average |
| `list_documents` | What is on file for a company, newest first, typed and dated | "Latest" and "last quarter" must come from document dates, not a guess |
| `recommend` | Rules-first hold/trim/add/avoid with evidence and rejected alternatives | The buy/sell question, made specific to this investor |

Operations: a model ladder over the Gemini free tier (strongest first; 429/5xx/404 cool a model down and the
request drops a rung; per-call timeout 20 s), and a trace table recording every model choice, fallback, tool
call and result, rendered as "Show the work". Live ingestion: folder watcher + upload endpoint, SHA-256 dedup,
text-layer first and OCR fallback.

## What I learned about the data
- Custodian statements and the family-office books **disagree**: JPM 7,250 vs 7,520 shares; the books' Positions
  sheet omits the Trust's 900 COST shares (COST is 2,300 in total). The custodian is treated as the record.
- NVDA had a 10-for-1 split; prices and pre-split trades are unadjusted. Trust is valued in CHF at the statement
  rate; its USD cost is taken from the trade blotter, not recomputed. Dividends there are net of 15% withholding.
- Three PDFs are scans with no text layer (an AMZN call transcript, a UNH Q2 2026 release, an XOM Q2 2025
  release, the latter with a misleading filename). OCR drops spaces, so glued words are split before indexing.
- Filenames and the first date in a file are poor signals: most earnings releases mention "Form 10-K" in their
  safe-harbour text, and scans carry OCR noise ("Ganuary 29"). Each document is therefore typed and dated
  from its first page (OCR-tolerant, statement date = period end), and every search result carries that date.
  After the fix all 57 documents have a date. Dates also separate old from new versions (Apple FY24 vs FY26).
- One exact duplicate (`MSFT FY26 Q2 ...` twice). Some vendor EPS values arrive as text (`"$4.82"`).
- Broker houses use incomparable rating scales and EPS bases (GAAP vs non-GAAP); the Calder & Rowe NVDA note
  contradicts itself (headline PT $165, rating box $240); the Halvard UNH note postdates the 30 Jun snapshot.
- The figure "$50.2 billion" legitimately appears in both NVIDIA's own release and the Westbrook note.

## How I know it works
- 63 tests, all passing: one suite per component (trace, loaders, portfolio, brokers, ingestion, retrieval,
  documents, ladder, recommend, agent), run on SQLite and MySQL (MySQL caught a column-length bug SQLite hid).
- A benchmark of **26 deterministic cases** whose expected values I computed independently from the source
  statements/spreadsheets (exact scoring, no LLM judge), covering each data trap above, plus **5 live-agent
  cases** scored from the answer text and the trace (right tools called, required facts present, citations
  present, no verdict for an unknown company). See `python -m benchmark.run`.
- Ten plain-language questions ("How did Microsoft do last quarter?", "What is my biggest risk?", "Should I buy
  Meta?") were run against the live system; answers, tools, models and tokens are in `reports/latest/`
  (`SUMMARY.md` is the one-page status; regenerate with `python -m benchmark.report --agent`).
- Live ingestion was checked with an invented document (`demo/`): dropped into the watched folder while the
  server ran, it was typed, dated and searchable in about 3 s, and the answer to "any new buyback?" changed
  from "none announced" to the new figures with a citation. This is also a test.
- A step-cap failure found in that testing (the model kept searching and the evidence was discarded) is fixed:
  on the last step the agent makes one tool-free call and answers from what it has.

## Cost
$0: Gemini free tier, local embeddings and OCR, MySQL in Docker. Tokens are recorded per model call in the
trace: about 5,000 per question on average in the sample run (2,000 to 9,000). The real cost of the free tier is
latency and availability (models time out or return 503: 10 fallbacks across 15 questions in the last run; the
lowest rungs also give thinner answers, though every figure still comes from tools), which is why the ladder exists.

## What I would do next
1. Decide per legal entity. The two accounts (an LLC at Northgate, a CHF trust at Banque Leman) are treated as one
   investor, as the brief describes, and limits apply to the combined portfolio. Splitting verdicts per entity
   needs each entity's own policy and tax position from the client; without them it would invent constraints.
   Model-in-the-loop tool-selection tests (a separate suite) come next.
2. Cash balances in exposure (weights are currently over listed securities only) and a time-aware portfolio
   (prices as of the question date; the data is a 30 Jun 2026 snapshot while some documents are later).
3. A real policy input (position caps, bands) from the client; risk-contribution once there is more price history.
4. Table-aware extraction of figures from filings so numeric comparisons are structured, not retrieved text.
5. Streaming responses, conversation memory, and an optional Phoenix/Langfuse export of the same traces.

## Deviations and limits
BM25 runs in-process (`rank_bm25`) over chunks stored in MySQL, not MySQL FULLTEXT (which is not BM25).
Tax effects are not modelled. Verdicts are analysis, not advice. The brief never says "buy or sell"; I read
"answers they can act on" that way, so the pipeline serves it, but the agent also answers plain factual questions.
