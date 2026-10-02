# -*- coding: utf-8 -*-
"""دانلود تاریخچه‌ی کندل از متاتریدر ۵ — سال‌به‌سال

بخشی از سیستم معامله‌گری خودکار حسین شیردل (ساخته‌شده با هوش مصنوعی).

اجرا:  python history_downloader.py      (متاتریدر ۵ باز و لاگین باشد)
پیش‌نیاز: pip install MetaTrader5 pandas

چه می‌کند:
  - برای هر نماد، هر تایم‌فریم را سال‌به‌سال و از جدید به قدیم از متاتریدر می‌گیرد (درخواست‌های بزرگ
    کندل ۱دقیقه متاتریدر را گیر می‌اندازد؛ تکه‌های کوچک نه). جایی که تاریخچه‌ی بروکر تمام شود، می‌ایستد.
  - هر سالِ تمام‌شده جدا ذخیره می‌شود؛ اگر دانلود نصفه بماند، دفعه‌ی بعد آن سال‌ها دوباره گرفته نمی‌شوند.
  - آخر کار همه‌ی سال‌ها کنار هم گذاشته می‌شوند و برای هر نماد یک ZIP ساخته می‌شود
    (مثلاً XAUUSD.zip با XAUUSD-1.csv، XAUUSD-15.csv و XAUUSD-240.csv) به فرمت خود متاتریدر.
  - فقط کندل‌های «بسته‌شده» ذخیره می‌شوند.
  - «Max bars in chart» متاتریدر باید Unlimited باشد، وگرنه سال‌های قدیمی‌تر نمی‌آیند.
"""

import os
import sys
import time
import zipfile
import datetime as dt

# =====================================================================================
#                    تنظیمات
# =====================================================================================
YEARS_BACK = 6                 # از چند سال قبل تا امروز (عدد اعشاری هم می‌شود)
START_DATE = ""                # یا تاریخ دقیق، مثل "2020-01-01" (اگر پر شود YEARS_BACK نادیده گرفته می‌شود)
END_DATE = ""                  # خالی = تا همین الان
WARMUP_DAYS = 120              # تایم‌های بالاتر از ۵دقیقه از این چند روز قبل از شروع گرفته می‌شوند
YEARS_DIR_NAME = "سال_به_سال"   # پوشه‌ی سال‌های ذخیره‌شده (داخل OUT_DIR)
TIMEFRAMES = [                 # ("برچسب اسم فایل", "تایم‌فریم متاتریدر")
    ("1",   "M1"),
    ("15",  "M15"),
    ("240", "H4"),
]
SYMBOLS = ["XAUUSD"]           # اگر نزد بروکر پسوند دارند (مثلاً XAUUSD.m)، خودش پیدا می‌کند
OUT_DIR = os.path.join(os.path.expanduser("~"), "Desktop", "history_data")
TERMINAL_PATH = ""             # مسیر terminal64.exe — فقط اگر چند متاتریدر نصب است
# =====================================================================================

TF_SECONDS = {"M1": 60, "M5": 300, "M15": 900, "M30": 1800, "H1": 3600,
              "H4": 14400, "D1": 86400, "W1": 604800}
BARS_PER_YEAR = {"M1": 374400, "M5": 74880, "M15": 24960, "M30": 12480, "H1": 6240,
                 "H4": 1560, "D1": 260, "W1": 52}
LTF_NAMES = ("M1", "M5")      # بدون گرم‌کردن (فقط از START_DATE)
YEAR_COMPLETE = 0.85          # سالی ذخیره می‌شود که دست‌کم این سهم از کندل‌های یک سال کامل را داشته باشد


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
    t0, t1 = int(start.timestamp()), int(end.timestamp())
    for attempt in range(4):
        rates = mt5.copy_rates_range(name, tf, start, end)
        if rates is not None and len(rates):         # متاتریدر گاهی یک کندل بی‌ربط بیرون از بازه می‌دهد
            rates = rates[(rates["time"] >= t0) & (rates["time"] < t1)]
        n = 0 if rates is None else len(rates)
        # تاریخچه‌ی این تکه رسیده؟ (شروعش نزدیک شروع درخواست، یا تعدادش دیگر زیاد نمی‌شود)
        if n and (int(rates["time"][0]) <= start.timestamp() + 7 * 86400 or n == best):
            break
        if not n and attempt >= 1:          # دو بار هیچ نیامد → این تکه در متاتریدر دیتا ندارد
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
    b = end
    while b > start:                                   # از جدید به قدیم
        a = max(b - step, start)
        r = _fetch_range(name, tf, a, b)
        if r is not None and len(r):
            parts.append(pd.DataFrame(r))
        elif parts:                                    # قدیمی‌تر از این تکه در متاتریدر دیتا نیست
            break
        b = a
    if not parts:
        return None
    df = pd.concat(parts, ignore_index=True).drop_duplicates("time").sort_values("time")
    df["time"] = pd.to_datetime(df["time"], unit="s")          # ساعت سرور بروکر (مثل خود متاتریدر)
    return df[["time", "open", "high", "low", "close"]].reset_index(drop=True)


