# -*- coding: utf-8 -*-
"""شبیه‌ساز «عین لایو» (walk-forward):

در هر کندل H4 دوره‌ی لایو، همان کاری که live_trader.py می‌کند تکرار می‌شود:
  ۱) مغز ربات (rb.backtest_one با return_state) روی دقیقاً همان پنجره‌ی دیتایی که
     ربات می‌دید (از states.pkl)
  ۲) سهمیه‌بندی دوری: هر نماد تا ۳ سفارش، کل حساب ۸ سفارش — عین sync_all
  ۳) لغو سفارش‌هایی که دیگر خواسته نیستند و گذاشتن سفارش‌های جدید
  ۴) در طول همان کندل: پر شدن سفارش، حد ضرر/حد سود، سیو سود در 2R
     (با همان قواعد بدبینانه‌ی خود بک‌تستر: اگر در یک کندل هم استاپ هم تارگت لمس شد → استاپ)
"""
import os, sys, pickle
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)                             # پوشه‌ی اصلی پروژه
CACHE = os.path.join(HERE, "_cache")                     # خروجی‌های میانی
os.makedirs(CACHE, exist_ok=True)
sys.path.insert(0, REPO)
import run_backtest as rb
rb.STABLE_ZONE_IDS = False   # همان شناسه‌های قدیمی که ربات لایو در این دوره داشت

BASKET = ["XAUUSD", "AUDJPY", "AUDUSD", "CHFJPY", "EURCAD", "EURNZD",
          "GBPJPY", "GBPNZD", "NZDCAD", "USDCHF"]
DIGITS = {"XAUUSD": 2, "AUDJPY": 3, "CHFJPY": 3, "GBPJPY": 3}
# جدول اسپرد خود run_backtest.py
SPREADS = {"AUDUSD": 0.00014, "USDCHF": 0.00014, "EURCAD": 0.00022, "EURNZD": 0.00025,
           "GBPNZD": 0.00032, "CHFJPY": 0.020, "GBPJPY": 0.025, "AUDJPY": 0.020,
           "NZDCAD": 0.00025, "XAUUSD": 0.30}
PIP = {"XAUUSD": 0.1, "AUDJPY": 0.01, "CHFJPY": 0.01, "GBPJPY": 0.01}

MAX_PENDING_TOTAL, MAX_OPEN_TOTAL, PER_SYM = 8, 8, 3
RISK, RESERVE, START_EQ = 0.005, 0.15, 100000.0
TRIG_R, PART = 2.0, 0.5
# بازه‌هایی که ربات در ساعات باز بازار خاموش/هنگ بود (ساعت سرور؛ از روی لاگ و سفارش‌های متاتریدر)
DOWNTIMES = [(pd.Timestamp("2026-08-24 10:47"), pd.Timestamp("2026-08-24 23:29")),
             (pd.Timestamp("2026-08-27 23:25"), pd.Timestamp("2026-08-31 00:00"))]


def digits(s):
    return DIGITS.get(s, 5)


def pip(s):
    return PIP.get(s, 0.0001)


def zkey(s, p):
    d = digits(s)
    return (s, p["direction"], round(p["entry"], d), round(p["sl"], d))


def session_weight(T):
    hr = (T.hour + rb.SESSION_HOUR_SHIFT) % 24
    return float(rb.DEFAULT_SESSION_WEIGHTS.get(rb.hour_to_session(hr), 1.0))


def load():
    with open(os.path.join(CACHE, "states.pkl"), "rb") as f:
        st = pickle.load(f)
    bars = {}
    for s in BASKET:
        h4, _, _, _ = rb.load_timeframes_from_zip(os.path.join(REPO, "دیتا_هفتگی", f"{s}.zip"), tf_set="H4")
        if s == "EURCAD":
            h4 = h4[h4["time"] < pd.Timestamp("2026-09-22 20:00")]
        bars[s] = {pd.Timestamp(r.time): (r.open, r.high, r.low, r.close) for r in h4.itertuples()}
    return st["sync_times"], st["states"], bars


def allocate(states, T, revalidate_pending=False):
    """عین sync_all: خواسته‌ی هر نماد = pending + armed؛ سهمیه‌ی دوری ۳×۸."""
    wanted = {}
    for s in BASKET:
        stt = states.get((s, T))
        if stt is None:
            continue
        pend = list(stt["pending"])
        if revalidate_pending and stt.get("دلیل_نبود") != "فیلترها سبزند":
            pend = []
        wanted[s] = pend + list(stt.get("armed", []))
    alloc, total = {}, 0
    for r in range(PER_SYM):
        for s in BASKET:
            lst = wanted.get(s, [])
            if len(lst) > r and total < MAX_PENDING_TOTAL:
                alloc.setdefault(s, []).append(lst[r])
                total += 1
    return wanted, alloc


