# -*- coding: utf-8 -*-
"""بک‌تستر عمومی — شبیه‌سازی معامله روی کندل‌های ۱دقیقه، با قفل ضد «دیدن آینده»

بخشی از سیستم معامله‌گری خودکار حسین شیردل (ساخته‌شده با هوش مصنوعی).
قوانین راهبرد اصلی من داخل این فایل نیست؛ به‌جایش یک راهبرد نمونه‌ی ساده گذاشته‌ام (شکست سقف/کف
۲۰ کندل). هر راهبردی را می‌شود جایش گذاشت: تابعی که کندل‌ها را می‌گیرد و فهرست سفارش‌ها را برمی‌گرداند.

اجرا:  python backtest_engine.py
پیش‌نیاز: pip install pandas numpy   (برای نمودار: matplotlib)
دیتا:    خروجی history_downloader.py — مثلاً XAUUSD.zip با XAUUSD-1.csv و XAUUSD-15.csv
         (و اگر spreads.csv از spread_meter.py کنارش باشد، اسپرد واقعی از آن خوانده می‌شود)

چرا «قفل ضد دیدن آینده»؟
  بک‌تست قبلی من سه ماه نتیجه‌ی عالی نشان داد و در حساب واقعی شکست خورد؛ دلیلش این بود که بخشی از
  کد، بدون اینکه معلوم باشد، از کندل‌هایی استفاده می‌کرد که هنوز بسته نشده بودند. این موتور قبل از
  اجرا، راهبرد را چند بار روی دیتای «بریده‌شده» هم اجرا می‌کند: سفارشی که تا لحظه‌ی برش صادر شده
  باید با دیتای کامل و دیتای بریده دقیقاً یکی باشد. اگر نباشد یعنی راهبرد آینده را می‌بیند و بک‌تست
  اجرا نمی‌شود.

قواعد شبیه‌سازی (همه بدبینانه):
  - کندل‌ها قیمت Bid اند؛ خرید با Ask (= Bid + اسپرد) پر می‌شود و فروش با Ask بسته می‌شود.
  - سفارش فقط از کندل بعد از بسته شدن کندل سیگنال فعال می‌شود (اوردر لیمیت).
  - اگر قیمت پیش از پر شدن اوردر به تارگت رسید یا زمان اوردر تمام شد → لغو.
  - در کندلی که اوردر پر می‌شود فقط حدضرر بررسی می‌شود (تارگت و سیو سود نه).
  - اگر حدضرر و تارگت در یک کندل ۱دقیقه لمس شدند → حدضرر.
  - سیو سود: در 2R نصف حجم بسته می‌شود؛ باقی تا حدضرر یا تارگت می‌ماند.
  - هزینه‌ها: اسپرد + سواپ هر شب نگهداری. ریسک هر معامله ۱٪ موجودی همان لحظه.
"""

import os
import io
import sys
import glob
import zipfile

import numpy as np
import pandas as pd

# =====================================================================================
#                    تنظیمات
# =====================================================================================
DATA_DIR = os.path.join(os.path.expanduser("~"), "Desktop", "history_data")
OUT_DIR = os.path.join(DATA_DIR, "نتیجه_بکتست")
SYMBOL = "XAUUSD"
SIGNAL_TF = "15"               # تایم‌فریم سیگنال (برچسب اسم فایل: 15 یعنی XAUUSD-15.csv)
START = ""                     # مثل "2021-01-01" — خالی = از اول دیتای ۱دقیقه
END = ""                       # خالی = تا آخر دیتا

START_EQUITY = 100000.0
RISK_PER_TRADE = 0.01          # ۱٪ موجودی برای هر معامله
PARTIAL_AT_R = 2.0             # سیو سود: در 2R ...
PARTIAL_FRAC = 0.5             # ... نصف حجم بسته شود (0 = بدون سیو سود)
SPREAD = None                  # None = از spreads.csv، وگرنه از جدول پایین (برحسب قیمت)
SPREAD_TABLE = {"XAUUSD": 0.30, "XAGUSD": 0.03, "EURUSD": 0.00012, "GBPUSD": 0.00018, "USDJPY": 0.020}
SWAP_SPREAD_MULT_PER_NIGHT = 0.2   # سواپ هر شب ≈ ۲۰٪ اسپرد
LOOKAHEAD_CHECKS = 25          # چند برش برای آزمون «دیدن آینده»

