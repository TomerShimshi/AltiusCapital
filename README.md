# Equity Research Assistant

A chat agent for a family-office investor: ask in plain language about the companies you own, the ones
you are considering, and your own portfolio. Answers are grounded (every claim cites a document or
spreadsheet row), portfolio-aware, and every step is traced ("Show the work").
Design rationale: [DESIGN.md](DESIGN.md).

## Requirements
- Python 3.9+ (developed on 3.9)
- MySQL 8 (Docker or a local install)
- A free Gemini API key from Google AI Studio
- The client documents folder (`portfolio/`), not included in this repo

No Tesseract or other system OCR is needed: OCR runs in pure Python (rapidocr-onnxruntime).

## Setup
```bash
# 1. Python environment
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. MySQL - either Docker...
docker compose up -d            # creates database `altius` (root / root on 127.0.0.1:3306)
#    ...or a local server:  mysql -uroot -e "CREATE DATABASE altius CHARACTER SET utf8mb4"

# 3. Configuration
cp .env.example .env            # then edit: GEMINI_API_KEY=..., DB_URL=... (see below)

# 4. Put the client documents at assignment/portfolio/  (or set PORTFOLIO_DIR in .env)

# 5. Load everything (spreadsheets, statements, broker notes, all PDFs incl. OCR of scans)
python -m app.bootstrap         # first run downloads the embedding model (~90 MB)
```
`DB_URL` examples: Docker `mysql+pymysql://root:root@127.0.0.1:3306/altius`; local passwordless root
`mysql+pymysql://root@127.0.0.1:3306/altius` (this is the default if `DB_URL` is unset).
`HF_TOKEN` is optional (the default embedding model downloads without it).

## Run
```bash
python -m uvicorn app.api:app --port 8765
```
Open http://localhost:8765 . Try: "Should I sell NVIDIA?", "Do my books match the custodian statements?",
"Is Tesla a buy?". Use **Show the work** under any answer to see each model choice, fallback and tool call.

New documents: drop a PDF into the `portfolio/` folder (a watcher ingests it within ~5 s) or use
**Add a document** in the UI. Re-adding the same file is a no-op (content hash). Every document is typed and
dated from its first page (`as_of`), and the agent can list what is on file, newest first. To see it live, copy
`demo/Microsoft repurchase and Azure expansion Aug 2026.pdf` (an invented document) into `portfolio/` and ask
"Has Microsoft announced any new share buyback or Azure capacity plans recently?" before and after.
After upgrading the classifier on an existing database, run `python -m app.reclassify`.

## Tests and benchmark
```bash
pytest -q                                    # unit tests (SQLite); no API key needed
TEST_DB_URL=mysql+pymysql://root@127.0.0.1:3306/altius_test pytest -q   # same tests on MySQL
python -m benchmark.run                      # 26 deterministic cases against the loaded DB, no LLM
python -m benchmark.run --agent              # + 5 live-agent cases (uses the Gemini free tier)
python -m benchmark.report --agent           # everything above + 10 sample questions -> reports/latest/
```
**System status at a glance:** open [`reports/latest/SUMMARY.md`](reports/latest/SUMMARY.md) (test and benchmark
results, data loaded, models used) and [`reports/latest/sample_answers.md`](reports/latest/sample_answers.md)
(real answers with tools, models, tokens and sources). Regenerate them with the command above.
Free-tier rate limits are real: the agent falls back through a ladder of models
(`GEMINI_MODELS` in `.env`, strongest first) and tells the user when everything is limited.
Model availability on free keys changes; set `GEMINI_MODELS` to models that answer for your key.

## Layout
`app/loaders` structured data and statements · `app/ingest` dedup, OCR, classify, watch ·
`app/retrieval.py` BM25 + embeddings · `app/tools` portfolio, brokers, recommend ·
`app/llm.py` model ladder · `app/agent.py` tool loop · `app/api.py` + `app/static` service and UI ·
`benchmark/` evaluation · `tests/` unit tests.
