import threading
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import func, select

from app import config
from app.agent import Agent
from app.db import get_engine
from app.ingest.pipeline import ingest_file
from app.ingest.watcher import watch
from app.llm import Ladder, gemini_call
from app.models import documents
from app.trace import Tracer

app = FastAPI(title="Equity Research Assistant")
engine = get_engine()
_ladder = Ladder(config.GEMINI_MODELS, gemini_call(), Tracer(engine))
_agent = Agent(engine, _ladder)
_lock = threading.Lock()  # free-tier friendly: one model call chain at a time


class Ask(BaseModel):
    question: str


@app.on_event("startup")
def _start_watcher():
    if config.PORTFOLIO_DIR.exists():
        threading.Thread(target=watch, args=(engine, config.PORTFOLIO_DIR, 5.0), daemon=True).start()


@app.post("/chat")
def chat(body: Ask):
    if not body.question.strip():
        raise HTTPException(400, "empty question")
    with _lock:
        return _agent.answer(body.question.strip())


@app.get("/trace/{run_id}")
def trace(run_id: int):
    try:
        return Tracer(engine).get_run(run_id)
    except Exception:  # noqa: BLE001
        raise HTTPException(404, "no such run")


@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "PDF files only")
    dest = Path(config.PORTFOLIO_DIR) / Path(file.filename).name
    dest.write_bytes(await file.read())
    return ingest_file(engine, dest)


@app.get("/documents")
def docs():
    with engine.connect() as c:
        rows = c.execute(select(documents.c.status, func.count()).group_by(documents.c.status)).all()
    return {s: n for s, n in rows}


@app.get("/")
def index():
    return FileResponse(Path(__file__).parent / "static" / "index.html")
