from sqlalchemy import (JSON, Column, DateTime, Float, ForeignKey, Integer,
                        MetaData, String, Table, Text, LargeBinary, func)

md = MetaData()
S = lambda n=64: String(n)  # noqa: E731

documents = Table("documents", md,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("sha256", S(64), unique=True, nullable=False),
    Column("filename", S(255)), Column("doc_type", S(32)), Column("ticker", S(16)),
    Column("house", S(64)), Column("as_of", S(16)), Column("status", S(16)),
    Column("detail", Text), Column("created", DateTime, server_default=func.now()))
chunks = Table("chunks", md,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("doc_id", Integer, ForeignKey("documents.id")), Column("page", Integer),
    Column("text", Text), Column("embedding", LargeBinary))
positions_books = Table("positions_books", md,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("entity", S(128)), Column("custodian", S(128)), Column("account", S(32)),
    Column("ticker", S(16)), Column("quantity", Float), Column("avg_cost", Float),
    Column("last_price", Float), Column("market_value", Float), Column("note", Text))
trades = Table("trades", md,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("entity", S(128)), Column("booking_date", S(16)), Column("trade_date", S(16)),
    Column("ticker", S(16)), Column("type", S(8)), Column("quantity", Float),
    Column("price", Float), Column("amount_usd", Float), Column("reference", S(64)),
    Column("memo", Text))
prices = Table("prices", md,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("date", S(16)), Column("ticker", S(16)), Column("close", Float))
dividends = Table("dividends", md,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("ticker", S(16)), Column("pay_date", S(16)), Column("per_share", Float),
    Column("note", Text))
corporate_actions = Table("corporate_actions", md,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("ticker", S(16)), Column("action", S(64)), Column("effective", S(16)),
    Column("ratio", S(16)))
fx_rates = Table("fx_rates", md,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("date", S(16)), Column("usd_chf", Float), Column("eur_usd", Float))
consensus_estimates = Table("consensus_estimates", md,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("ticker", S(16)), Column("period", S(32)), Column("revenue_cons", Float),
    Column("eps_cons", Float), Column("eps_basis", S(64)), Column("report_date", S(16)),
    Column("revenue_actual", Float), Column("eps_actual", Float), Column("eps_surprise", Float))
price_targets = Table("price_targets", md,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("ticker", S(16)), Column("consensus_pt", Float), Column("buy", Integer),
    Column("hold", Integer), Column("sell", Integer), Column("last_price", Float))
broker_notes = Table("broker_notes", md,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("date", S(16)), Column("house", S(64)), Column("ticker", S(16)),
    Column("rating", S(32)), Column("price_target", Float), Column("analyst", S(64)),
    Column("eps_basis", S(64)), Column("source", S(255)), Column("flags", JSON))
custodian_positions = Table("custodian_positions", md,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("entity", S(128)), Column("account", S(32)), Column("ticker", S(16)),
    Column("quantity", Float), Column("price", Float), Column("market_value", Float),
    Column("cost_basis", Float), Column("currency", S(8)), Column("fx_rate", Float),
    Column("as_of", S(16)), Column("source_file", S(255)))
reconciliation = Table("reconciliation", md,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("ticker", S(16)), Column("field", S(32)), Column("books", Float),
    Column("custodian", Float), Column("diff", Float), Column("entity", S(128)),
    Column("source", S(255)))
trace_runs = Table("trace_runs", md,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("question", Text), Column("answer", Text), Column("citations", JSON),
    Column("started", DateTime, server_default=func.now()), Column("finished", DateTime))
trace_steps = Table("trace_steps", md,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("run_id", Integer, ForeignKey("trace_runs.id")), Column("seq", Integer),
    Column("kind", S(16)), Column("name", S(128)), Column("model", S(64)),
    Column("payload", JSON), Column("ms", Integer),
    Column("created", DateTime, server_default=func.now()))


def init_schema(engine) -> None:
    md.create_all(engine)