# ---- راهبرد نمونه (شکست سقف/کف) ----
DEMO_BREAKOUT_BARS = 20        # بسته شدن بالای سقف ۲۰ کندل قبل → خرید (و برعکس)
DEMO_EMA = 50                  # فقط هم‌جهت شیب میانگین متحرک ۵۰
DEMO_PULLBACK_ATR = 0.5        # اوردر لیمیت نیم ATR عقب‌تر از قیمت بسته شدن
DEMO_STOP_ATR = 1.5            # حدضرر ۱.۵ ATR پشت ورود
DEMO_RR = 3.0                  # تارگت 3R
DEMO_EXPIRE_BARS = 8           # اگر تا ۸ کندل پر نشد، لغو
# =====================================================================================


# ============================================================================
# خواندن دیتا
# ============================================================================
def _smart_dt(d, t=None):
    """تبدیل تاریخ به datetime با تشخیص خودکار ترتیب روز/ماه (فرمت بروکرها فرق دارد)."""
    s = d.astype(str).str.strip()
    if t is not None:
        s = s + " " + t.astype(str).str.strip()
    samp = s.head(500).str.extract(r"^(\d{1,4})[./-](\d{1,2})[./-](\d{1,4})")
    dayfirst = False
    try:
        first = pd.to_numeric(samp[0], errors="coerce")
        if first.notna().any() and first.max() <= 31 and (first > 12).any():
            dayfirst = True
    except Exception:
        pass
    return pd.to_datetime(s, errors="coerce", dayfirst=dayfirst)


def read_mt_csv_from_bytes(b: bytes) -> pd.DataFrame:
    """CSV قیمت: متاتریدر بدون سطر عنوان (date,time,o,h,l,c[,v] یا datetime,o,h,l,c) یا فایل با سطر عنوان
    (ستون‌های Open/High/Low/Close یا BidOpen/...، تاریخ در Date/Time یا DateTime)."""
    if b is None or len(b) == 0:
        raise ValueError("فایل CSV خالی است.")
    head = b[:2048].decode("utf-8", "ignore")
    first_line = head.splitlines()[0].lower() if head else ""
    if any(k in first_line for k in ("open", "high", "low", "close")):
        df = pd.read_csv(io.BytesIO(b))
        df.columns = [str(c).strip().lower().replace(" ", "") for c in df.columns]

        def pick(*names):
            for nm in names:
                if nm in df.columns:
                    return df[nm]
            return None

        o = pick("open", "bidopen"); h = pick("high", "bidhigh")
        l = pick("low", "bidlow");   c = pick("close", "bidclose")
        if o is None or h is None or l is None or c is None:
            raise ValueError("ستون‌های قیمت (Open/High/Low/Close یا BidOpen/...) پیدا نشد.")
        dcol = pick("date"); tcol = pick("time", "datetime", "timestamp", "gmttime")
        if dcol is not None and tcol is not None:
            tser = _smart_dt(dcol, tcol)
        elif dcol is not None or tcol is not None:
            tser = _smart_dt(dcol if dcol is not None else tcol)
        else:
            tser = _smart_dt(df.iloc[:, 0])
    else:
        df = pd.read_csv(io.BytesIO(b), header=None)
        if df.shape[1] < 5:
            raise ValueError("فرمت CSV غیرمنتظره است (ستون کم).")
        if pd.to_numeric(df.iloc[:, 1], errors="coerce").notna().mean() > 0.9:
            tser = _smart_dt(df.iloc[:, 0])                       # ستون اول تاریخ+ساعت یکجا
            o, h, l, c = (df.iloc[:, k] for k in (1, 2, 3, 4))
        else:
            if df.shape[1] < 6:
                raise ValueError("فرمت CSV غیرمنتظره است (ستون کم).")
            tser = _smart_dt(df.iloc[:, 0], df.iloc[:, 1])        # فرمت کلاسیک: date,time,o,h,l,c
            o, h, l, c = (df.iloc[:, k] for k in (2, 3, 4, 5))
    out = pd.DataFrame({"time": tser,
                        "open": pd.to_numeric(o, errors="coerce"), "high": pd.to_numeric(h, errors="coerce"),
                        "low": pd.to_numeric(l, errors="coerce"), "close": pd.to_numeric(c, errors="coerce")})
    out = out.dropna().sort_values("time").drop_duplicates("time").reset_index(drop=True)
    if out.empty:
        raise ValueError("هیچ سطر معتبری در CSV پیدا نشد (فرمت ناشناخته).")
    return out


