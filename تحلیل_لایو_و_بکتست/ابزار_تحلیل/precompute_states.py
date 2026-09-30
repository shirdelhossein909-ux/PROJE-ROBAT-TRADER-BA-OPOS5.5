# -*- coding: utf-8 -*-
"""پیش‌محاسبه‌ی «مغز ربات» در هر کندل H4 دوره‌ی لایو — دقیقاً با همان پنجره‌ی دیتایی
که live_trader.py می‌دید: آخرین 2000 کندل بسته‌ی H4، 500 کندل بسته‌ی D1، 300 کندل بسته‌ی W1."""
import os, sys, pickle, time
import multiprocessing as mp
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))          # پوشه‌ی اصلی پروژه
CACHE = os.path.join(HERE, "_cache")                     # خروجی‌های میانی
os.makedirs(CACHE, exist_ok=True)
sys.path.insert(0, REPO)
import run_backtest as rb

# عین تنظیمات live_trader.py
rb.BACKTEST_START = pd.Timestamp("2000-01-01")
rb.BACKTEST_END = None
rb.USE_M15 = False
H4_BARS, D1_BARS, W1_BARS = 2000, 500, 300
ENTRY_OFF, RR = -0.50, 3.0

BASKET = ["XAUUSD", "AUDJPY", "AUDUSD", "CHFJPY", "EURCAD", "EURNZD",
          "GBPJPY", "GBPNZD", "NZDCAD", "USDCHF"]
LIVE_FROM = pd.Timestamp("2026-08-14 00:00")
OUT = os.path.join(CACHE, "states.pkl")

_DATA = {}


def load_all():
    data = {}
    for s in BASKET:
        h4, d1, w1, _ = rb.load_timeframes_from_zip(os.path.join(REPO, "دیتا_هفتگی", f"{s}.zip"))
        if s == "EURCAD":
            # آخرین کندل EURCAD (2026-09-22 20:00) موقع خروجی گرفتن هنوز بسته نشده بود
            h4 = h4[h4["time"] < pd.Timestamp("2026-09-22 20:00")].reset_index(drop=True)
            d1 = d1[d1["time"] < pd.Timestamp("2026-09-22")].reset_index(drop=True)
        data[s] = (h4, d1, w1)
    return data


def _init():
    global _DATA
    _DATA = load_all()


def window(sym, T):
    """کندل‌های بسته‌شده در لحظه‌ی T (باز شدن کندل H4 جدید) — عین copy_rates_from_pos(...,1,N)."""
    h4, d1, w1 = _DATA[sym]
    h = h4[h4["time"] < T].tail(H4_BARS).reset_index(drop=True)
    d = d1[d1["time"] < T.normalize()].tail(D1_BARS).reset_index(drop=True)
    w = w1[w1["time"] + pd.Timedelta(days=7) <= T].tail(W1_BARS).reset_index(drop=True)
    return h, d, w


def work(task):
    sym, T = task
    h, d, w = window(sym, T)
    # دیتای این نماد برای این لحظه نیست اگر آخرین کندلش از آخرین کندل کل سبد عقب‌تر باشد
    # (مثلاً EURCAD بعد از 2026-09-22). تعطیلی آخر هفته این شرط را خراب نمی‌کند.
    prev_all = max(_DATA[s][0]["time"][_DATA[s][0]["time"] < T].max() for s in _DATA
                   if (_DATA[s][0]["time"] < T).any())
    if h.empty or h["time"].iloc[-1] < prev_all:
        return (sym, T, None)
    out = rb.backtest_one(sym, h, d, w, None, 0.0, entry_off=ENTRY_OFF, rr=RR,
                          m15=None, return_state=True)
    st = out[6]
    keep = {k: st[k] for k in ("pending", "armed", "فیلتر_توضیح", "دلیل_نبود")}
    keep["win"] = (str(h["time"].iloc[0]), str(h["time"].iloc[-1]), len(h), len(d), len(w))
    return (sym, T, keep)


def main():
    data = load_all()
    times = sorted(set().union(*[set(data[s][0]["time"]) for s in BASKET]))
    sync_times = [t for t in times if t >= LIVE_FROM]
    tasks = [(s, T) for T in sync_times for s in BASKET]
    print(f"{len(sync_times)} sync × {len(BASKET)} symbols = {len(tasks)} replays", flush=True)
    t0 = time.time()
    res = {}
    with mp.Pool(4, initializer=_init) as pool:
        for k, (s, T, st) in enumerate(pool.imap_unordered(work, tasks, chunksize=4), 1):
            res[(s, T)] = st
            if k % 200 == 0:
                print(f"  {k}/{len(tasks)}  {time.time()-t0:.0f}s", flush=True)
    with open(OUT, "wb") as f:
        pickle.dump({"sync_times": sync_times, "states": res}, f)
    print("done", time.time() - t0, OUT)


if __name__ == "__main__":
    main()
