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
#    مثلاً 6 یعنی ۶ سال گذشته تا همین الان. (عدد اعشاری هم می‌شود: 0.5 یعنی ۶ ماه)
YEARS_BACK = 6

# ۲) یا به‌جای «چند سال قبل»، تاریخ دقیق بده (اختیاری).
#    فرمت: "2020-01-01"  — اگر START_DATE پر شود، YEARS_BACK نادیده گرفته می‌شود.
#    END_DATE خالی یعنی «تا همین الان».
START_DATE = ""
END_DATE = ""

# ۳) تایم‌فریم‌ها — هر ردیف: ("برچسب اسم فایل", "تایم‌فریم متاتریدر")
#    برچسب در اسم فایل می‌آید؛ مثلاً ("240", "H4") فایل XAUUSD-240.csv را می‌سازد.
#    برای حذف یک تایم‌فریم، اول خطش یک # بگذار؛ برای اضافه کردن، یک ردیف مثل بقیه بنویس.
#
#    تایم‌فریم‌های قابل استفاده و برچسب پیشنهادی هر کدام:
#       "M1" → "1"    "M5" → "5"    "M15" → "15"   "M30" → "30"
#       "H1" → "60"   "H4" → "240"  "D1"  → "1D"   "W1"  → "1W"
#
#    ⚠️ سه تای اول (240 و 1D و 1W) را حذف نکن؛ بک‌تستر بدون آن‌ها اجرا نمی‌شود.
#    ℹ️ بک‌تستر ریزترین فایلِ موجود از بین "1"، "5" و "15" را خودش پیدا می‌کند و ترتیب واقعی
#       اتفاقات داخل کندل ۴ساعته را از روی آن حساب می‌کند (بک‌تست دقیق‌تر می‌شود).
#    ⚠️ دیتای ۱ دقیقه خیلی حجیم است (حدود ۳۷۰ هزار کندل در سال برای هر نماد).
TIMEFRAMES = [
    ("240", "H4"),
    ("1D",  "D1"),
    ("1W",  "W1"),
    ("60",  "H1"),
    ("15",  "M15"),
    ("5",   "M5"),
    # ("1", "M1"),
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

# ۶) مسیر فایل terminal64.exe متاتریدر — معمولاً خالی بگذار.
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
REQUIRED_LABELS = ("240", "1D", "1W")

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
    for need in REQUIRED_LABELS:
        if need not in labels:
            problems.append(f"تایم‌فریم با برچسب «{need}» در TIMEFRAMES نیست؛ بک‌تستر بدون آن اجرا نمی‌شود.")
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


def fetch(name, tf_name, start, end):
    """کندل‌های بازه را می‌گیرد. اگر متاتریدر هنوز تاریخچه را از سرور نگرفته باشد،
    چند بار صبر می‌کند و دوباره می‌پرسد."""
    tf = getattr(mt5, "TIMEFRAME_" + tf_name)
    rates = None
    best = 0
    for attempt in range(6):
        rates = mt5.copy_rates_range(name, tf, start, end)
        n = 0 if rates is None else len(rates)
        # تاریخچه کامل رسیده؟ (شروع دیتا نزدیک شروع درخواست، یا تعدادش دیگر زیاد نمی‌شود)
        if n and (int(rates["time"][0]) <= start.timestamp() + 14 * 86400 or n == best):
            break
        best = max(best, n)
        time.sleep(3)
    if rates is None or len(rates) == 0:
        return None
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")          # ساعت سرور بروکر (مثل خود متاتریدر)
    return df[["time", "open", "high", "low", "close"]]


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


def main():
    print("=" * 64)
    print(" دانلود دیتای متاتریدر برای بک‌تست")
    print("=" * 64)

    problems = check_settings()
    if problems:
        print("⛔ تنظیمات بالای فایل مشکل دارد:")
        for p in problems:
            print("   - " + p)
        return 1

    start, end = date_range()
    years = (min(end, dt.datetime.now(dt.timezone.utc)) - start).days / 365.25
    print(f"بازه: از {start.date()} تا {'امروز' if not END_DATE.strip() else END_DATE}  (حدود {years:.1f} سال)")
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

        files = {}
        notes = []
        for lab, tf_name in TIMEFRAMES:
            df = fetch(name, tf_name, start, end)
            df = drop_open_bar(df, tf_name, last_tick)
            if df is None or df.empty:
                notes.append(f"{tf_name}: دیتا نیامد")
                print(f"   ⚠️ {base} {tf_name}: دیتا نیامد")
                continue
            files[f"{base}-{lab}.csv"] = to_csv_text(df, digits)
            first, last = df["time"].iloc[0], df["time"].iloc[-1]
            short = first > pd.Timestamp(start.replace(tzinfo=None)) + pd.Timedelta(days=30)
            flag = "  ⚠️ از شروع بازه کوتاه‌تر" if short else ""
            if short:
                notes.append(f"{tf_name} از {first.date()}")
            print(f"   {base:7s} {tf_name:4s} → {len(df):>9,} کندل | {first:%Y-%m-%d} تا {last:%Y-%m-%d %H:%M}{flag}")

        missing = [lab for lab in REQUIRED_LABELS if f"{base}-{lab}.csv" not in files]
        if missing:
            print(f"❌ {base}: فایل‌های لازم ساخته نشد ({', '.join(missing)}) — ZIP ساخته نشد.\n")
            summary.append((base, "ناقص", "، ".join(notes)))
            continue

        zpath = os.path.join(OUT_DIR, f"{base}.zip")
        tmp = zpath + ".tmp"
        with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as z:
            for fname, text in files.items():
                z.writestr(fname, text)
        os.replace(tmp, zpath)
        print(f"✅ {base}.zip ساخته شد ({len(files)} تایم‌فریم)\n")
        summary.append((base, "✅", "، ".join(notes)))

    mt5.shutdown()

    print("=" * 64)
    print(" نتیجه")
    print("=" * 64)
    for base, st, note in summary:
        print(f" {st:10s} {base:7s} {note}")
    print(f"\nفایل‌ها در: {OUT_DIR}")
    if os.path.normcase(os.path.abspath(OUT_DIR)) != os.path.normcase(
            os.path.join(os.path.expanduser("~"), "Desktop", "0")):
        print("برای بک‌تست: فایل‌های ZIP این پوشه را در پوشه‌ی «0» روی دسکتاپ کپی کن (جای قبلی‌ها).")
    return 0


if __name__ == "__main__":
    try:
        code = main()
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
