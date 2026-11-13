# Equity Research Assistant: Design

Status: DRAFT for approval. Items marked **[Assumption]** are my calls, not decisions made by the user.

## 1. Intent

Home assignment for Altius Capital (AI Engineer). Build a chat agent for the investor of a family office (Harbor Oak). The investor is non-technical and asks plain-language questions about companies they own, companies they are considering, and their own portfolio. Answers must be trustworthy and actionable. The typical question is "is this stock a buy or a sell, for me?".

The assignment is graded on what we choose to focus on, how we justify it (DESIGN.md), and a live demo plus Q&A. About 5 hours of work is budgeted, and the assignment says that is not enough to do everything.

All figures, people and events in the documents are fictional, so the agent must never answer from the model's own knowledge of the real companies.

## 2. Hard constraints (from the assignment)

- Backend in Python, database MySQL.
- New documents can arrive while the system is running.
- Runs on the reviewers' machines by following the README (clean machine, `docker compose up` for MySQL).
- Deliverable zip: source, `README.md`, `DESIGN.md` (1-2 pages: tools and why, what we learned about the data, how we know it works, cost, next steps).
- Free tooling expected: Gemini free tier (low rate limits), local sentence-transformers embeddings, Docling / pdfplumber / Tesseract, MySQL in Docker. HF token goes in `.env`; `.env` is never committed.

## 3. Goals, non-goals, anti-goals

Goals
- Grounded answers: every claim cites document + quote, or spreadsheet/statement + row.
- A buy/sell style recommendation that is specific to this investor's holdings.
- Visible reasoning: a "Show the work" trace of every agent step.
- Handle the traps in the data (section 5) explicitly.
- Evaluate: tool unit tests plus a small benchmark with independently computable answers.

Non-goals (mention in DESIGN.md, do not build)
- Tax advice, hedging structures (collars, exchange funds), real-time market data.
- Precise risk-contribution modelling (only about 31 monthly prices per stock).
- Langfuse/Phoenix export (later, if time).

Anti-goals (would be a failure even if it "works")
- A confident verdict with no source, or a number the model produced from memory.
- Silently picking one side when books and custodian disagree.
- Averaging broker ratings across incompatible scales.
- Answers that treat a stock in general and ignore the investor's position.

## 4. What the recon found (data)

Facts observed in `assignment/portfolio/`:
- About 60 PDFs: earnings releases, 10-K/10-Q, call transcripts, broker notes (Calder & Rowe, Westbrook, Halvard), custodian statements (Northgate, Banque Leman), plus 4 spreadsheets (Holdings and trades, Prices, FX rates, Consensus estimates).
- 3 PDFs have no text layer: `Doc_2026-02-06_scan.pdf`, `scan_20260730_1142.pdf`, `ExxonMobil 2Q25 earnings.pdf` (a scan with a clean filename). They need OCR and may be duplicates of each other.
- Exact duplicate: `Microsoft FY26 Q2 (1).pdf` = `MSFT FY26 Q2 earnings release.pdf`.
- Slide-style PDFs with little text: Tesla Investor Day, Lilly R&D Day, Costco Investor Overview.
- Held names: AAPL, MSFT, NVDA, AMZN, JPM, XOM, COST (Harbor Oak Holdings LLC at Northgate, account 4471-8820, USD) and UNH, COST (Harbor Oak 2019 Family Trust at Banque Leman, CH-5521.03, valued in CHF). Considering: TSLA, LLY (no positions; broker notes and company documents only).
- JPM: the family-office books say 7,520 shares, Northgate says 7,250 (likely transposition).
- COST: 1,400 shares at Northgate plus 900 at the Trust = 2,300. The books' Positions sheet lists only the Northgate lot.
- NVDA 10-for-1 split effective 10 June 2025. Prices.xlsx is unadjusted; pre-split trades are in pre-split units.
- Trust: CHF valuation (USD/CHF 0.7801 at 30 Jun 2026), cost converted at historical rates, dividends net of 15% US withholding (gross, tax, net on separate lines). Family office reports in USD, translate at the statement-date rate.
- Broker rating scales are not comparable (Buy/Hold/Sell; Overweight/Equal-weight/Underweight; Market Perform/Underperform). EPS basis differs (Calder & Rowe GAAP, Westbrook non-GAAP). The Calder & Rowe NVDA note contradicts itself (headline "PT $165" vs rating box $240).
- Consensus sheet: price targets, buy/hold/sell counts, quarterly estimates with surprise, as of 30 Jun 2026.
- Older and newer versions coexist (for example Apple FY2024 10-K next to FY26 results).

These findings are partial (first pages and structured sheets only). Ingestion work must verify them against full text.

## 5. Architecture

