from sqlalchemy import create_engine

from app import config
from app.models import init_schema


def get_engine(url: str = None):
    eng = create_engine(url or config.DB_URL, pool_pre_ping=True)
    init_schema(eng)
    return eng