def fetch_by_year(name, base, lab, tf_name, start, end, years_dir):
    """کندل‌های بازه، سال‌به‌سال: هر سال تقویمی جدا از متاتریدر گرفته می‌شود و سال‌های تمام‌شده‌ی کامل در
    years_dir ذخیره می‌شوند (دفعه‌ی بعد از همان‌جا خوانده می‌شوند). آخر کار همه‌ی سال‌ها کنار هم."""
    now = dt.datetime.now(dt.timezone.utc)
    folder = os.path.join(years_dir, base)
    os.makedirs(folder, exist_ok=True)
    parts, report = [], []
    for y in range(end.year, start.year - 1, -1):     # از جدید به قدیم
        a = dt.datetime(y, 1, 1, tzinfo=dt.timezone.utc)
        b = min(dt.datetime(y + 1, 1, 1, tzinfo=dt.timezone.utc), end)
        if b <= start or a >= end:
            continue
        path = os.path.join(folder, f"{base}-{lab}-{y}.csv")
        done = b.year > y and b < now                    # سال تمام‌شده
        if done and os.path.exists(path):
            df, src = pd.read_csv(path, parse_dates=["time"]), "ذخیره"
        else:
            df, src = in_range(fetch(name, tf_name, a, b), a, b), ""
            if done and df is not None and len(df) >= YEAR_COMPLETE * BARS_PER_YEAR[tf_name]:
                df.to_csv(path, index=False)
        n = 0 if df is None else len(df)
        report.append(f"{y}: {n:,}" + (f" ({src})" if src and n else ""))
        if n:
            parts.append(df)
        elif parts:                                    # سال‌های قدیمی‌تر در متاتریدر دیتا ندارند
            report.append(f"قبل از {y}: ندارد")
            break
    print(f"   {base:7s} {tf_name:4s} سال‌به‌سال → " + " | ".join(reversed(report)), flush=True)
    if not parts:
        return None
    df = pd.concat(parts, ignore_index=True).drop_duplicates("time").sort_values("time")
    return in_range(df.reset_index(drop=True), start, end)


def in_range(df, a, b):
    """فقط کندل‌های داخل بازه‌ی [a, b) — متاتریدر گاهی برای بازه‌ی بی‌دیتا یک کندل بی‌ربط برمی‌گرداند."""
    if df is None or df.empty:
        return df
    a_ = pd.Timestamp(a.replace(tzinfo=None))
    b_ = pd.Timestamp(b.replace(tzinfo=None))
    return df[(df["time"] >= a_) & (df["time"] < b_)].reset_index(drop=True)


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


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    log_path = os.path.join(OUT_DIR, LOG_NAME)
    try:
        sys.stdout = _Tee(sys.__stdout__, open(log_path, "w", encoding="utf-8"))
    except Exception:
        log_path = None

    print("=" * 64)
    print(" دانلود تاریخچه‌ی کندل از متاتریدر ۵ (سال‌به‌سال)")
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
    years_dir = os.path.join(OUT_DIR, YEARS_DIR_NAME)
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
            tf_start = start if tf_name in LTF_NAMES else start - dt.timedelta(days=WARMUP_DAYS)
            df = drop_open_bar(fetch_by_year(name, base, lab, tf_name, tf_start, end, years_dir), tf_name, last_tick)
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
    print("\nℹ️ اگر سال‌های قدیمی‌ی ۱دقیقه نیامد: متاتریدر → Tools → Options → Charts → Max bars in chart = Unlimited،")
    print("   بعد متاتریدر را کامل ببند و دوباره باز کن و این فایل را دوباره اجرا کن (سال‌های ذخیره‌شده دوباره گرفته نمی‌شوند).")
    print("   بک‌تستر بازه را خودش با دیتای ۱دقیقه هماهنگ می‌کند.")
    print(f"\nفایل‌ها در: {OUT_DIR}")
    if os.path.normcase(os.path.abspath(OUT_DIR)) != os.path.normcase(
            os.path.join(os.path.expanduser("~"), "Desktop", "0")):
        print("برای بک‌تست: فایل‌های ZIP این پوشه را در پوشه‌ی دیتای بک‌تستر کپی کن.")
    if log_path:
        print(f"گزارش کامل این دانلود: {log_path}")
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
    if os.environ.get("EXPORT_FROM_BAT") != "1":
        try:
            input("\nبرای بستن پنجره Enter بزن...")
        except Exception:
            pass
    sys.exit(code)
