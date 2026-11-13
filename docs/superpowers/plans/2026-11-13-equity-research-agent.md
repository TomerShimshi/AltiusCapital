# Equity Research Assistant Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (native, inline) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** A chat agent (Python + MySQL) that answers grounded, portfolio-aware buy/sell questions for the Harbor Oak family office, with full step tracing.

**Architecture:** Structured data (positions, trades, prices, FX, consensus, statements) lives in MySQL tables behind deterministic tools; PDFs are ingested into MySQL chunks and retrieved with hybrid BM25 + local embeddings. A Gemini model-ladder agent calls five tools; every step is written to trace tables and rendered in a "Show the work" panel.

**Tech Stack:** Python (venv), SQLAlchemy + PyMySQL, MySQL 8, pdfplumber (+ rapidocr-onnxruntime and pypdfium2 for scans), rank_bm25, sentence-transformers, google-genai, FastAPI, vanilla HTML/JS UI, pytest.

**Spec:** `docs/superpowers/specs/2026-11-13-equity-research-agent-design.md`

## Global Constraints

- Backend Python, database MySQL (reviewers run `docker compose up`; locally here MySQL runs from a binary in gitignored `.local/`).
- New documents can arrive while running (watcher + upload endpoint, content-hash dedup).
- Runs from README on a clean machine; `.env` never committed (`GEMINI_API_KEY`, `HF_TOKEN`, `DB_URL`).
- Never answer from model memory about the companies; numbers come from tools; every claim cites a source.
- Default policy limits are configurable and labelled as assumptions in every recommendation.
- Source data under `assignment/` is client material: never committed or pushed.
- Deviation from spec: BM25 uses `rank_bm25` over MySQL-stored chunks (index rebuilt on ingest), because MySQL FULLTEXT is not BM25. Note this in DESIGN.md.

## Review Focus

- Ticker in lowercase or company-name form ("Nvidia") resolves to the same ticker.
- Question about a ticker not in the data (e.g. "Should I buy Meta?") returns "no documents on file", never an invented answer.
- Empty retrieval result: the agent says so and does not give a verdict.
- Gemini 429 on every rung: the user gets a clear "rate-limited, retry in N s" message, and the trace records it.
- Re-ingesting the same file (or a renamed copy) creates no duplicate chunks.
- A scan that OCR cannot read is recorded as `status=failed` and surfaced, not silently dropped.

---

### Task 1: Foundation: config, schema, trace logger

**Files:** Create `app/config.py`, `app/db.py`, `app/models.py`, `app/trace.py`, `tests/test_trace.py`, `requirements.txt`, `docker-compose.yml`, `.env.example`
**Interfaces:**
- Produces: `get_engine() -> Engine`, `init_schema(engine) -> None`; tables `documents, chunks, positions_books, trades, prices, dividends, corporate_actions, fx_rates, consensus_estimates, price_targets, broker_notes, custodian_positions, reconciliation, trace_runs, trace_steps`; `Tracer(engine).start_run(question) -> run_id`, `Tracer.step(run_id, kind, name, payload: dict, model: str | None = None, ms: int = 0) -> None`, `Tracer.finish_run(run_id, answer: str, citations: list[dict]) -> None`, `Tracer.get_run(run_id) -> dict` (steps ordered).
- [ ] Write failing test: start_run, two steps, finish_run; `get_run` returns steps in order with payloads and the answer.
- [ ] Run `pytest tests/test_trace.py -v`, expect FAIL.
- [ ] Implement config/db/models/trace (SQLAlchemy Core, JSON columns).
- [ ] Run test, expect PASS. Commit.

### Task 2: Structured loaders (spreadsheets + custodian statements)

