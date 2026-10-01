# -*- coding: utf-8 -*-
"""دانلود دیتای کندل از متاتریدر ۵ برای بک‌تست.

اجرا:  روی export_data.bat دابل‌کلیک کن  (یا روی خود همین export_data.py دابل‌کلیک کن)
پیش‌نیاز: متاتریدر ۵ باز و لاگین باشد (همان بروکری که ربات رویش کار می‌کند).

برای هر نماد یک فایل ZIP می‌سازد (مثلاً XAUUSD.zip) که داخلش برای هر تایم‌فریم یک CSV
هست (مثلاً XAUUSD-240.csv) — دقیقاً همان فرمتی که run_backtest.py می‌خواند.
فقط کندل‌های «بسته‌شده» ذخیره می‌شوند (کندلِ در حال شکل‌گیری حذف می‌شود).
"""

import os
import sys
import time
import zipfile
import datetime as dt

# =====================================================================================
#                    تنظیمات — فقط همین بخش را عوض کن
# =====================================================================================

# ۱) از چند سال قبل تا امروز دیتا گرفته شود؟
#    مثلاً 3 یعنی ۳ سال گذشته تا همین الان. (عدد اعشاری هم می‌شود: 0.5 یعنی ۶ ماه)
#    ⚠️ تایم‌های ریز حجیم‌اند: هر سال ≈ ۲۵ هزار کندل ۱۵دقیقه، ۷۵ هزار کندل ۵دقیقه، ۳۷۰ هزار کندل ۱دقیقه.
#       اگر از «Max bars in chart» متاتریدر بیشتر شود، دیتای قدیمی‌تر نمی‌آید (پایین را ببین).
YEARS_BACK = 3

# ۲) یا به‌جای «چند سال قبل»، تاریخ دقیق بده (اختیاری).
#    فرمت: "2020-01-01"  — اگر START_DATE پر شود، YEARS_BACK نادیده گرفته می‌شود.
#    END_DATE خالی یعنی «تا همین الان».
START_DATE = "2025-01-01"
END_DATE = "2025-12-31"
#    گرم‌کردن: تایم‌های ۱۵دقیقه و بالاتر از این چند روز قبل از START_DATE گرفته می‌شوند تا روند ۴ساعته و
#    زون‌ها روز اول بک‌تست آماده باشند (معامله فقط از START_DATE؛ همان WARMUP_DAYS در run_backtest.py).
#    تایم‌های ۱ و ۵ دقیقه فقط از خود START_DATE.
WARMUP_DAYS = 120

# ۳) تایم‌فریم‌ها — هر ردیف: ("برچسب اسم فایل", "تایم‌فریم متاتریدر")
#    برچسب در اسم فایل می‌آید؛ مثلاً ("240", "H4") فایل XAUUSD-240.csv را می‌سازد.
#    برای حذف یک تایم‌فریم، اول خطش یک # بگذار؛ برای اضافه کردن، یک ردیف مثل بقیه بنویس.
#
#    تایم‌فریم‌های قابل استفاده و برچسب پیشنهادی هر کدام:
#       "M1" → "1"    "M5" → "5"    "M15" → "15"   "M30" → "30"
#       "H1" → "60"   "H4" → "240"  "D1"  → "1D"   "W1"  → "1W"
#
#    بک‌تستر (run_backtest.py) بسته به تنظیم STRATEGY_TF یکی از این دو دسته را لازم دارد:
#       STRATEGY_TF = "M15" → برچسب‌های  15 و 240        (بیس ۱۵دقیقه، روند و زون مخالف ۴ساعته)
#       STRATEGY_TF = "H4"  → برچسب‌های  240 و 1D و 1W   (همان ربات لایو فعلی)
#    ℹ️ اگر یک تایم ریزتر از تایم زون هم بگیری (مثلاً "5" یا "1" برای دسته‌ی M15)، بک‌تستر خودش
#       پیدایش می‌کند و ترتیب واقعی اتفاقات داخل کندل را از روی آن حساب می‌کند (دقیق‌تر).
#    دسته‌ی فعلی = STRATEGY_TF="M15" (بیس ۱۵دقیقه، روند ۴ساعته، تأیید چاک ۱دقیقه)
#    ℹ️ ۱دقیقه برای تأیید چاک لازم است؛ یک سالش ≈ ۳۷۰ هزار کندل → «Max bars in chart» متاتریدر
#       باید Unlimited باشد.
TIMEFRAMES = [
    ("1",   "M1"),
    ("15",  "M15"),
    ("240", "H4"),
    # ("1D",  "D1"),
    # ("5",   "M5"),
    # ("1W",  "W1"),
    # ("60",  "H1"),
]