def run(sync_times, states, bars, spread_mode=False, cost_mode=True, downtime=False,
        revalidate_pending=False, pess_entry=False, end=pd.Timestamp("2026-09-26")):
    eq = START_EQ
    peak, maxdd = eq, 0.0
    pending = {}      # key -> order
    positions = []    # list of dict
    trades = []
    desired_log = []  # برای مقایسه‌ی تصمیم‌ها با لایو
    curve = []

    def sprd(s):
        return SPREADS[s] if spread_mode else 0.0

    def close_pos(p, t, px, why):
        nonlocal eq, peak, maxdd
        risk = p["risk"]
        raw = (px - p["entry"]) / risk if p["dir"] == "BUY" else (p["entry"] - px) / risk
        r = p["banked"] + p["frac"] * raw
        if cost_mode and not spread_mode:
            # همان مدل هزینه‌ی run_backtest: کمیسیون ≈ ۰.۵ اسپرد + سواپ ≈ ۰.۲ اسپرد به ازای هر شب
            nights = max(0, (t.normalize() - p["fill_time"].normalize()).days)
            r -= (0.5 * SPREADS[p["sym"]] + 0.2 * SPREADS[p["sym"]] * nights) / risk
        pnl = p["risk_amt"] * r
        eq += pnl
        peak = max(peak, eq)
        maxdd = max(maxdd, (peak - eq) / peak)
        curve.append((t, eq))
        trades.append(dict(sym=p["sym"], dir=p["dir"], zone_id=p["zone_id"], key=p["key"],
                           placed=p["placed"], fill_time=p["fill_time"], exit_time=t,
                           entry=p["entry"], sl=p["sl"], tp=p["tp"], exit=px, why=why,
                           partial=p["managed"], R=r, risk_amt=p["risk_amt"], pnl=pnl,
                           weight=p["w"], risk_pips=risk / pip(p["sym"])))

    def step_pos(p, o, h, l, c, t, manage_ok, entry_bar=False):
        """یک کندل برای یک پوزیشن — عین process_pos_candle بک‌تستر (بدبینانه).
        entry_bar + pess_entry: در کندلی که سفارش پر شده معلوم نیست سقف/کف قبل از
        پر شدن بوده یا بعد از آن؛ پس سیو سود/تارگت فقط وقتی پذیرفته می‌شود که
        «کلوز» کندل آن را تأیید کند (قیمت بعد از ورود حتماً به آن‌جا رسیده)."""
        s = sprd(p["sym"])
        if p["dir"] == "BUY":
            hit_sl = l <= p["sl"]
            fav = h
            if entry_bar and pess_entry == "mid":
                fav = h if c >= o else c
            elif entry_bar and pess_entry:
                fav = c
            hit_tp, hit_trg = fav >= p["tp"], fav >= p["trig"]
        else:
            hit_sl = h + s >= p["sl"]
            fav = l
            if entry_bar and pess_entry == "mid":
                fav = l if c <= o else c
            elif entry_bar and pess_entry:
                fav = c
            hit_tp, hit_trg = fav + s <= p["tp"], fav + s <= p["trig"]
        if manage_ok and not p["managed"] and not hit_sl and hit_trg:
            p["managed"] = True
            p["banked"] = TRIG_R * PART
            p["frac"] = 1.0 - PART
        if hit_sl:
            close_pos(p, t, p["sl"], "حدضرر" if not hit_tp else "هر دو در یک کندل: حدضرر")
            return True
        if hit_tp:
            close_pos(p, t, p["tp"], "حدسود")
            return True
        return False

    for T in sync_times:
        if T >= end:
            break
        in_down = downtime and any(a <= T < b for a, b in DOWNTIMES)
        w = session_weight(T)

        # ---------- همگام‌سازی سر کندل (عین sync_all) ----------
        if not in_down:
            wanted, alloc = allocate(states, T, revalidate_pending)
            desired = {}
            for s, lst in alloc.items():
                for p in lst:
                    desired[zkey(s, p)] = (s, p)
            desired_log.append(dict(T=T, keys=set(desired.keys()),
                                    n_wanted=sum(len(v) for v in wanted.values())))
            if len(positions) >= MAX_OPEN_TOTAL:
                pending.clear()
            else:
                for k in list(pending):
                    if k not in desired:
                        del pending[k]
                for k, (s, p) in desired.items():
                    if k in pending:
                        pending[k]["w"] = w       # جایگزینی با حجم سشن جدید
                        continue
                    bar = bars[s].get(T)
                    if bar is None:
                        continue
                    o = bar[0]
                    # سفارش لیمیت فقط وقتی معنا دارد که قیمت هنوز به ورود نرسیده باشد
                    if p["direction"] == "BUY" and not (p["entry"] < o + sprd(s)):
                        continue
                    if p["direction"] == "SELL" and not (p["entry"] > o):
                        continue
                    d = digits(s)
                    entry, sl, tp = round(p["entry"], d), round(p["sl"], d), round(p["tp"], d)
                    risk = abs(entry - sl)
                    if risk <= 0:
                        continue
                    pending[k] = dict(sym=s, key=k, zone_id=p["zone_id"], dir=p["direction"],
                                      entry=entry, sl=sl, tp=tp, risk=risk, placed=T, w=w,
                                      trig=entry + TRIG_R * risk if p["direction"] == "BUY" else entry - TRIG_R * risk)

        # ---------- حرکت بازار در طول همین کندل ----------
        manage_ok = not in_down
        still = []
        for p in positions:
            bar = bars[p["sym"]].get(T)
            if bar is None or not step_pos(p, *bar, T, manage_ok):
                still.append(p)
        positions = still

        for k in list(pending):
            od = pending[k]
            bar = bars[od["sym"]].get(T)
            if bar is None:
                continue
            o, h, l, c = bar
            s = sprd(od["sym"])
            filled = (l + s <= od["entry"]) if od["dir"] == "BUY" else (h >= od["entry"])
            if not filled:
                continue
            del pending[k]
            if len(positions) >= MAX_OPEN_TOTAL:
                continue
            pos = dict(od)
            pos.update(fill_time=T, managed=False, banked=0.0, frac=1.0,
                       risk_amt=eq * (1 - RESERVE) * RISK * od["w"])
            if not step_pos(pos, o, h, l, c, T, manage_ok, entry_bar=True):
                positions.append(pos)
            if len(positions) >= MAX_OPEN_TOTAL:
                pending.clear()

    for p in positions:
        last_t = max(t for t in bars[p["sym"]] if t < end)
        close_pos(p, last_t, bars[p["sym"]][last_t][3], "پایان دیتا (باز)")

    tdf = pd.DataFrame(trades)
    return dict(trades=tdf, equity=eq, maxdd=maxdd, curve=curve, desired=desired_log)