**Files:** Create `app/loaders/spreadsheets.py`, `app/loaders/statements.py`, `tests/test_loaders.py`
**Interfaces:**
- Produces: `load_spreadsheets(engine, folder: Path) -> dict[str, int]` (row counts per table); `parse_northgate(text: str) -> list[dict]` and `parse_banque_leman(text: str) -> list[dict]` returning `{ticker, quantity, price, market_value, cost_basis, entity, account, as_of, source_file}`; `load_statements(engine, folder) -> int`.
- [ ] Tests (against real files): Positions has 8 rows; JPM books qty 7520; Northgate parse yields JPM 7250 and 7 positions; Banque Leman parse yields UNH 2600 and COST 900, valuation rate 0.7801; NVDA corporate action 10:1 on 2025-06-10.
- [ ] Implement loaders (openpyxl, pdfplumber text + regex). Idempotent (replace by source_file).
- [ ] Run, PASS, commit.

### Task 3: Portfolio tools (exposure, reconcile)

**Files:** Create `app/tools/portfolio.py`, `tests/test_portfolio.py`
**Interfaces:**
- Produces: `portfolio_exposure(engine, as_of: str = "2026-06-30") -> dict` with per-ticker combined `quantity, market_value_usd, weight, cost_basis_usd, unrealised_pnl_usd, entities` and totals; `reconcile_positions(engine) -> list[dict]` of `{ticker, field, books, custodian, diff, entity, source}`; `split_adjust(ticker, trade_date, qty, price) -> (qty, price)`.
- [ ] Tests: COST combined quantity 2300 (1400 + 900); JPM mismatch 7520 vs 7250 reported; NVDA trade of 1800 @ 779.70 on 2024-03-06 adjusts to 18000 @ 77.97; Trust values converted at 0.7801 to USD; weights sum to 1 over securities.
- [ ] Implement; Banque Leman CHF cost shown with its stated historical-rate note, not recomputed.
- [ ] Run, PASS, commit.

### Task 4: Broker views and rating normalisation

**Files:** Create `app/tools/brokers.py`, `tests/test_brokers.py`
**Interfaces:**
- Produces: `normalise_rating(house: str, rating: str) -> Literal["positive","neutral","negative"]`; `broker_views(engine, ticker: str) -> dict` with per-house rating (raw + normalised), PT, date, EPS basis, consensus PT, counts, price, implied upside, and `flags` (self-contradiction, scale caveat).
- [ ] Tests: Buy/Overweight → positive; Hold/Equal-weight/Market Perform → neutral; Underperform/Underweight → negative; NVDA shows C&R positive PT 240 vs Westbrook neutral PT 155 and a `pt_conflict` flag for the C&R note (headline 165 vs box 240); LLY shows three houses.
- [ ] Implement; broker note details parsed from PDFs in Task 5 ingestion (`broker_notes`), sheet used as fallback.
- [ ] Run, PASS, commit.

### Task 5: Document ingestion (live)

**Files:** Create `app/ingest/pipeline.py`, `app/ingest/classify.py`, `app/ingest/ocr.py`, `app/ingest/watcher.py`, `tests/test_ingest.py`
**Interfaces:**
- Produces: `ingest_file(engine, path: Path) -> dict` (`{status: "new"|"duplicate"|"failed", doc_id, chunks, doc_type, ticker}`); `classify(text: str, filename: str) -> dict` (`doc_type, ticker, house, as_of`); `ocr_pdf(path) -> str`; `watch(engine, folder, interval=5)`.
- [ ] Tests: ingesting `MSFT FY26 Q2 earnings release.pdf` then `Microsoft FY26 Q2 (1).pdf` yields one `new` and one `duplicate`; a scan returns text via OCR or `failed` with a reason; Westbrook NVDA note classifies as `broker_note`, ticker NVDA, house Westbrook; dropping a new file in a temp watched folder ingests it within 10 s.
- [ ] Implement: sha256 dedup, pdfplumber first, OCR fallback when text length is below threshold, chunk about 800 chars with 100 overlap, preserve page numbers.
- [ ] Run, PASS, commit.

### Task 6: Hybrid retrieval