# ۴) نمادها — همان سبد ربات. اگر نزد بروکر پسوند دارند (مثلاً XAUUSD.m)، خودش پیدا می‌کند.
SYMBOLS = ["XAUUSD", "AUDJPY", "AUDUSD", "CHFJPY", "EURCAD", "EURNZD",
           "GBPJPY", "GBPNZD", "NZDCAD", "USDCHF"]

# ۵) پوشه‌ی خروجی (فایل‌های ZIP اینجا ساخته می‌شوند).
#    بک‌تستر دیتا را از پوشه‌ی «0» روی دسکتاپ می‌خواند. پیش‌فرض اینجا یک پوشه‌ی جدا است
#    تا دیتای قبلی‌ات پاک نشود؛ بعد از دانلود، ZIPها را در Desktop\0 کپی کن.
#    اگر می‌خواهی مستقیم همان‌جا ساخته شوند، خط زیر را این‌طور کن:
#       OUT_DIR = os.path.join(os.path.expanduser("~"), "Desktop", "0")
OUT_DIR = os.path.join(os.path.expanduser("~"), "Desktop", "دیتای_جدید_بکتست")

# ۶) اسپرد واقعی: میانگین اسپرد (Ask − Bid) تیک‌های چند روز اخیر هر نماد از همین متاتریدر
#    اندازه گرفته و در فایل spreads.csv کنار ZIPها ذخیره می‌شود؛ بک‌تستر از میانه‌ی آن استفاده
#    می‌کند (میانگین را پرش‌های رول‌اوور بالا می‌برد).
#    فقط اسپرد (بدون دانلود دوباره‌ی کندل‌ها): export_spreads.bat را اجرا کن.
SPREAD_DAYS = 5

# ۷) مسیر فایل terminal64.exe متاتریدر — معمولاً خالی بگذار.
#    فقط اگر چند متاتریدر نصب داری و به اشتباه وصل می‌شود، مسیرش را اینجا بنویس، مثلاً:
#       r"C:\Program Files\MetaTrader 5\terminal64.exe"
TERMINAL_PATH = ""

# =====================================================================================
#                       از اینجا به پایین را لازم نیست تغییر بدهی
# =====================================================================================

TF_SECONDS = {"M1": 60, "M5": 300, "M15": 900, "M30": 1800, "H1": 3600,
              "H4": 14400, "D1": 86400, "W1": 604800}
BARS_PER_YEAR = {"M1": 374400, "M5": 74880, "M15": 24960, "M30": 12480, "H1": 6240,
                 "H4": 1560, "D1": 260, "W1": 52}
# دسته‌های تایم‌فریمی که بک‌تستر می‌شناسد (باید با TF_SETS در run_backtest.py یکی باشد)
BACKTEST_SETS = {"M15": ("15", "240"), "H4": ("240", "1D", "1W")}
LTF_NAMES = ("M1", "M5")      # بدون گرم‌کردن (فقط از START_DATE)

def _fail(msg):
    """پیام خطا + (اگر مستقیم دابل‌کلیک شده) صبر تا کاربر پیام را بخواند."""
    print(msg)
    if os.environ.get("EXPORT_FROM_BAT") != "1":
        try:
            input("\nبرای بستن پنجره Enter بزن...")
        except Exception:
            pass
    sys.exit(1)


try:
    import pandas as pd
except ImportError:
    _fail("پکیج pandas نصب نیست. در CMD بزن:  pip install pandas")
try:
    import MetaTrader5 as mt5
except ImportError:
    _fail("پکیج MetaTrader5 نصب نیست. در CMD بزن:  pip install MetaTrader5")


def parse_date(s):
    return dt.datetime.strptime(s.strip(), "%Y-%m-%d").replace(tzinfo=dt.timezone.utc)


