# -*- coding: utf-8 -*-
"""بکتستر روی کل ۲ سال دیتا: رفتار قبل از اصلاح در برابر اصلاح «کندل ورود» (بقیه‌ی کلیدها خاموش،
تا فقط اثر همین یک فرض دیده شود)."""
import os, sys, pickle
import pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)                             # پوشه‌ی اصلی پروژه
CACHE = os.path.join(HERE, "_cache")                     # خروجی‌های میانی
os.makedirs(CACHE, exist_ok=True)
sys.path.insert(0, REPO)
sys.path.insert(0, HERE)
import run_backtest as rb
rb.STABLE_ZONE_IDS = False   # همان شناسه‌های قدیمی که ربات لایو در این دوره داشت
from emulate import SPREADS, BASKET

frames = {}
for s in BASKET:
    h4, d1, w1, _ = rb.load_timeframes_from_zip(os.path.join(REPO, "دیتا_هفتگی", f"{s}.zip"), tf_set="H4")
    if s == "EURCAD":
        h4 = h4[h4["time"] < pd.Timestamp("2026-09-22 20:00")].reset_index(drop=True)
        d1 = d1[d1["time"] < pd.Timestamp("2026-09-22")].reset_index(drop=True)
    frames[s] = (h4, d1, w1, None)
rb.BACKTEST_START = pd.Timestamp("2019-01-01"); rb.BACKTEST_END = None; rb.USE_M15 = False
out = {}
rb.NO_SAME_BAR_TOUCH_FILL, rb.MODEL_BID_ASK = False, False
MODES = {False: "optimistic", "mid": "path", True: "pessimistic"}
for pess in (False, "mid", True):
    rb.ENTRY_BAR_MODE = MODES[pess]
    res, book, alloc = rb.portfolio_live_replay(frames, SPREADS, entry_off=rb.DEFAULT_ENTRY_OFF, sl_off=rb.DEFAULT_SL_OFF,
                                                rr=rb.DEFAULT_RR, manage_mode=rb.DEFAULT_MANAGE)
    tr = pd.concat([r[2] for r in res.values() if r[2] is not None and not r[2].empty], ignore_index=True)
    tr["زمان_ورود"] = pd.to_datetime(tr["زمان_ورود"])
    curve = pd.DataFrame(book.equity_curve, columns=["t", "eq"]); curve["t"] = pd.to_datetime(curve["t"])
    m = curve.set_index("t")["eq"].resample("ME").last().ffill()
    mret = m.pct_change().fillna(m.iloc[0] / 1e5 - 1) * 100
    per_sym = tr.groupby("نماد")["نتیجه_R"].agg(["count", "sum", "mean"]).round(3)
    out[pess] = dict(trades=tr, equity=book.equity, mdd=book.max_dd, monthly=mret, per_sym=per_sym,
                     start=tr["زمان_ورود"].min(), end=tr["زمان_ورود"].max())
    print({False: "ORIG", "mid": "MID", True: "PESS"}[pess], "trades", len(tr), "win%", round((tr["نتیجه_R"] > 0).mean() * 100, 1),
          "sumR", round(tr["نتیجه_R"].sum(), 1), "ret%", round((book.equity / 1e5 - 1) * 100, 2),
          "mdd%", round(book.max_dd * 100, 2), "neg months", int((mret < 0).sum()), "/", len(mret),
          tr["زمان_ورود"].min(), tr["زمان_ورود"].max())
    print(per_sym.to_string())
pickle.dump(out, open(os.path.join(CACHE, "classic_full.pkl"), "wb"))