def _source(data_dir, symbol):
    """ZIP نماد یا پوشه‌ی بازشده‌اش → {اسم فایل: تابع خواندن}"""
    zp = os.path.join(data_dir, f"{symbol}.zip")
    if os.path.exists(zp):
        z = zipfile.ZipFile(zp)
        return {os.path.basename(n): (lambda n=n: z.read(n)) for n in z.namelist() if n.lower().endswith(".csv")}
    out = {}
    for p in glob.glob(os.path.join(data_dir, "**", f"{symbol}-*.csv"), recursive=True):
        out.setdefault(os.path.basename(p), (lambda p=p: open(p, "rb").read()))
    return out


def load_data(data_dir, symbol, tf):
    """(کندل‌های تایم‌فریم سیگنال، کندل‌های ۱دقیقه یا None)"""
    files = _source(data_dir, symbol)
    if f"{symbol}-{tf}.csv" not in files:
        raise FileNotFoundError(f"فایل {symbol}-{tf}.csv در {data_dir} پیدا نشد.")
    sig = read_mt_csv_from_bytes(files[f"{symbol}-{tf}.csv"]())
    m1 = None
    for name in (f"{symbol}-1.csv", f"{symbol}-M1.csv"):
        if name in files:
            m1 = read_mt_csv_from_bytes(files[name]())
            break
    return sig, m1


def load_spread(data_dir, symbol):
    if SPREAD is not None:
        return float(SPREAD)
    try:
        df = pd.read_csv(os.path.join(data_dir, "spreads.csv"))
        col = "median" if "median" in df.columns else "spread"
        v = float(df.loc[df["symbol"].astype(str).str.strip() == symbol, col].iloc[0])
        if np.isfinite(v) and v > 0:
            return v
    except Exception:
        pass
    return float(SPREAD_TABLE.get(symbol, 0.0))


# ============================================================================
# راهبرد نمونه — جای این تابع، راهبرد خودت را بگذار
# ============================================================================
def demo_strategy(df, tf_span):
    """df: کندل‌های بسته‌شده (ستون‌های time,open,high,low,close؛ time = زمان باز شدن کندل).
    خروجی: فهرست سفارش‌ها. هر سفارش: time (زمانی که صادر می‌شود = بسته شدن کندل سیگنال)،
    direction ("BUY"/"SELL")، entry، sl، tp، expire (تا کی معتبر است).
    قانون طلایی: سفارشی که در کندل i صادر می‌شود فقط باید از کندل‌های 0..i استفاده کند."""
    h, l, c = df["high"], df["low"], df["close"]
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()
    ema = c.ewm(span=DEMO_EMA, adjust=False).mean()
    hh = h.rolling(DEMO_BREAKOUT_BARS).max().shift(1)        # سقف ۲۰ کندل «قبل»
    ll = l.rolling(DEMO_BREAKOUT_BARS).min().shift(1)
    up = (c > hh) & (c.shift() <= hh.shift()) & (ema > ema.shift(5))
    dn = (c < ll) & (c.shift() >= ll.shift()) & (ema < ema.shift(5))
    out = []
    t_close = df["time"] + tf_span
    for i in np.flatnonzero((up | dn).to_numpy() & atr.notna().to_numpy()):
        a, cl = float(atr.iloc[i]), float(c.iloc[i])
        buy = bool(up.iloc[i])
        entry = cl - DEMO_PULLBACK_ATR * a if buy else cl + DEMO_PULLBACK_ATR * a
        sl = entry - DEMO_STOP_ATR * a if buy else entry + DEMO_STOP_ATR * a
        tp = entry + DEMO_RR * (entry - sl)
        out.append({"time": t_close.iloc[i], "direction": "BUY" if buy else "SELL",
                    "entry": entry, "sl": sl, "tp": tp,
                    "expire": t_close.iloc[i] + DEMO_EXPIRE_BARS * tf_span})
    return out


# ============================================================================
# قفل ضد «دیدن آینده»
# ============================================================================
def _key(s):
    return (pd.Timestamp(s["time"]), s["direction"], round(float(s["entry"]), 8), round(float(s["sl"]), 8),
            round(float(s["tp"]), 8), pd.Timestamp(s["expire"]))


