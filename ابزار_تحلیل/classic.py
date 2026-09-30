# -*- coding: utf-8 -*-
"""بکتستر کلاسیک (portfolio_live_replay از run_backtest.py، بدون هیچ تغییری در منطق).
عمق تاریخچه = همان عمقی که ربات در شروع لایو می‌دید (۲۰۰۰ کندل H4 قبل از ۲۰۲۶-۰۸-۱۴)."""
import os, sys, pickle
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)                             # پوشه‌ی اصلی پروژه
CACHE = os.path.join(HERE, "_cache")                     # خروجی‌های میانی
os.makedirs(CACHE, exist_ok=True)
sys.path.insert(0, REPO)
sys.path.insert(0, HERE)
import run_backtest as rb
from emulate import SPREADS, BASKET

LIVE_FROM = pd.Timestamp("2026-08-14")
END = pd.Timestamp("2026-09-26")


def main():
    frames = {}
    for s in BASKET:
        h4, d1, w1, _ = rb.load_timeframes_from_zip(os.path.join(REPO, "دیتا_هفتگی", f"{s}.zip"))
        if s == "EURCAD":
            h4 = h4[h4["time"] < pd.Timestamp("2026-09-22 20:00")].reset_index(drop=True)
            d1 = d1[d1["time"] < pd.Timestamp("2026-09-22")].reset_index(drop=True)
        frames[s] = (h4, d1, w1, None)
    # شروع = اولین کندل پنجره‌ی ۲۰۰۰تایی ربات در لحظه‌ی شروع لایو
    starts = [f[0][f[0]["time"] < LIVE_FROM].tail(2000)["time"].iloc[0] for f in frames.values()]
    rb.BACKTEST_START = pd.Timestamp(min(starts))
    rb.BACKTEST_END = None
    rb.USE_M15 = False
    # بکتستر «قبل از اصلاح» (همانی که نتایج قبلی را ساخته بود)
    rb.ENTRY_BAR_MODE, rb.NO_SAME_BAR_TOUCH_FILL, rb.MODEL_BID_ASK = "optimistic", False, False
    print("BACKTEST_START", rb.BACKTEST_START)
    res, book, alloc = rb.portfolio_live_replay(frames, SPREADS, entry_off=rb.DEFAULT_ENTRY_OFF,
                                                sl_off=rb.DEFAULT_SL_OFF, rr=rb.DEFAULT_RR,
                                                manage_mode=rb.DEFAULT_MANAGE)
    trades = pd.concat([r[2] for r in res.values() if r[2] is not None and not r[2].empty], ignore_index=True)
    trades["زمان_ورود"] = pd.to_datetime(trades["زمان_ورود"])
    trades["زمان_خروج"] = pd.to_datetime(trades["زمان_خروج"])
    curve = pd.DataFrame(book.equity_curve, columns=["t", "eq"])
    curve["t"] = pd.to_datetime(curve["t"])
    win = trades[(trades["زمان_ورود"] >= LIVE_FROM) & (trades["زمان_ورود"] < END)].sort_values("زمان_ورود")
    eq0 = curve[curve["t"] < LIVE_FROM]["eq"].iloc[-1] if (curve["t"] < LIVE_FROM).any() else book.start_equity
    # بازده دوره: فقط معاملاتی که داخل پنجره وارد شده‌اند، روی حساب ۱۰۰ هزاری با همان فرمول ریسک
    eq = 100000.0
    peak = eq
    mdd = 0.0
    for _, r in win.sort_values("زمان_خروج").iterrows():
        hr = (r["زمان_ورود"].hour + rb.SESSION_HOUR_SHIFT) % 24
        w = rb.DEFAULT_SESSION_WEIGHTS.get(rb.hour_to_session(hr), 1.0)
        eq += eq * 0.85 * 0.005 * w * r["نتیجه_R"]
        peak = max(peak, eq)
        mdd = max(mdd, (peak - eq) / peak)
    out = dict(trades=win, all_trades=trades, equity=eq, maxdd=mdd, start=rb.BACKTEST_START)
    with open(os.path.join(CACHE, "classic.pkl"), "wb") as f:
        pickle.dump(out, f)
    n = len(win)
    print("classic in live window:", n, "wins", int((win["نتیجه_R"] > 0).sum()),
          "sumR", round(win["نتیجه_R"].sum(), 2), "ret%", round((eq / 1e5 - 1) * 100, 2), "mdd%", round(mdd * 100, 2))
    pd.set_option("display.width", 250)
    print(win[["نماد", "جهت", "ZoneID", "زمان_ورود", "زمان_خروج", "ورود", "حدضرر", "علت_خروج", "نتیجه_R"]].to_string())
    # نتیجه‌ی کل تاریخچه برای مرجع
    print("whole run: trades", len(trades), "ret%", round((book.equity / book.start_equity - 1) * 100, 2),
          "mdd%", round(book.max_dd * 100, 2))


if __name__ == "__main__":
    main()
