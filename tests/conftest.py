import pytest
from sqlalchemy import create_engine

from app.models import init_schema


@pytest.fixture()
def engine(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path/'t.db'}")
    init_schema(eng)
    return eng