def date_range():
    now = dt.datetime.now(dt.timezone.utc)
    end = parse_date(END_DATE) + dt.timedelta(days=1) if END_DATE.strip() else now + dt.timedelta(days=1)
    if START_DATE.strip():
        start = parse_date(START_DATE)
    else:
        start = now - dt.timedelta(days=float(YEARS_BACK) * 365.25)
    return start, end


def check_settings():
    problems = []
    labels = [lab for lab, _ in TIMEFRAMES]
    if not labels:
        problems.append("TIMEFRAMES خالی است؛ حداقل یک تایم‌فریم لازم است.")
    elif not any(all(l in labels for l in need) for need in BACKTEST_SETS.values()):
        problems.append("با این تایم‌فریم‌ها بک‌تستر اجرا نمی‌شود. یکی از این دو دسته لازم است: "
                        + " یا ".join(f"«{' و '.join(v)}» (STRATEGY_TF={k})" for k, v in BACKTEST_SETS.items()))
    for lab, name in TIMEFRAMES:
        if name not in TF_SECONDS:
            problems.append(f"تایم‌فریم «{name}» شناخته‌شده نیست. مجازها: {', '.join(TF_SECONDS)}")
    if len(set(labels)) != len(labels):
        problems.append("یک برچسب دو بار در TIMEFRAMES آمده است.")
    if START_DATE.strip():
        try:
            parse_date(START_DATE)
        except ValueError:
            problems.append(f"فرمت START_DATE اشتباه است: «{START_DATE}» — درستش مثل 2020-01-01")
    if END_DATE.strip():
        try:
            parse_date(END_DATE)
        except ValueError:
            problems.append(f"فرمت END_DATE اشتباه است: «{END_DATE}» — درستش مثل 2026-08-31")
    return problems


def connect():
    ok = mt5.initialize(path=TERMINAL_PATH) if TERMINAL_PATH.strip() else mt5.initialize()
    if not ok:
        print(f"⛔ اتصال به متاتریدر برقرار نشد: {mt5.last_error()}")
        print("   متاتریدر ۵ باید باز و لاگین باشد.")
        return None
    acc = mt5.account_info()
    ti = mt5.terminal_info()
    if acc is not None:
        print(f"✅ وصل شد | حساب {acc.login} ({acc.server})")
    return ti


def resolve(base):
    """اسم نماد نزد بروکر (با پسوند احتمالی)."""
    if mt5.symbol_info(base) is not None:
        mt5.symbol_select(base, True)
        return base
    cands = mt5.symbols_get(f"*{base}*")
    if cands:
        name = sorted((c.name for c in cands), key=len)[0]
        mt5.symbol_select(name, True)
        return name
    return None


def _fetch_range(name, tf, start, end):
    """یک تکه از بازه. اگر متاتریدر هنوز تاریخچه را از سرور نگرفته باشد،
    چند بار صبر می‌کند و دوباره می‌پرسد."""
    rates = None
    best = 0
    for attempt in range(4):
        rates = mt5.copy_rates_range(name, tf, start, end)
        n = 0 if rates is None else len(rates)
        # تاریخچه‌ی این تکه رسیده؟ (شروعش نزدیک شروع درخواست، یا تعدادش دیگر زیاد نمی‌شود)
        if n and (int(rates["time"][0]) <= start.timestamp() + 7 * 86400 or n == best):
            break
        best = max(best, n)
        time.sleep(2)
    return rates


def fetch(name, tf_name, start, end):
    """کندل‌های کل بازه — تکه‌تکه (هر تکه حداکثر حدود ۴۰ هزار کندل)، چون متاتریدر درخواستِ
    خیلی بزرگ را گاهی کامل رد می‌کند و هیچ دیتایی نمی‌دهد."""
    tf = getattr(mt5, "TIMEFRAME_" + tf_name)
    per_day = BARS_PER_YEAR[tf_name] / 365.25
    step = dt.timedelta(days=max(7, int(40000 / per_day)))
    parts = []
    a = start
    while a < end:
        b = min(a + step, end)
        r = _fetch_range(name, tf, a, b)
        if r is not None and len(r):
            parts.append(pd.DataFrame(r))
        a = b
    if not parts:
        return None
    df = pd.concat(parts, ignore_index=True).drop_duplicates("time").sort_values("time")
    df["time"] = pd.to_datetime(df["time"], unit="s")          # ساعت سرور بروکر (مثل خود متاتریدر)
    return df[["time", "open", "high", "low", "close"]].reset_index(drop=True)