def lookahead_check(strategy, df, tf_span, n=LOOKAHEAD_CHECKS, seed=7):
    """راهبرد را روی دیتای کامل و روی n برش تصادفی اجرا می‌کند. هر سفارشی که تا لحظه‌ی برش صادر شده
    باید در هر دو یکی باشد. خروجی: (درست است؟، توضیح)"""
    full = sorted(_key(s) for s in strategy(df, tf_span))
    if n <= 0 or len(df) < 50:
        return True, "آزمون انجام نشد (دیتا کم یا خاموش)"
    rng = np.random.default_rng(seed)
    cuts = sorted(set(int(k) for k in rng.integers(len(df) // 5, len(df), n)))
    for k in cuts:
        cut_time = df["time"].iloc[k - 1] + tf_span          # بسته شدن آخرین کندلِ برش
        part = sorted(_key(s) for s in strategy(df.iloc[:k].reset_index(drop=True), tf_span))
        later = [s for s in part if s[0] > cut_time]
        if later:
            return False, f"سفارشی با زمان {later[0][0]} از دیتایی ساخته شده که تا {cut_time} بود."
        want = [s for s in full if s[0] <= cut_time]
        if part != want:
            diff = sorted(set(want) ^ set(part))
            return False, (f"با برش در {cut_time}، سفارش‌ها عوض شدند (مثلاً {diff[0][1]} در {diff[0][0]}) — "
                           f"یعنی راهبرد از کندل‌های بعد از آن لحظه خبر داشته.")
    return True, f"{len(cuts)} برش آزمایش شد؛ راهبرد آینده را نمی‌بیند."


# ============================================================================
# شبیه‌سازی
# ============================================================================
def _first(mask_fn, j0, j1, step=4096):
    """اولین j در [j0, j1) که mask_fn(slice) برایش درست است — تکه‌تکه، تا کل آرایه بی‌دلیل خوانده نشود."""
    j = j0
    while j < j1:
        k = min(j1, j + step)
        m = mask_fn(slice(j, k))
        if m.any():
            return j + int(np.argmax(m))
        j, step = k, step * 2
    return j1


def simulate(signals, bars, spread):
    """هر سفارش جداگانه روی کندل‌های bars (۱دقیقه) → فهرست معامله‌ها با نتیجه برحسب R"""
    t = bars["time"].to_numpy(dtype="datetime64[ns]")
    o, h, l, c = (bars[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close"))
    n = len(t)
    out, cancelled = [], {"تارگت_پیش_از_ورود": 0, "تمام_شدن_زمان": 0, "سفارش_نامعتبر": 0}
    for s in signals:
        buy = s["direction"] == "BUY"
        entry, sl, tp = float(s["entry"]), float(s["sl"]), float(s["tp"])
        if (entry - sl if buy else sl - entry) <= 0 or (tp - entry if buy else entry - tp) <= 0:
            cancelled["سفارش_نامعتبر"] += 1
            continue
        j0 = int(np.searchsorted(t, np.datetime64(pd.Timestamp(s["time"])), "left"))
        j1 = int(np.searchsorted(t, np.datetime64(pd.Timestamp(s["expire"])), "left"))
        if buy:
            jf = _first(lambda r: l[r] + spread <= entry, j0, j1)
            jt = _first(lambda r: h[r] >= tp, j0, j1)
        else:
            jf = _first(lambda r: h[r] >= entry, j0, j1)
            jt = _first(lambda r: l[r] + spread <= tp, j0, j1)
        if jf >= j1 or jt < jf:
            cancelled["تارگت_پیش_از_ورود" if jt < min(jf, j1) else "تمام_شدن_زمان"] += 1
            continue
        # پر شدن: اگر کندل با شکاف از ورود رد شده باشد، با قیمت بهتر (باز شدن) پر می‌شود
        eff = min(entry, o[jf] + spread) if buy else max(entry, o[jf])
        risk = (eff - sl) if buy else (sl - eff)
        trig = eff + PARTIAL_AT_R * risk if buy else eff - PARTIAL_AT_R * risk
        if buy:
            sl_hit = lambda r: l[r] <= sl
            tp_hit = lambda r: h[r] >= tp
            pt_hit = lambda r: h[r] >= trig
        else:
            sl_hit = lambda r: h[r] + spread >= sl
            tp_hit = lambda r: l[r] + spread <= tp
            pt_hit = lambda r: l[r] + spread <= trig
        if sl_hit(slice(jf, jf + 1))[0]:                    # کندل ورود: فقط حدضرر
            js, jtp, jp = jf, n, n
        else:
            js = _first(sl_hit, jf + 1, n)
            jtp = _first(tp_hit, jf + 1, min(js + 1, n))
            jp = _first(pt_hit, jf + 1, min(js + 1, n)) if PARTIAL_FRAC > 0 else n
        if js < n and js <= jtp:
            jx, px, why = js, sl, ("حدضرر" if js < jtp else "هر دو در یک کندل: حدضرر")
        elif jtp < n:
            jx, px, why = jtp, tp, "حدسود"
        else:
            jx, px, why = n - 1, (c[-1] if buy else c[-1] + spread), "پایان دیتا"
        banked, frac = 0.0, 1.0
        if jp < js and jp <= jx:                             # سیو سود فقط اگر در همان کندل حدضرر نخورده
            banked, frac = PARTIAL_AT_R * PARTIAL_FRAC, 1.0 - PARTIAL_FRAC
        raw = (px - eff) / risk if buy else (eff - px) / risk
        fill_t, exit_t = pd.Timestamp(t[jf]), pd.Timestamp(t[jx])
        nights = max(0, (exit_t.normalize() - fill_t.normalize()).days)
        swap = SWAP_SPREAD_MULT_PER_NIGHT * spread * nights
        out.append({"جهت": "خرید" if buy else "فروش", "زمان_سیگنال": pd.Timestamp(s["time"]),
                    "زمان_ورود": fill_t, "ورود": eff, "حدضرر": sl, "حدسود": tp,
                    "زمان_خروج": exit_t, "قیمت_خروج": float(px), "علت_خروج": why,
                    "سیو_سود": banked > 0, "نتیجه_R": banked + frac * raw - swap / risk,
                    "هزینه_R": (spread + swap) / risk})
    return out, cancelled


def account(trades):
    """موجودی حساب: ریسک هر معامله = RISK_PER_TRADE × موجودی همان لحظه‌ی ورود (فقط معامله‌های بسته‌شده)"""
    ev = []
    for k, tr in enumerate(trades):
        # در یک لحظه: اول خروج‌های قبلی، بعد ورودها، بعد خروجِ معامله‌هایی که در همان کندل ورود بسته شدند
        ev.append((tr["زمان_خروج"], 2 if tr["زمان_خروج"] == tr["زمان_ورود"] else 0, k))
        ev.append((tr["زمان_ورود"], 1, k))
    eq, peak, dd = START_EQUITY, START_EQUITY, 0.0
    risk_amt, curve = {}, [(trades[0]["زمان_ورود"], eq)] if trades else []
    for when, kind, k in sorted(ev, key=lambda e: (e[0], e[1])):
        if kind == 1:
            risk_amt[k] = eq * RISK_PER_TRADE
        else:
            eq += risk_amt[k] * trades[k]["نتیجه_R"]
            trades[k]["سود_دلار"] = risk_amt[k] * trades[k]["نتیجه_R"]
            trades[k]["موجودی"] = eq
            peak = max(peak, eq)
            dd = max(dd, (peak - eq) / peak if peak > 0 else 0.0)
            curve.append((when, eq))
    return eq, dd, curve


def summary(trades, equity, max_dd):
    if not trades:
        return {"تعداد": 0}
    R = pd.Series([x["نتیجه_R"] for x in trades])
    loss = R[R < 0].abs().sum()
    return {"تعداد": len(R), "درصد_برد": round(float((R > 0).mean() * 100), 2),
            "فاکتور_سود": round(float(R[R > 0].sum() / loss), 3) if loss > 0 else float("inf"),
            "میانگین_R": round(float(R.mean()), 3), "جمع_R": round(float(R.sum()), 2),
            "بازده_خالص٪": round(float((equity - START_EQUITY) / START_EQUITY * 100), 2),
            "حداکثر_افت٪": round(max_dd * 100, 2),
            "هزینه_میانه_R": round(float(pd.Series([x["هزینه_R"] for x in trades]).median()), 3)}


def yearly(trades):
    if not trades:
        return pd.DataFrame()
    df = pd.DataFrame(trades)
    df["سال"] = pd.to_datetime(df["زمان_خروج"]).dt.year
    g = df.groupby("سال")["نتیجه_R"]
    return pd.DataFrame({"تعداد": g.size(), "درصد_برد": (g.apply(lambda r: (r > 0).mean() * 100)).round(1),
                         "جمع_R": g.sum().round(2)}).reset_index()


def save_chart(curve, path):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return False
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot([p[0] for p in curve], [p[1] for p in curve], color="#1f9d6b", lw=1.6)
    ax.set_title(f"{SYMBOL} equity")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return True


# ============================================================================
def run(data_dir=None, strategy=demo_strategy, out_dir=None, quiet=False):
    data_dir = data_dir or DATA_DIR
    out_dir = out_dir or (OUT_DIR if data_dir == DATA_DIR else os.path.join(data_dir, "نتیجه_بکتست"))
    say = (lambda *a: None) if quiet else print
    sig_df, m1 = load_data(data_dir, SYMBOL, SIGNAL_TF)
    span = pd.Timedelta(minutes=int(SIGNAL_TF)) if SIGNAL_TF.isdigit() else pd.Timedelta(SIGNAL_TF)
    spread = load_spread(data_dir, SYMBOL)
    bars = m1 if m1 is not None else sig_df
    if m1 is None:
        say(f"⚠️ دیتای ۱دقیقه نیست — شبیه‌سازی روی همان کندل‌های {SIGNAL_TF} (دقت کمتر).")
    t0 = max(pd.Timestamp(START) if START else bars["time"].iloc[0], bars["time"].iloc[0])
    t1 = min(pd.Timestamp(END) if END else bars["time"].iloc[-1], bars["time"].iloc[-1])
    say(f"نماد {SYMBOL} | از {t0:%Y-%m-%d} تا {t1:%Y-%m-%d} | اسپرد {spread}")

    ok, why = lookahead_check(strategy, sig_df, span)
    say(("✅ " if ok else "⛔ ") + "آزمون دیدن آینده: " + why)
    if not ok:
        say("بک‌تست اجرا نشد: نتیجه‌ی راهبردی که آینده را می‌بیند قابل اعتماد نیست.")
        return None

    signals = [s for s in strategy(sig_df, span) if t0 <= pd.Timestamp(s["time"]) <= t1]
    bars = bars[(bars["time"] >= t0) & (bars["time"] <= t1)].reset_index(drop=True)
    trades, cancelled = simulate(signals, bars, spread)
    trades.sort(key=lambda x: x["زمان_ورود"])
    equity, max_dd, curve = account(trades)
    m = summary(trades, equity, max_dd)

    os.makedirs(out_dir, exist_ok=True)
    pd.DataFrame(trades).to_csv(os.path.join(out_dir, "معاملات.csv"), index=False, encoding="utf-8-sig")
    y = yearly(trades)
    y.to_csv(os.path.join(out_dir, "سال_به_سال.csv"), index=False, encoding="utf-8-sig")
    lines = [f"{k}: {v}" for k, v in m.items()]
    lines += [f"سفارش‌ها: {len(signals)} | پر شد: {len(trades)} | لغو: " +
              ", ".join(f"{k} {v}" for k, v in cancelled.items())]
    with open(os.path.join(out_dir, "خلاصه.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n\n" + (y.to_string(index=False) if len(y) else "") + "\n")
    chart = curve and save_chart(curve, os.path.join(out_dir, "نمودار_موجودی.png"))
    say("\n".join(lines))
    if len(y):
        say(y.to_string(index=False))
    say(f"خروجی‌ها در: {out_dir}" + ("" if chart else " (بدون نمودار — matplotlib نصب نیست)"))
    return {"metrics": m, "trades": trades, "cancelled": cancelled, "signals": len(signals)}


if __name__ == "__main__":
    try:
        res = run(sys.argv[1] if len(sys.argv) > 1 else None)
        code = 0 if res is not None else 2
    except Exception as e:
        print(f"❌ خطا: {e}")
        code = 1
    if os.environ.get("BACKTEST_FROM_BAT") != "1" and sys.stdin and sys.stdin.isatty():
        try:
            input("\nبرای بستن Enter بزن...")
        except Exception:
            pass
    sys.exit(code)
