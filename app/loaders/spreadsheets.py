from datetime import datetime
from pathlib import Path

import openpyxl
from sqlalchemy import delete, insert

from app import models as m


def _d(v):
    return v.strftime("%Y-%m-%d") if isinstance(v, datetime) else (str(v) if v is not None else None)


def _f(v):
    """Coerce vendor numbers that sometimes arrive as text ('$4.82', '1,234')."""
    if v is None or isinstance(v, (int, float)):
        return v
    try:
        return float(str(v).replace("$", "").replace(",", "").strip())
    except ValueError:
        return None


def _rows(ws, header_first_cell):
    """Yield dict rows below the header row whose first cell equals header_first_cell."""
    it = ws.iter_rows(values_only=True)
    header = None
    for r in it:
        if header is None:
            if r and r[0] == header_first_cell:
                header = [str(h) if h is not None else "" for h in r]
            continue
        if any(v is not None for v in r):
            yield dict(zip(header, r))


def _wb(folder, name):
    return openpyxl.load_workbook(Path(folder) / name, data_only=True)


def load_spreadsheets(engine, folder) -> dict:
    out = {}
    with engine.begin() as c:
        for t in (m.positions_books, m.trades, m.prices, m.dividends, m.corporate_actions,
                  m.fx_rates, m.consensus_estimates, m.price_targets):
            c.execute(delete(t))

        wb = _wb(folder, "Holdings and trades.xlsx")
        rows = [dict(entity=r["Entity"], custodian=r["Custodian"], account=r["Account"],
                     ticker=r["Ticker"], quantity=r["Quantity"], avg_cost=r["Average cost (USD)"],
                     last_price=r["Last price (USD)"], market_value=r["Market value (USD)"],
                     note=r["Note"]) for r in _rows(wb["Positions"], "Entity")]
        c.execute(insert(m.positions_books), rows); out["positions_books"] = len(rows)
        trows = []
        for sheet, entity in (("Trades - Holdings LLC", "Harbor Oak Holdings LLC"),
                              ("Trades - Trust", "Harbor Oak 2019 Family Trust")):
            for r in _rows(wb[sheet], "Booking date"):
                trows.append(dict(entity=entity, booking_date=_d(r["Booking date"]),
                                  trade_date=_d(r["Trade date"]), ticker=r["Ticker"], type=r["Type"],
                                  quantity=r["Quantity"], price=r["Price"], amount_usd=r["Amount (USD)"],
                                  reference=r["Reference"], memo=r["Memo"]))
        c.execute(insert(m.trades), trows); out["trades"] = len(trows)

        wb = _wb(folder, "Prices.xlsx")
        prow = []
        for r in _rows(wb["Month-end closes"], "Date"):
            for k, v in r.items():
                if k != "Date" and v is not None:
                    prow.append(dict(date=_d(r["Date"]), ticker=k, close=v))
        c.execute(insert(m.prices), prow); out["prices"] = len(prow)
        drow = [dict(ticker=r["Ticker"], pay_date=_d(r["Pay date"]),
                     per_share=r["Dividend per share (USD)"], note=r["Note"])
                for r in _rows(wb["Dividends"], "Ticker")]
        c.execute(insert(m.dividends), drow); out["dividends"] = len(drow)
        carow = [dict(ticker=r["Ticker"], action=r["Action"], effective=_d(r["Effective date"]),
                      ratio=r["Ratio"]) for r in _rows(wb["Corporate actions"], "Ticker")]
        c.execute(insert(m.corporate_actions), carow); out["corporate_actions"] = len(carow)

        wb = _wb(folder, "FX rates.xlsx")
        frow = [dict(date=_d(r["Date"]), usd_chf=r["USD/CHF"], eur_usd=r["EUR/USD"])
                for r in _rows(wb["Month-end"], "Date")]
        c.execute(insert(m.fx_rates), frow); out["fx_rates"] = len(frow)

        wb = _wb(folder, "Consensus estimates.xlsx")
        erow = [dict(ticker=r["Ticker"], period=r["Fiscal period"], revenue_cons=r["Revenue consensus ($m)"],
                     eps_cons=_f(r["EPS consensus"]), eps_basis=r["EPS basis"], report_date=_d(r["Report date"]),
                     revenue_actual=r["Revenue actual ($m)"], eps_actual=_f(r["EPS actual"]),
                     eps_surprise=r["EPS surprise"]) for r in _rows(wb["Estimates"], "Ticker")]
        c.execute(insert(m.consensus_estimates), erow); out["consensus_estimates"] = len(erow)
        ptrow = [dict(ticker=r["Ticker"], consensus_pt=r["Consensus PT (USD)"], buy=r["Buy"], hold=r["Hold"],
                      sell=r["Sell"], last_price=r["Last price"]) for r in _rows(wb["Price targets"], "Ticker")]
        c.execute(insert(m.price_targets), ptrow); out["price_targets"] = len(ptrow)
    return out
