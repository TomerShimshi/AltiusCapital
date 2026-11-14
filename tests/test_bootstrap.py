from app.bootstrap import preflight


def test_missing_data_folder_gives_a_clear_message(engine, tmp_path):
    msg = preflight(engine, tmp_path / "nope")
    assert "PORTFOLIO_DIR" in msg and "nope" in msg


def test_folder_without_spreadsheets_gives_a_clear_message(engine, tmp_path):
    assert "Holdings and trades.xlsx" in preflight(engine, tmp_path)


def test_unreachable_database_gives_a_clear_message(tmp_path):
    from sqlalchemy import create_engine
    msg = preflight(create_engine("mysql+pymysql://root@127.0.0.1:1/none"), tmp_path)
    assert "DB_URL" in msg
