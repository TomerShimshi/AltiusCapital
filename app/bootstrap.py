"""Load everything into the configured database: python -m app.bootstrap"""
import sys

from app import config
from app.db import get_engine
from app.ingest.pipeline import ingest_folder
from app.loaders.spreadsheets import load_spreadsheets
from app.loaders.statements import load_statements
from app.tools.brokers import load_broker_notes


def bootstrap(engine=None, folder=None) -> dict:
    engine = engine or get_engine()
    folder = folder or config.PORTFOLIO_DIR
    out = dict(tables=load_spreadsheets(engine, folder))
    out["custodian_positions"] = load_statements(engine, folder)
    out["broker_notes"] = load_broker_notes(engine, folder)
    res = ingest_folder(engine, folder)
    out["documents"] = {s: sum(1 for r in res if r["status"] == s) for s in ("new", "duplicate", "failed")}
    return out


def preflight(engine, folder):
    """A plain-language problem description, or None when we are ready to load."""
    from pathlib import Path
    from sqlalchemy import text
    try:
        with engine.connect() as c:
            c.execute(text("select 1"))
    except Exception as e:  # noqa: BLE001
        return (f"Cannot reach the database ({type(e).__name__}). Check DB_URL in .env and that MySQL is running "
                f"and the database exists (see README, step 2).")
    folder = Path(folder)
    if not folder.is_dir():
        return f"The documents folder {folder} does not exist. Put the client portfolio/ folder there or set PORTFOLIO_DIR in .env."
    if not (folder / "Holdings and trades.xlsx").exists():
        return f"{folder} does not contain 'Holdings and trades.xlsx'. Is PORTFOLIO_DIR pointing at the portfolio/ folder?"
    return None


if __name__ == "__main__":
    from sqlalchemy import create_engine
    problem = preflight(create_engine(config.DB_URL), config.PORTFOLIO_DIR)  # before init_schema, so errors are readable
    if problem:
        sys.exit(f"Setup problem: {problem}")
    eng = get_engine()
    print(bootstrap(eng), file=sys.stdout)