def drop_open_bar(df, tf_name, last_tick_time):
    """کندلی که تا لحظه‌ی آخرین تیک هنوز تمام نشده، حذف می‌شود (فقط کندل‌های کامل)."""
    if df is None or df.empty or last_tick_time is None:
        return df
    end_of_bar = df["time"] + pd.Timedelta(seconds=TF_SECONDS[tf_name])
    return df[end_of_bar <= last_tick_time].reset_index(drop=True)


def to_csv_text(df, digits):
    """فرمت متاتریدر بدون سطر عنوان: date,time,open,high,low,close"""
    out = pd.DataFrame({
        "d": df["time"].dt.strftime("%Y.%m.%d"),
        "t": df["time"].dt.strftime("%H:%M"),
    })
    for c in ("open", "high", "low", "close"):
        out[c] = df[c].round(digits)
    return out.to_csv(header=False, index=False)


class _Tee:
    """هر چه چاپ می‌شود هم در پنجره می‌آید و هم در فایل گزارش ذخیره می‌شود
    (اگر پنجره بسته شد، نتیجه از دست نرود)."""
    def __init__(self, *streams):
        self.streams = streams

    def write(self, s):
        for st in self.streams:
            try:
                st.write(s)
                st.flush()
            except Exception:
                pass

    def flush(self):
        for st in self.streams:
            try:
                st.flush()
            except Exception:
                pass


LOG_NAME = "گزارش_دانلود.txt"
SPREADS_NAME = "spreads.csv"
DATA_DIR = os.path.join(os.path.expanduser("~"), "Desktop", "0")   # پوشه‌ای که بک‌تستر می‌خواند


