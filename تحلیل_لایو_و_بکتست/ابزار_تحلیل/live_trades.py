# -*- coding: utf-8 -*-
"""معاملات واقعی لایو → جدول تمیز با R قیمتی، ریسک دلاری و زمان ثبت سفارش."""
import os, re
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))          # پوشه‌ی اصلی پروژه
CACHE = os.path.join(HERE, "_cache")                     # خروجی‌های میانی
os.makedirs(CACHE, exist_ok=True)
PIP = {"XAUUSD": 0.1, "AUDJPY": 0.01, "CHFJPY": 0.01, "GBPJPY": 0.01}


def build():
    pos = pd.read_pickle(os.path.join(CACHE, "live_positions.pkl"))
    orders = pd.read_pickle(os.path.join(CACHE, "live_orders.pkl"))
    deals = pd.read_pickle(os.path.join(CACHE, "live_deals.pkl"))
    outs = deals[deals["direction"] == "out"].copy()

    pos = pos.sort_values("open_time").reset_index(drop=True)
    assign = {i: [] for i in pos.index}
    for _, d in outs.iterrows():
        side_closed = "BUY" if d["type"] == "sell" else "SELL"
        c = pos[(pos["symbol"] == d["symbol"]) & (pos["side"] == side_closed) &
                (pos["open_time"] <= d["time"]) & (pos["close_time"] >= d["time"])]
        if len(c) > 1:
            m = re.search(r"\[(sl|tp) ([\d.]+)\]", str(d["comment"]))
            if m:
                px = float(m.group(2))
                c2 = c[(abs(c["sl"] - px) < 1e-6) | (abs(c["tp"] - px) < 1e-6)]
                if len(c2):
                    c = c2
        assign[c.index[0]].append(d)

    rows = []
    for i, p in pos.iterrows():
        ds = assign[i]
        risk = abs(p["entry"] - p["sl"])
        sgn = 1 if p["side"] == "BUY" else -1
        vol = sum(d["volume"] for d in ds)
        r_price = sum(d["volume"] * sgn * (d["price"] - p["entry"]) for d in ds) / (p["volume"] * risk)
        partials = [d for d in ds if d["comment"] == "TP2-partial"]
        last = ds[-1]["comment"] if ds else ""
        why = "حدسود" if str(last).startswith("[tp") else ("حدضرر" if str(last).startswith("[sl") else str(last))
        net = p["profit"] + p["swap"] + p["commission"]
        o = orders[orders["order"] == p["position"]]
        placed = o["open_time"].iloc[0] if len(o) else pd.NaT
        comment = o["comment"].iloc[0] if len(o) else ""
        rows.append(dict(position=p["position"], sym=p["symbol"], dir=p["side"], zone_id=comment,
                         placed=placed, fill_time=p["open_time"], exit_time=p["close_time"],
                         entry=p["entry"], sl=p["sl"], tp=p["tp"], volume=p["volume"],
                         closed_vol=round(vol, 2), n_partial_deals=len(partials), why=why,
                         R_price=r_price, profit=net,
                         risk_usd=(net / r_price) if abs(r_price) > 1e-9 else float("nan"),
                         risk_pips=risk / PIP.get(p["symbol"], 0.0001)))
    return pd.DataFrame(rows)


if __name__ == "__main__":
    t = build()
    t.to_pickle(os.path.join(CACHE, "live_trades.pkl"))
    pd.set_option("display.width", 250)
    print(t[["sym", "dir", "zone_id", "placed", "fill_time", "exit_time", "entry", "sl", "tp", "volume",
             "n_partial_deals", "why", "R_price", "profit", "risk_usd", "risk_pips"]].round(3).to_string())
    print("sum profit", t["profit"].sum(), "sum R", t["R_price"].sum(), "wins", (t["profit"] > 0).sum(), "/", len(t))
