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


if __name__ == "__main__":
    print(bootstrap(), file=sys.stdout)
