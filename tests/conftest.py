import os

import pytest
from sqlalchemy import create_engine

from app.models import init_schema, md


@pytest.fixture()
def engine(tmp_path):
    url = os.getenv("TEST_DB_URL")  # e.g. mysql+pymysql://root@127.0.0.1:3306/altius_test
    eng = create_engine(url or f"sqlite:///{tmp_path/'t.db'}")
    if url:
        md.drop_all(eng)
    init_schema(eng)
    yield eng
    if url:
        md.drop_all(eng)
