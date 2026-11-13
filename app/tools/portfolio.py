"""Deterministic portfolio tools. Custodian statements are the record of quantities;
the family-office books are compared against them, never silently preferred."""
from sqlalchemy import select

from app.models import (corporate_actions, custodian_positions, positions_books, trades)


def _split_factor(engine, ticker: str, trade_date: str) -> float:
    with engine.connect() as c:
        rows = c.execute(select(corporate_actions).where(corporate_actions.c.ticker == ticker)).mappings().all()
    f = 1.0
    for r in rows:
        if "split" in r["action"].lower() and trade_date < r["effective"]:
            a, b = r["ratio"].split(":")
            f *= float(a) / float(b)
    return f


def split_adjust(engine, ticker: str, trade_date: str, qty: float, price: float):
    f = _split_factor(engine, ticker, trade_date)
    return qty * f, round(price / f, 4)


def _usd_cost(c, entity: str, ticker: str, row) -> float:
    if row["currency"] == "USD":
        return row["cost_basis"]
    # Foreign-currency custodian: take USD cost from the trade blotter (BUY amounts).
    amt = c.execute(select(trades.c.amount_usd).where(
        trades.c.entity == entity, trades.c.ticker == ticker, trades.c.type == "BUY")).scalars().all()
    return -sum(amt)


def portfolio_exposure(engine, as_of: str = "2026-06-30") -> dict:
    out = {}
    with engine.connect() as c:
        rows = c.execute(select(custodian_positions)).mappings().all()
        for r in rows:
            mv = r["quantity"] * r["price"]  # price is quoted in USD in both statements
            cost = _usd_cost(c, r["entity"], r["ticker"], r)
            p = out.setdefault(r["ticker"], dict(quantity=0.0, market_value_usd=0.0, cost_basis_usd=0.0,
                                                 entities={}, sources=[]))
            p["quantity"] += r["quantity"]; p["market_value_usd"] += mv; p["cost_basis_usd"] += cost
            p["entities"][r["entity"]] = dict(account=r["account"], quantity=r["quantity"],
                                              market_value_usd=mv, cost_basis_usd=cost)
            p["sources"].append(r["source_file"])
    total = sum(p["market_value_usd"] for p in out.values())
    for p in out.values():
        p["weight"] = p["market_value_usd"] / total
        p["unrealised_pnl_usd"] = p["market_value_usd"] - p["cost_basis_usd"]
    return dict(as_of=as_of, basis="custodian statements; weights over listed securities (cash excluded)",
                positions=out, totals=dict(market_value_usd=total,
                                           cost_basis_usd=sum(p["cost_basis_usd"] for p in out.values())))


def reconcile_positions(engine) -> list:
    with engine.connect() as c:
        books = {(r["entity"], r["ticker"]): r for r in c.execute(select(positions_books)).mappings()}
        cust = {(r["entity"], r["ticker"]): r for r in c.execute(select(custodian_positions)).mappings()}
    out = []
    for key in sorted(set(books) | set(cust)):
        b, k = books.get(key), cust.get(key)
        bq = b["quantity"] if b else None
        kq = k["quantity"] if k else None
        if bq != kq:
            out.append(dict(ticker=key[1], entity=key[0], field="quantity", books=bq, custodian=kq,
                            diff=(bq or 0) - (kq or 0) if bq is not None else None,
                            source=(k or b)["source_file"] if k else "books"))
    return out
