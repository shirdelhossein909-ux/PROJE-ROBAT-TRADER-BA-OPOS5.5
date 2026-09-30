# -*- coding: utf-8 -*-
"""مقایسه‌ی لایو با شبیه‌ساز «عین لایو»: هم در سطح تصمیم (سفارش‌های روی حساب در هر
همگام‌سازی) و هم در سطح معامله."""
import os, sys, pickle
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))          # پوشه‌ی اصلی پروژه
CACHE = os.path.join(HERE, "_cache")                     # خروجی‌های میانی
os.makedirs(CACHE, exist_ok=True)
sys.path.insert(0, HERE)
from emulate import digits, BASKET

orders = pd.read_pickle(os.path.join(CACHE, "live_orders.pkl"))
live = pd.read_pickle(os.path.join(CACHE, "live_trades.pkl"))
emu = pickle.load(open(os.path.join(CACHE, "emu_results.pkl"), "rb"))
END = pd.Timestamp("2026-09-26")

lim = orders[orders["type"].str.contains("limit")].copy()
lim["dir"] = lim["type"].str.startswith("buy").map({True: "BUY", False: "SELL"})
lim["key"] = [(s, d, round(float(p), digits(s)), round(float(sl), digits(s)))
              for s, d, p, sl in zip(lim["symbol"], lim["dir"], lim["price"], lim["sl"])]


def close(k1, k2):
    """دو کلید یکی‌اند اگر نماد و جهت یکی و ورود/استاپ حداکثر ۲ پوینت فرق داشته باشد (خطای گرد کردن)."""
    if k1[0] != k2[0] or k1[1] != k2[1]:
        return False
    pt = 10 ** -digits(k1[0])
    return abs(k1[2] - k2[2]) <= 2.01 * pt and abs(k1[3] - k2[3]) <= 2.01 * pt


def fuzzy_sets(ek, lk):
    ek, lk = list(ek), list(lk)
    used = set()
    both = []
    only_e = []
    for a in ek:
        hit = None
        for j, b in enumerate(lk):
            if j not in used and close(a, b):
                hit = j
                break
        if hit is None:
            only_e.append(a)
        else:
            used.add(hit)
            both.append(a)
    only_l = [b for j, b in enumerate(lk) if j not in used]
    return both, only_e, only_l


def live_book(snap):
    a = lim[(lim["open_time"] <= snap) & (lim["close_time"] > snap)]
    return a


def decisions(res_name="A_backtester_like"):
    rows = []
    for d in emu[res_name]["desired"]:
        T = d["T"]
        if T >= END:
            break
        snap = T + pd.Timedelta(hours=1, minutes=3) if T.hour == 0 else T + pd.Timedelta(minutes=3)
        book = live_book(snap)
        lk = list(book["key"])
        dup = len(lk) - len(set(lk))
        both, oe, ol = fuzzy_sets(sorted(d["keys"]), lk)
        rows.append(dict(T=T, snap=snap, emu_n=len(d["keys"]), live_n=len(lk), both=len(both),
                         only_emu=len(oe), only_live=len(ol), live_dups=dup,
                         only_emu_keys=oe, only_live_keys=ol))
    return pd.DataFrame(rows)


def match_trades(res_name):
    e = emu[res_name]["trades"].copy()
    e = e[e["fill_time"] < END]
    l = live[live["fill_time"] < END].copy()
    l["key"] = [(s, d, round(p, digits(s)), round(sl, digits(s)))
                for s, d, p, sl in zip(l["sym"], l["dir"], l["entry"], l["sl"])]
    used = set()
    out = []
    for i, r in l.iterrows():
        # همان زون (کلید قیمتی) و زمان پر شدن نزدیک (حداکثر یک کندل اختلاف)
        c = e[[close(k, r["key"]) for k in e["key"]] & (~e.index.isin(used))]
        c = c[(c["fill_time"] - r["fill_time"].floor("4h")).abs() <= pd.Timedelta(hours=8)]
        if len(c):
            j = c.index[0]
            used.add(j)
            out.append(dict(وضعیت="هر دو", نماد=r["sym"], جهت=r["dir"], زون_لایو=r["zone_id"],
                            ورود=r["entry"], استاپ=r["sl"], تارگت=r["tp"], ریسک_پیپ=round(r["risk_pips"], 1),
                            زمان_پر_شدن_لایو=r["fill_time"], کندل_پر_شدن_بکتست=e.at[j, "fill_time"],
                            نتیجه_لایو=r["why"] + (" + سیو سود" if r["n_partial_deals"] else ""),
                            R_لایو=round(r["R_price"], 2), سود_لایو=round(r["profit"], 2),
                            نتیجه_بکتست=e.at[j, "why"] + (" + سیو سود" if e.at[j, "partial"] else ""),
                            R_بکتست=round(e.at[j, "R"], 2), سود_بکتست=round(e.at[j, "pnl"], 2)))
        else:
            out.append(dict(وضعیت="فقط لایو", نماد=r["sym"], جهت=r["dir"], زون_لایو=r["zone_id"],
                            ورود=r["entry"], استاپ=r["sl"], تارگت=r["tp"], ریسک_پیپ=round(r["risk_pips"], 1),
                            زمان_پر_شدن_لایو=r["fill_time"],
                            نتیجه_لایو=r["why"] + (" + سیو سود" if r["n_partial_deals"] else ""),
                            R_لایو=round(r["R_price"], 2), سود_لایو=round(r["profit"], 2)))
    for j, r in e[~e.index.isin(used)].iterrows():
        out.append(dict(وضعیت="فقط بکتست", نماد=r["sym"], جهت=r["dir"], زون_لایو="",
                        ورود=r["entry"], استاپ=r["sl"], تارگت=r["tp"], ریسک_پیپ=round(r["risk_pips"], 1),
                        کندل_پر_شدن_بکتست=r["fill_time"],
                        نتیجه_بکتست=r["why"] + (" + سیو سود" if r["partial"] else ""),
                        R_بکتست=round(r["R"], 2), سود_بکتست=round(r["pnl"], 2)))
    df = pd.DataFrame(out)
    df["_t"] = df["زمان_پر_شدن_لایو"].fillna(df["کندل_پر_شدن_بکتست"])
    return df.sort_values("_t").drop(columns="_t").reset_index(drop=True)


if __name__ == "__main__":
    pd.set_option("display.width", 260)
    pd.set_option("display.max_colwidth", 80)
    dec = decisions()
    print("syncs", len(dec), "emu orders", dec.emu_n.sum(), "live orders", dec.live_n.sum(),
          "both", dec.both.sum(), "only_emu", dec.only_emu.sum(), "only_live", dec.only_live.sum(),
          "dups", dec.live_dups.sum())
    print("exact-match syncs:", ((dec.only_emu == 0) & (dec.only_live == 0)).sum())
    bad = dec[(dec.only_emu > 0) | (dec.only_live > 0)]
    print(bad[["T", "emu_n", "live_n", "both", "only_emu", "only_live", "live_dups", "only_emu_keys", "only_live_keys"]].head(60).to_string())
    dec.to_pickle(os.path.join(CACHE, "decisions.pkl"))
    for nm in ("A_backtester_like", "H_pess_spread_down"):
        m = match_trades(nm)
        m.to_pickle(os.path.join(CACHE, f"match_{nm}.pkl"))
        print("\n==", nm, m["وضعیت"].value_counts().to_dict())
        print(m.drop(columns=["تارگت"]).to_string())
