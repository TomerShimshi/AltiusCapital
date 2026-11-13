import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DB_URL = os.getenv("DB_URL", "mysql+pymysql://root@127.0.0.1:3306/altius")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
HF_TOKEN = os.getenv("HF_TOKEN", "")
PORTFOLIO_DIR = Path(os.getenv("PORTFOLIO_DIR", ROOT / "assignment" / "portfolio"))
# Model ladder, strongest first. Verify names/limits against current free tier.
GEMINI_MODELS = [m for m in os.getenv(
    "GEMINI_MODELS", "gemini-3.8-flash,gemini-3.7-flash,gemini-3.5-flash,gemini-3.1-flash-lite,gemini-3.5-flash-lite").split(",") if m]
EMBED_MODEL = os.getenv("EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