def summarize(res, label):
    t = res["trades"]
    n = len(t)
    if n == 0:
        return {"حالت": label, "تعداد": 0}
    wins = (t["R"] > 0).sum()
    return {"حالت": label, "تعداد": n, "برد": int(wins), "وین_ریت": round(wins / n * 100, 1),
            "جمع_R": round(t["R"].sum(), 2), "میانگین_R": round(t["R"].mean(), 3),
            "سود_دلاری": round(res["equity"] - START_EQ, 0),
            "بازده٪": round((res["equity"] / START_EQ - 1) * 100, 2),
            "حداکثر_افت٪": round(res["maxdd"] * 100, 2)}


if __name__ == "__main__":
    sync_times, states, bars = load()
    variants = {
        "A_backtester_like": dict(),
        "B_with_spread": dict(spread_mode=True),
        "C_downtime": dict(downtime=True),
        "D_spread_downtime": dict(spread_mode=True, downtime=True),
        "E_revalidate": dict(revalidate_pending=True),
        "F_pess_entry": dict(pess_entry=True),
        "G_pess_spread": dict(pess_entry=True, spread_mode=True),
        "H_pess_spread_down": dict(pess_entry=True, spread_mode=True, downtime=True),
        "M_mid": dict(pess_entry="mid"),
        "N_mid_spread_down": dict(pess_entry="mid", spread_mode=True, downtime=True),
    }
    out = {}
    for name, kw in variants.items():
        res = run(sync_times, states, bars, **kw)
        out[name] = res
        print(summarize(res, name))
    with open(os.path.join(CACHE, "emu_results.pkl"), "wb") as f:
        pickle.dump(out, f)
    t = out["A_backtester_like"]["trades"]
    pd.set_option("display.width", 250)
    print(t[["sym", "dir", "zone_id", "fill_time", "exit_time", "entry", "sl", "tp", "exit", "why", "partial", "R", "pnl", "risk_pips"]].to_string())
