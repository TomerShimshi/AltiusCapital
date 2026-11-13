"""Rules-first recommendation. The rules decide; the model only explains the result."""
from sqlalchemy import select

from app.models import consensus_estimates
from app.policy import DEFAULT_POLICY
from app.tools.brokers import broker_views
from app.tools.portfolio import portfolio_exposure

_DIR = {"positive": 1.0, "neutral": 0.0, "negative": -1.0}


def _clamp(x, lo=-1.0, hi=1.0):
    return max(lo, min(hi, x))


def _evidence(engine, ticker):
    bv = broker_views(engine, ticker)
    ev, parts = [], []
    latest = {}
    for h in bv["houses"]:           # latest note per house
        latest[h["house"]] = h
    for h in latest.values():
        ev.append(dict(source=f"{h['house']} ({h['source']})", date=h["date"],
                       detail=f"{h['rating']} (reads {h['normalised']}), PT ${h['price_target']:.0f}"
                              + (f"; flags: {', '.join(h['flags'])}" if h["flags"] else "")))
    if latest:
        parts.append((0.5, sum(_DIR[h["normalised"]] for h in latest.values()) / len(latest)))
    c = bv["consensus"]
    if c:
        tot = (c["buy"] + c["hold"] + c["sell"]) or 1
        upside = c["consensus_pt"] / c["last_price"] - 1
        ev.append(dict(source="Consensus estimates.xlsx (Price targets)", date="2026-06-30",
                       detail=f"{c['buy']} buy / {c['hold']} hold / {c['sell']} sell; consensus PT "
                              f"${c['consensus_pt']:.0f} vs price ${c['last_price']:.2f} ({upside:+.1%})"))
        parts += [(0.25, (c["buy"] - c["sell"]) / tot), (0.25, _clamp(upside / 0.2))]
    with engine.connect() as cn:
        sur = [r for r in cn.execute(select(consensus_estimates.c.eps_surprise).where(
            consensus_estimates.c.ticker == ticker, consensus_estimates.c.eps_surprise.is_not(None))
            .order_by(consensus_estimates.c.report_date.desc()).limit(4)).scalars()]
    if sur:
        ev.append(dict(source="Consensus estimates.xlsx (Estimates)", date="2026-06-30",
                       detail=f"average EPS surprise last {len(sur)} quarters {sum(sur)/len(sur):+.1%}"))
    w = sum(p[0] for p in parts)
    score = sum(p[0] * p[1] for p in parts) / w if w else 0.0
    return bv, ev, score, len(latest)


def recommend(engine, ticker: str, policy: dict = DEFAULT_POLICY) -> dict:
    ticker = ticker.upper()
    bv, evidence, score, n_houses = _evidence(engine, ticker)
    pos = portfolio_exposure(engine)["positions"].get(ticker)
    assumptions = [f"Assumption: max position weight {policy['max_position_weight']:.0%} and drift band "
                   f"{policy['drift_band']:.0%} are placeholder defaults; no investment policy statement was provided.",
                   "Weights are over listed securities at custodian prices of 30 Jun 2026; cash is excluded.",
                   "Not tax advice; tax effects of selling are not modelled."]
    if not evidence and not pos:
        return dict(ticker=ticker, action="no_data", confidence="none", rules_fired=[], facts={},
                    evidence=[], conflicts=[], rejected_alternatives=[], would_change_if=[],
                    assumptions=assumptions, score=0.0,
                    summary=f"No documents or data on file for {ticker}.")
    conflicts = list(bv["flags"])
    for h in bv["houses"]:
        conflicts += [f for f in h["flags"] if f not in conflicts]
    conflicts = [c for c in dict.fromkeys(conflicts) if c != "ratings_not_comparable"] + (
        ["ratings_not_comparable"] if "ratings_not_comparable" in bv["flags"] else [])
    rules, facts = [], {}
    cap, band = policy["max_position_weight"], policy["drift_band"]
    if pos:
        facts = dict(weight=pos["weight"], market_value_usd=pos["market_value_usd"], quantity=pos["quantity"],
                     cost_basis_usd=pos["cost_basis_usd"], unrealised_pnl_usd=pos["unrealised_pnl_usd"],
                     entities=list(pos["entities"]))
        if pos["weight"] > cap:
            rules.append("position_over_cap")
        if pos["unrealised_pnl_usd"] < 0:
            rules.append("unrealised_loss")
    if any(h["normalised"] == "negative" for h in bv["houses"]):
        rules.append("negative_broker_view")
    if score >= 0.4:
        rules.append("positive_evidence")
    elif score <= -0.4:
        rules.append("negative_evidence")

    if pos:
        if "position_over_cap" in rules:
            action = "trim"
        elif score <= -0.5:
            action = "trim"
        elif score >= 0.5 and pos["weight"] < cap - band:
            action = "add"
        else:
            action = "hold"
    else:
        action = "no_position_buy" if score >= 0.4 else "no_position_avoid" if score <= -0.4 else "no_position_watch"

    material = [c for c in conflicts if c != "ratings_not_comparable"]
    has_consensus = any(e["source"].startswith("Consensus estimates.xlsx (Price") for e in evidence)
    if not evidence or "pt_conflict" in conflicts:
        confidence = "low"
    elif n_houses >= 2 and not material and has_consensus:
        confidence = "high"
    else:
        confidence = "medium"

    alts = {"trim": "Trim: ", "hold": "Hold: ", "add": "Add: ", "exit": "Exit: "}
    reason = {}
    if pos:
        reason["trim"] = ("not required by policy or evidence" if action != "trim" else None)
        reason["add"] = ("position already at or above cap" if pos["weight"] >= cap - band else "evidence not strong enough")
        reason["hold"] = ("rules point to reducing the position" if action == "trim" else None)
        reason["exit"] = "evidence is not negative enough to justify a full exit; a partial trim is the proportionate step"
    rejected = [dict(action=a, why=w) for a, w in reason.items() if w and a != action]
    would = []
    if "houses_disagree" in conflicts:
        would.append("Brokers disagree (houses_disagree): a convergence of ratings would change confidence.")
    if "pt_conflict" in conflicts:
        would.append("A broker note contradicts itself on its price target; a corrected note would change the evidence.")
    if "after_portfolio_snapshot" in conflicts:
        would.append("A note postdates the 30 Jun 2026 portfolio snapshot; refreshed prices could change the weight and call.")
    if n_houses == 0:
        would.append("No individual broker notes are on file for this name; the view rests on vendor consensus only.")
    if pos:
        would.append(f"Raising the cap above {pos['weight']:.1%} would remove the over-cap rule." if "position_over_cap" in rules
                     else f"A cap below {pos['weight']:.1%} would trigger a trim.")
    else:
        would.append("Evidence score crossing +/-0.4 would move this from watch to buy/avoid.")
    summary = (f"{ticker}: {action.replace('_', ' ')} (confidence {confidence}, evidence score {score:+.2f}). "
               f"Rules fired: {', '.join(rules) or 'none'}.")
    return dict(ticker=ticker, action=action, confidence=confidence, score=round(score, 3), rules_fired=rules,
                facts=facts, evidence=evidence, conflicts=conflicts, rejected_alternatives=rejected,
                would_change_if=would, assumptions=assumptions, summary=summary)