def measure_spread(name, si):
    """اسپرد واقعی نماد (برحسب قیمت): میانگین Ask − Bid تیک‌های SPREAD_DAYS روز اخیر.
    خروجی: (میانگین, میانه, تعداد تیک, منبع). روزبه‌روز خوانده می‌شود تا حافظه پر نشود."""
    point = float(getattr(si, "point", 0.0) or 0.0)
    now = dt.datetime.now(dt.timezone.utc)
    total, count, samples = 0.0, 0, []
    for d in range(SPREAD_DAYS + 3, 0, -1):          # چند روز بیشتر، چون آخر هفته تیک ندارد
        a = now - dt.timedelta(days=d)
        ticks = mt5.copy_ticks_range(name, a, a + dt.timedelta(days=1), mt5.COPY_TICKS_INFO)
        if ticks is None or len(ticks) == 0:
            continue
        sp = ticks["ask"] - ticks["bid"]
        sp = sp[(ticks["bid"] > 0) & (sp > 0)]
        if len(sp) == 0:
            continue
        total += float(sp.sum())
        count += int(len(sp))
        samples.append(sp[::max(1, len(sp) // 20000)])
    if count:
        import numpy as np
        med = float(np.median(np.concatenate(samples)))
        return total / count, med, count, "تیک"
    # تیک نیامد → ستون اسپرد کندل‌های ۱۵دقیقه (کمینه‌ی اسپرد هر کندل؛ کمی خوش‌بینانه)
    rates = mt5.copy_rates_from_pos(name, mt5.TIMEFRAME_M15, 0, 2000)
    if rates is not None and len(rates) and point > 0:
        sp = rates["spread"].astype(float) * point
        sp = sp[sp > 0]
        if len(sp):
            return float(sp.mean()), float(sorted(sp)[len(sp) // 2]), 0, "کندل"
    cur = float(getattr(si, "spread", 0) or 0) * point
    return cur, cur, 0, "لحظه‌ای"


def write_spreads(rows, dirs):
    """rows: [(نماد, میانگین, میانه, تعداد تیک, منبع, digits)] → spreads.csv در هر پوشه‌ی dirs"""
    lines = ["symbol,spread,median,ticks,source"]
    for base, mean, med, n, src, digits in rows:
        nd = max(int(digits) + 2, 6)
        lines.append(f"{base},{mean:.{nd}f},{med:.{nd}f},{n},{src}")
    text = "\n".join(lines) + "\n"
    out = []
    for d in dirs:
        if not d or not os.path.isdir(d):
            continue
        path = os.path.join(d, SPREADS_NAME)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        out.append(path)
    return out


def _pip(base):
    if base.endswith("JPY"):
        return 0.01
    if base.startswith("XAU"):
        return 0.1
    if base.startswith("XAG"):
        return 0.01
    return 0.0001


def spreads_only():
    """فقط اندازه‌گیری اسپرد همه‌ی نمادها (بدون دانلود کندل) → spreads.csv"""
    print("=" * 64)
    print(f" اندازه‌گیری اسپرد واقعی متاتریدر (میانگین تیک‌های {SPREAD_DAYS} روز اخیر)")
    print("=" * 64)
    if connect() is None:
        return 1
    rows = []
    for base in SYMBOLS:
        name = resolve(base)
        if name is None:
            print(f"❌ {base}: نزد بروکر پیدا نشد")
            continue
        si = mt5.symbol_info(name)
        mean, med, n, src = measure_spread(name, si)
        rows.append((base, mean, med, n, src, int(getattr(si, "digits", 5) or 5)))
        print(f"   {base:7s} اسپرد میانگین {mean / _pip(base):6.2f} پیپ | میانه {med / _pip(base):6.2f} پیپ"
              f" | {n:,} تیک ({src})")
    mt5.shutdown()
    if not rows:
        return 1
    os.makedirs(OUT_DIR, exist_ok=True)
    paths = write_spreads(rows, [OUT_DIR, DATA_DIR])
    print("\nذخیره شد:")
    for p_ in paths:
        print("   " + p_)
    if not any(os.path.dirname(p_) == DATA_DIR for p_ in paths):
        print(f"⚠️ پوشه‌ی {DATA_DIR} پیدا نشد؛ فایل spreads.csv را خودت در پوشه‌ی 0 کپی کن.")
    return 0


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    log_path = os.path.join(OUT_DIR, LOG_NAME)
    try:
        sys.stdout = _Tee(sys.__stdout__, open(log_path, "w", encoding="utf-8"))
    except Exception:
        log_path = None

    print("=" * 64)
    print(" دانلود دیتای متاتریدر برای بک‌تست")
    print("=" * 64)
    if log_path:
        print(f"(همه‌ی این پیام‌ها در این فایل هم ذخیره می‌شود: {log_path})")

    problems = check_settings()
    if problems:
        print("⛔ تنظیمات بالای فایل مشکل دارد:")
        for p in problems:
            print("   - " + p)
        return 1

    start, end = date_range()
    years = (min(end, dt.datetime.now(dt.timezone.utc)) - start).days / 365.25
    print(f"بازه: از {start.date()} تا {'امروز' if not END_DATE.strip() else END_DATE}  (حدود {years:.1f} سال)")
    if WARMUP_DAYS:
        print(f"   (تایم‌های ۱۵دقیقه و بالاتر از {WARMUP_DAYS} روز قبلش برای گرم‌کردن روند و زون‌ها)")
    print(f"تایم‌فریم‌ها: {', '.join(f'{n} (فایل -{lab}.csv)' for lab, n in TIMEFRAMES)}")
    print(f"نمادها: {', '.join(SYMBOLS)}")
    print(f"پوشه‌ی خروجی: {OUT_DIR}\n")

    ti = connect()
    if ti is None:
        return 1

    # سقف کندل متاتریدر: اگر کمتر از نیاز باشد، دیتای تایم‌فریم‌های ریز ناقص می‌آید
    maxbars = getattr(ti, "maxbars", 0) or 0
    need = max(int(BARS_PER_YEAR[n] * years) for _, n in TIMEFRAMES)
    if maxbars and maxbars < need:
        print(f"⚠️ «Max bars in chart» متاتریدر {maxbars:,} است ولی برای این بازه تا حدود {need:,} کندل لازم است.")
        print("   در متاتریدر: Tools → Options → Charts → Max bars in chart = Unlimited")
        print("   بعد متاتریدر را ببند و دوباره باز کن و این فایل را دوباره اجرا کن.")
        print("   (ادامه می‌دهم، ولی دیتای تایم‌فریم‌های ریز ممکن است از شروع بازه کوتاه‌تر باشد.)\n")

    os.makedirs(OUT_DIR, exist_ok=True)
    summary = []
    spread_rows = []
    for base in SYMBOLS:
        name = resolve(base)
        if name is None:
            print(f"❌ {base}: نزد بروکر پیدا نشد — رد شد.")
            summary.append((base, "پیدا نشد", ""))
            continue
        si = mt5.symbol_info(name)
        digits = int(getattr(si, "digits", 5) or 5)
        tick = mt5.symbol_info_tick(name)
        last_tick = pd.to_datetime(tick.time, unit="s") if (tick is not None and tick.time) else None

        try:
            mean, med, n_t, src = measure_spread(name, si)
            spread_rows.append((base, mean, med, n_t, src, digits))
            print(f"   {base:7s} اسپرد واقعی: میانگین {mean / _pip(base):.2f} پیپ ({src})")
        except Exception as e:
            print(f"   ⚠️ {base}: اندازه‌گیری اسپرد نشد ({e})")

        files = {}
        notes = []
        for lab, tf_name in TIMEFRAMES:
            tf_start = start if tf_name in LTF_NAMES else start - dt.timedelta(days=WARMUP_DAYS)
            df = fetch(name, tf_name, tf_start, end)
            df = drop_open_bar(df, tf_name, last_tick)
            if df is None or df.empty:
                notes.append(f"{tf_name}: دیتا نیامد")
                print(f"   ⚠️ {base} {tf_name}: دیتا نیامد")
                continue
            files[f"{base}-{lab}.csv"] = to_csv_text(df, digits)
            first, last = df["time"].iloc[0], df["time"].iloc[-1]
            short = first > pd.Timestamp(tf_start.replace(tzinfo=None)) + pd.Timedelta(days=30)
            flag = "  ⚠️ از شروع بازه کوتاه‌تر" if short else ""
            if short:
                notes.append(f"{tf_name} از {first.date()}")
            print(f"   {base:7s} {tf_name:4s} → {len(df):>9,} کندل | {first:%Y-%m-%d} تا {last:%Y-%m-%d %H:%M}{flag}")

        if not files:
            print(f"❌ {base}: هیچ دیتایی نیامد — ZIP ساخته نشد.\n")
            summary.append((base, "ناقص", "، ".join(notes)))
            continue
        if not any(all(f"{base}-{l}.csv" in files for l in need) for need in BACKTEST_SETS.values()):
            notes.append("برای بک‌تست کامل نیست")

        zpath = os.path.join(OUT_DIR, f"{base}.zip")
        tmp = zpath + ".tmp"
        with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as z:
            for fname, text in files.items():
                z.writestr(fname, text)
        os.replace(tmp, zpath)
        print(f"✅ {base}.zip ساخته شد ({len(files)} تایم‌فریم)\n")
        summary.append((base, "✅", "، ".join(notes)))

    mt5.shutdown()
    if spread_rows:
        write_spreads(spread_rows, [OUT_DIR])

    print("=" * 64)
    print(" نتیجه")
    print("=" * 64)
    for base, st, note in summary:
        print(f" {st:10s} {base:7s} {note}")
    print(f"\nفایل‌ها در: {OUT_DIR}")
    if os.path.normcase(os.path.abspath(OUT_DIR)) != os.path.normcase(
            os.path.join(os.path.expanduser("~"), "Desktop", "0")):
        print("برای بک‌تست: فایل‌های ZIP و spreads.csv این پوشه را در پوشه‌ی «0» روی دسکتاپ کپی کن (جای قبلی‌ها).")
    labels = [lab for lab, _ in TIMEFRAMES]
    fits = [k for k, need in BACKTEST_SETS.items() if all(l in labels for l in need)]
    if fits:
        print(f"در run_backtest.py مقدار STRATEGY_TF باید «{fits[0]}» باشد (همان بالای فایل).")
    if log_path:
        print(f"گزارش کامل این دانلود: {log_path}")
    return 0


if __name__ == "__main__":
    try:
        code = spreads_only() if "--spreads" in sys.argv[1:] else main()
    except KeyboardInterrupt:
        print("\n⏹️ متوقف شد.")
        code = 1
    except Exception as e:
        print(f"\n❌ خطای غیرمنتظره: {e}")
        code = 1
    # اگر خود همین فایل مستقیم دابل‌کلیک شده (نه از export_data.bat)، پنجره فوراً بسته نشود
    if os.environ.get("EXPORT_FROM_BAT") != "1":
        try:
            input("\nبرای بستن پنجره Enter بزن...")
        except Exception:
            pass
    sys.exit(code)