**Ingestion (live)**
- Watcher on `portfolio/` plus an upload endpoint. Content hash dedup. Classify each file: type, company/ticker, as-of date, source house, version (superseded flag).
- PDFs with a text layer: table-aware parsing (Docling or pdfplumber). Image-only and slide PDFs: OCR fallback (Tesseract). **[Assumption]**
- Chunks and metadata in MySQL. Retrieval is hybrid: BM25 (MySQL FULLTEXT) plus local sentence-transformers embeddings (small HF model, **[Assumption]** model to be chosen at build), scores merged. BM25 favours exact numbers and tickers, embeddings favour meaning.
- Spreadsheets and statements parse into structured tables (positions, trades, prices, dividends, FX, corporate actions, consensus, broker views). Differences between books and custodians are stored as reconciliation records, never overwritten.

**Agent and tools**
1. `search_documents`: hybrid retrieval with citations and as-of dates.
2. `portfolio_exposure`: combined holdings across both entities, split-adjusted, USD-normalised, P&L, weights, concentration.
3. `reconcile_positions`: books vs custodian statements; reports mismatches (JPM, COST).
4. `broker_views`: normalises ratings across houses, shows disagreement, price targets vs price, EPS basis.
5. `recommend`: the decision pipeline (section 6).

**LLM harness**
- Gemini free tier with a model ladder: strongest model first; on 429/quota, mark the model cooling down and retry one rung down; per-model RPM/RPD tracking so we skip before failing. **[Assumption]** Per-task ladders: strongest models reserved for final synthesis. Exact model names and limits to be checked at build time.
- Numbers come from tools, never model memory, so weaker models degrade explanation quality, not figures.

**Observability (must-have)**
- Every step is written to MySQL trace tables: question, model chosen and reason, fallbacks, tool calls with arguments and results, retrieved chunks with scores, latency, tokens, final answer and citations.
- The chat UI has a "Show the work" panel rendering a run from the trace. Export to Phoenix/Langfuse only if needed later.

**Delivery**
- FastAPI backend, simple web chat UI **[Assumption]**, `docker compose up` for MySQL. Stack defaults accepted as a baseline by the user and revisable after testing.

## 6. Recommendation pipeline (buy/sell for this investor)

Basis: family offices decide under an investment-policy framework (position limits, rebalancing bands, staged diversification), not by running a return optimiser. Pure mean-variance is avoided (needs return forecasts, unstable). This mapping to the agent is my extrapolation from vendor/educational sources.

Steps:
1. Policy check: combined position weight vs cap; drift.
2. Risk contribution: share of portfolio volatility, flagged low confidence (about 31 monthly prices).
3. Evidence score: normalised broker views, price vs targets, results vs consensus.
4. Position economics: cost basis, unrealised gain/loss, holding entity. Facts only, no tax advice.
5. Decision: hold / trim / add / exit, with rejected alternatives and the conditions that would change the call.

Rules decide, the model explains. Default limits are configurable and labelled as assumptions in every answer **[Assumption]** (no investment policy document exists in the files; the user agreed to configurable defaults). Output carries a confidence level, separates retrieved facts from judgement, and says so when sources conflict or are stale.

## 7. Evaluation

- One trace format feeds debugging, benchmarks and tests.
- Tool tests, layer 1 (no model): split adjustment, FX conversion at statement-date rate, reconciliation flags JPM 7,520 vs 7,250, COST combined, rating normalisation.
- Tool tests, layer 2 (model in the loop): given a plain-language question, does the model pick the right tool with sensible arguments. Small fast set, larger on-demand set, run against the real ladder.
- Benchmark: about 25-30 synthetic questions with answers computable independently from spreadsheets/statements (exact scoring, no LLM judge). Opinion questions use a rubric (cites both brokers, notes scale differences, no unsupported verdict). Planted traps: duplicate MSFT file, self-contradicting C&R note, scans, NVDA split.

## 8. Scope for ~5 hours

Build: ingestion, the five tools, decision pipeline, tracing, small benchmark, README, DESIGN.md.
Describe only: risk-contribution precision, hedging, external trace viewer.

## 9. Execution approach

Serial foundation first (MySQL schema, trace table, Gemini ladder), then parallel streams: (1) ingestion and retrieval, (2) structured data and portfolio tools incl. reconciliation, (3) agent and decision pipeline, (4) benchmark and UI. Each stream test-first. Model-in-the-loop tests are batched, not run in parallel, because of free-tier rate limits. Interfaces (table shapes, tool signatures) must be fixed in the plan before streams fan out.

## 10. Open items for the builder

- Exact Gemini model names and free-tier limits (verify at build).
- Embedding model choice and Docling vs pdfplumber after trying both on the real files.
- Default policy limits (position cap, drift band): placeholders until confirmed.
- Whether the three scans are true duplicates (needs OCR).
- Remote deliverable is a zip; the git repo excludes `.env` and should consider excluding client data under `assignment/portfolio/`.