**Files:** Create `app/retrieval.py`, `tests/test_retrieval.py`
**Interfaces:**
- Consumes: `chunks` from Task 5.
- Produces: `search_documents(engine, query: str, ticker: str | None = None, k: int = 6) -> list[dict]` with `{doc, page, text, score_bm25, score_vec, score}` merged by reciprocal rank fusion; index refreshes after ingest.
- [ ] Tests: query "Q1 FY2027 revenue guidance" with ticker NVDA returns an NVDA document; exact-number query "$50.2 billion" finds the Westbrook note via BM25; unknown ticker returns `[]`.
- [ ] Implement with rank_bm25 + sentence-transformers (small model chosen at build), embeddings stored as float32 blobs.
- [ ] Run, PASS, commit.

### Task 7: LLM ladder

**Files:** Create `app/llm.py`, `tests/test_llm.py`
**Interfaces:**
- Produces: `class Ladder(models: list[str], client, tracer)` with `generate(run_id, messages, tools=None, task="chat") -> LLMResult`; on 429/quota marks the model cooling for a window and retries the next rung; raises `AllModelsLimited(retry_after_s)` when none are available.
- [ ] Tests with a fake client: rung 1 raises 429, rung 2 answers, trace records fallback with reason; all rungs 429 raises `AllModelsLimited`; cooled model is skipped on the next call.
- [ ] Implement against `google-genai`; model names taken from config (verified at build).
- [ ] Run, PASS, commit.

### Task 8: Recommendation pipeline

**Files:** Create `app/tools/recommend.py`, `app/policy.py`, `tests/test_recommend.py`
**Interfaces:**
- Consumes: Tasks 3, 4, 6.
- Produces: `DEFAULT_POLICY = {"max_position_weight": 0.15, "drift_band": 0.03}` (assumptions); `recommend(engine, ticker: str, policy: dict = DEFAULT_POLICY) -> dict` with `action` in `hold|trim|add|exit|no_position_buy|no_position_avoid`, `confidence`, `rules_fired`, `rejected_alternatives`, `would_change_if`, `evidence` (citations), `assumptions`.
- [ ] Tests: over-cap position with neutral broker view yields `trim` and cites the weight rule; UNH (underperform rating, unrealised loss) fires the negative-evidence rule and reports the loss as a fact; TSLA (not held) returns a `no_position_*` action; conflicting sources lower confidence and appear in `would_change_if`.
- [ ] Implement as deterministic rules; the model only explains.
- [ ] Run, PASS, commit.

### Task 9: Agent loop and API

**Files:** Create `app/agent.py`, `app/api.py`, `app/static/index.html`, `tests/test_agent.py`
**Interfaces:**
- Produces: `answer(question: str) -> {run_id, answer, citations}`; `POST /chat`, `GET /trace/{run_id}`, `POST /upload`; UI with chat and "Show the work" panel.
- [ ] Tests with a scripted fake model: a portfolio question triggers `portfolio_exposure`; an unknown ticker yields "no documents on file"; `AllModelsLimited` returns a friendly message with the trace recorded; answers include citations.
- [ ] Implement tool-calling loop (max 6 steps), system prompt enforcing grounding and the fixed answer structure.
- [ ] Run, PASS, commit.

### Task 10: Benchmark, README, DESIGN.md

**Files:** Create `benchmark/cases.yaml`, `benchmark/run.py`, `README.md`, `DESIGN.md`
- [ ] Write about 25 cases with exact, independently computed answers (COST total 2300, JPM mismatch, NVDA split-adjusted cost, Trust unrealised in USD, rating normalisation, duplicate handling), plus rubric cases for buy/sell.
- [ ] `python -m benchmark.run` scores from traces and prints a table; deterministic cases run without an LLM.
- [ ] README with clean-machine setup; DESIGN.md (1-2 pages) covering tools, data findings, evaluation, cost, next steps.
- [ ] Commit.

---

## Self-Review

- Spec coverage: ingestion (T5), five tools (T3, T4, T6, T8, plus search), ladder (T7), tracing (T1, T9 UI), evaluation (T10 plus per-task tests), delivery (T1, T10). Gaps: model-in-the-loop tool-selection tests need a Gemini key; they live in `tests/live/` and are skipped without one.
- Deviation noted: BM25 via `rank_bm25`, not MySQL FULLTEXT.
