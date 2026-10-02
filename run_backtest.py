# -*- coding: utf-8 -*-
"""
بک‌تست استراتژی بیس ۱۵دقیقه با تأیید چاک ۱دقیقه

  ۱) بیس ۱۵دقیقه: کنسالیدیشن اوی + لگ‌اوت قوی + تأیید چاک (لگ‌اوت، بیس مخالف خودش را با بادی بشکند)
  ۲) روند ۴ساعته و روند ۱۵دقیقه هر دو هم‌جهت معامله (ساختار بازار، سقف/کف با ۳ کندل هر طرف)
  ۳) فیلترهای ۴ساعته: داخل زون مخالف نه، تا زون مخالف دست‌کم 3R جا، بعد از ۳ سی‌پی پشت‌سرهم نه
  ۴) قیمت به بیس ۱۵دقیقه برسد → منتظر چاک ۱دقیقه در جهت بیس → اوردر لیمیت روی بیس ۱۵دقیقه
     (ورود +۱۰٪ بیرون از پراکسیمال، استاپ ۲۵٪ پشت دیستال، تارگت 3R، نصف حجم در 2R سیو)
  ۵) فقط تست اول | بیس با کلوز ۱۵دقیقه پشت دیستال باطل | اوردر پرنشده با دور شدن 7R لغو
  ۶) لغو پیش از ورود: روند برگشت | قیمت از زون مخالف ۴ساعته آمده یا (تا ورود) به آن خورد |
     بعد از چاک ۱دقیقه قیمت به بیس مخالف معتبر ۱۵دقیقه خورد

دیتا: پوشه‌ی «0» روی دسکتاپ — برای هر نماد یک ZIP (یا پوشه) با فایل‌های -1.csv، -15.csv و -240.csv
      (خروجی export_data.bat) + spreads.csv برای اسپرد واقعی (export_spreads.bat).
خروجی: پوشه‌ی «خروجی» کنار همین فایل — خلاصه_نتایج.xlsx و پوشه‌ی نمودار_معاملات

ربات لایو: تابع live_state همین موتور را روی دیتای تازه‌ی بروکر اجرا می‌کند و می‌گوید الان کدام اوردرها و
پوزیشن‌ها باید روی حساب باشند (یک مغز برای بک‌تست و لایو، با همین قوانین).
"""
import os
import io
import glob
import bisect
import zipfile

import numpy as np
import pandas as pd

# ============================================================================
# تنظیمات
# ============================================================================
# بازه‌ی معامله — خودکار با دیتای ۱دقیقه هماهنگ می‌شود: از جایی که دیتای ۱دقیقه (بدون جای خالی بزرگ) شروع
# می‌شود تا آخرش. پس این دو عدد فقط سقف بازه‌اند؛ برای همه‌ی دیتای موجود دست نزن.
BACKTEST_START = pd.Timestamp("2015-01-01")
BACKTEST_END = None                                   # None = تا انتهای دیتا
WARMUP_DAYS = 120          # روند و بیس‌ها از این چند روز قبل ساخته می‌شوند؛ در این مدت معامله نیست
ONLY_SYMBOLS = ["XAUUSD"]  # خالی = همه‌ی نمادهای پوشه‌ی دیتا

# ---- بیس ۱۵دقیقه ----
BASE_MAX_CANDLES = 6       # بیس: ۱ تا ۶ کندل که بدنه‌شان حداکثر نصف طول کندل است
LEGOUT_CLEAR_BARS = 3      # کنسالیدیشن اوی: تا ۳ کندل بعد از بیس یک کندل کامل بیرون از بیس (سایه هم به پراکسیمال نخورد)
MIN_LEGOUT_BODY_ATR = 1.0  # لگ‌اوت قوی: بدنه‌ی کندل خروج ≥ این ضریب × ATR(14)
# تأیید چاک: کلوز لگ‌اوت پشت سقف/کفی که «بیس مخالف خودش» ساخته (آخرین بیس مخالفِ نشکسته با کنسالیدیشن
# اوی)، پیش از برگشت قیمت به بیس. بیس از بسته شدن کندل چاک قابل معامله است.

# ---- روند ----
STRUCT_SWING_N = 3         # سقف/کف ساختار: کندلی که از ۳ کندل قبل و ۳ کندل بعدش بالاتر/پایین‌تر است.
#                            روند با کلوز پشت کف/سقف محافظ‌شده (چاک) عوض می‌شود.

# ---- فیلترهای ۴ساعته ----
OPP_ZONE_ROOM_R = 3.0      # فاصله‌ی ورود تا نزدیک‌ترین زون مخالف ۴ساعته ≥ ۳ برابر ریسک (داخل زون مخالف هم ممنوع)
MAX_CONSECUTIVE_CP = 3     # بعد از ۳ بیس هم‌جهت پشت‌سرهم روی ۴ساعته، در آن جهت معامله نمی‌شود

# ---- ورود و مدیریت ----
ENTRY_OFF = 0.10           # ورود: ۱۰٪ ارتفاع بیس بیرون از پراکسیمال (به سمت قیمت)
SL_OFF = 0.25              # استاپ: ۲۵٪ ارتفاع بیس پشت دیستال
RR = 3.0                   # تارگت: 3R
PARTIAL_AT_R = 2.0         # سیو سود: در 2R ...
PARTIAL_FRAC = 0.5         # ... نصف حجم بسته می‌شود

# ---- تأیید ۱دقیقه ----
# قیمت به نقطه‌ی ورود بیس ۱۵دقیقه برسد → منتظر چاک ۱دقیقه در جهت بیس (همان قوانین بیس ۱۵دقیقه) → اوردر
# لیمیت روی بیس ۱۵دقیقه. اگر لحظه‌ی چاک قیمت از نقطه‌ی ورود گذشته باشد، ورود با قیمت بازار.
CHOCH_CLUSTER_GAP_ATR = 1.5    # بیس‌های مخالفِ چسبیده‌ی ۱دقیقه یک بیس‌اند و چاک باید پشت دورترینشان باشد.
CHOCH_CLUSTER_MAX_BARS = 5     # چسبیده = فاصله‌ی قیمتی ≤ ۱.۵×ATR و فاصله‌ی زمانی ≤ ۵ کندل
LTF_TEST_AWAY_R = 1.0          # فقط تست اول: اگر قیمت ۱R دور شد و پیش از چاک برگشت (تست دوم) → لغو
LTF_CANCEL_R = 7.0             # اوردرِ بعد از چاک اگر پر نشد و قیمت 7R دور شد → لغو

# ---- حساب و هزینه‌ها ----
RISK_PER_TRADE = 0.01          # ریسک هر معامله: ۱٪ اکویتی کل حساب
START_EQUITY = 100000.0
SWAP_SPREAD_MULT_PER_NIGHT = 0.2   # سواپ ≈ ۲۰٪ اسپرد برای هر شب نگهداری | کمیسیون: ندارد (دموی MetaQuotes)
# اسپرد: از spreads.csv کنار دیتا (میانه‌ی تیک‌های متاتریدر خودت)؛ اگر نبود، این جدول تقریبی (برحسب قیمت)
SPREAD_TABLE = {
    "EURUSD": 0.00012, "GBPUSD": 0.00018, "AUDUSD": 0.00014, "NZDUSD": 0.00016,
    "USDCAD": 0.00015, "USDCHF": 0.00014,
    "EURAUD": 0.00025, "EURCAD": 0.00022, "EURGBP": 0.00018, "EURNZD": 0.00025,
    "GBPAUD": 0.00030, "GBPCAD": 0.00028, "GBPNZD": 0.00032,
    "AUDCAD": 0.00022, "AUDNZD": 0.00024, "CADJPY": 0.020, "CHFJPY": 0.020,
    "EURJPY": 0.020, "GBPJPY": 0.025, "USDJPY": 0.020, "AUDJPY": 0.020,
    "NZDCAD": 0.00025,
    "XAUUSD": 0.30, "XAGUSD": 0.03,
}

# ---- اجراها: اجرای اصلی + اجراهای مقایسه (هر کدام جدا، روی همان دیتا) ----
MAIN_RUN = "تأیید ۱دقیقه + ورود روی بیس ۱۵دقیقه — فقط تست اول"
EXTRA_RUNS = {
    # نام اجرا: (تنظیمات، توضیح) — اجرایی را که نمی‌خواهی با # غیرفعال کن
    "زون_مخالف_۴ساعته_بدون_اوی": ({"htf_opp_no_oe": True},
        "مثل اجرای اصلی، ولی همه‌ی بیس‌های ۴ساعته‌ی مخالف (حتی بدون کنسالیدیشن اوی) جلوی معامله را می‌گیرند"),
    "لگ‌اوت_بدون_شرط_قدرت": ({"legout_atr": 0.0},
        "مثل اجرای اصلی، ولی بیس ۱۵دقیقه شرط «لگ‌اوت قوی» ندارد (فقط کنسالیدیشن اوی و تأیید چاک)"),
    "لگ‌اوت_نصف": ({"legout_atr": 0.5},
        "مثل اجرای اصلی، ولی لگ‌اوت قوی = بدنه‌ی کندل خروج دست‌کم نصفِ میانگین اندازه‌ی کندل‌ها (به‌جای یک برابر)"),
    "روند_۴ساعته_برگشت_لغو_نشود": ({"keep_on_htf_flip": True},
        "مثل اجرای اصلی، ولی اگر روند ۴ساعته پیش از ورود برگردد اوردر لغو نمی‌شود (فقط برگشت روند ۱۵دقیقه لغو می‌کند)"),
    "خلاف_روند_۴ساعته_با_شرط": ({"counter_htf": True},
        "روند ۴ساعته لازم نیست هم‌جهت باشد (روند ۱۵دقیقه لازم است). معامله‌ی خلاف روند ۴ساعته فقط وقتی که "
        "قیمت از بیس ۴ساعته‌ی هم‌جهت روند ۴ساعته نمی‌آید (مثلاً در روند صعودی ۴ساعته، اگر قیمت از دیمند ۴ساعته "
        "بلند شده، سل نه)"),
}

# ---- خروجی ----
TRADE_CHARTS = True        # نمودار هر معامله (عکس PNG) — به matplotlib نیاز دارد
TRADE_CHARTS_MAX = 400     # حداکثر تعداد نمودار هر اجرا
STOP_CAUSE_DAYS = 30       # برای دلیل استاپ: تا چند روز بعد از ورود نگاه شود (روند ۴ساعته برگشت یا تارگت خورد)
# سشن‌ها: ساعت دیتای بروکر + این عدد = ساعت UTC (دیتای UTC+3 → -3)
SESSION_HOUR_SHIFT = -3
SESSION_RANGES = [         # [شروع، پایان) به ساعت UTC
    (0, 4, "آسیا (توکیو)"),
    (4, 8, "آسیا (پایان)"),
    (8, 12, "لندن"),
    (12, 16, "همپوشانی لندن-نیویورک"),
    (16, 20, "نیویورک"),
    (20, 24, "سیدنی/پایان روز"),
]


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


def _csvs_in_folder(folder):
    """همه‌ی CSVهای یک پوشه (و زیرپوشه‌هایش) → {اسم فایل: مسیر کامل}"""
    out = {}
    for root, _dirs, files in os.walk(folder):
        for fn in files:
            if fn.lower().endswith(".csv"):
                out.setdefault(fn, os.path.join(root, fn))
    return out


class _FolderSource:
    """پوشه‌ی بازشده‌ی یک نماد (مثلاً 0\\XAUUSD\\XAUUSD-15.csv) را مثل یک ZIP می‌خواند."""
    def __init__(self, folder):
        self._files = _csvs_in_folder(folder)

    def namelist(self):
        return list(self._files)

    def read(self, name):
        with open(self._files[name], "rb") as f:
            return f.read()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _open_data_source(path):
    """ZIP یک نماد، یا پوشه‌ی بازشده‌اش (CSVها یا یک ZIP داخلش)."""
    if os.path.isdir(path):
        if _csvs_in_folder(path):
            return _FolderSource(path)
        inner = sorted(glob.glob(os.path.join(path, "**", "*.zip"), recursive=True))
        if inner:
            return zipfile.ZipFile(inner[0], "r")
        raise ValueError(f"داخل پوشه‌ی {path} هیچ فایل CSV یا ZIP نیست.")
    return zipfile.ZipFile(path, "r")


def find_data_sources(datadir):
    """دیتای هر نماد: XAUUSD.zip یا پوشه‌ی بازشده‌ی XAUUSD (اگر هر دو باشد، ZIP) → {نماد: مسیر}"""
    sources = {}
    for zp in sorted(glob.glob(os.path.join(datadir, "*.zip"))):
        sources[os.path.basename(zp).split(".")[0]] = zp
    for d in sorted(glob.glob(os.path.join(datadir, "*"))):
        sym = os.path.basename(d).split(".")[0]
        if os.path.isdir(d) and sym not in sources and (
                _csvs_in_folder(d) or glob.glob(os.path.join(d, "**", "*.zip"), recursive=True)):
            sources[sym] = d
    return {k: sources[k] for k in sorted(sources)}


def load_symbol(path):
    """فایل‌های -15، -240 و -1 (یا -M1) یک نماد → (۱۵دقیقه، ۴ساعته، ۱دقیقه یا None)"""
    with _open_data_source(path) as z:
        names = z.namelist()

        def find(*labels):
            return [n for n in names if any(n.endswith(f"-{lab}.csv") for lab in labels)]

        f15, f4, f1 = find("15"), find("240"), find("1", "M1")
        if not f15 or not f4:
            raise ValueError(f"داخل {path} فایل -15.csv یا -240.csv نیست.")
        df15 = read_mt_csv_from_bytes(z.read(f15[0]))
        df4 = read_mt_csv_from_bytes(z.read(f4[0]))
        m1 = read_mt_csv_from_bytes(z.read(f1[0])) if f1 else None
    return df15, df4, m1


def pip_size(symbol):
    if symbol.endswith("JPY"):
        return 0.01
    if symbol.startswith("XAU"):
        return 0.1
    if symbol.startswith("XAG"):
        return 0.01
    return 0.0001


def load_mt5_spreads(datadir):
    """اسپرد واقعی هر نماد از spreads.csv → {نماد: اسپرد}. میانه‌ی تیک‌ها، نه میانگین (پرش‌های رول‌اوور
    میانگینِ نمادهای کم‌معامله را چند برابر نشان می‌دهد)."""
    path = os.path.join(datadir, "spreads.csv")
    if not os.path.exists(path):
        return {}
    try:
        df = pd.read_csv(path)
        col = "median" if "median" in df.columns else "spread"
        out = {}
        for sym, sp in zip(df["symbol"].astype(str), pd.to_numeric(df[col], errors="coerce")):
            if np.isfinite(sp) and sp > 0:
                out[sym.strip()] = float(sp)
        return out
    except Exception as e:
        print(f"⚠️ spreads.csv خوانده نشد ({e}) — جدول تقریبی SPREAD_TABLE استفاده می‌شود.")
        return {}


# ============================================================================
# روند و بیس‌ها
# ============================================================================
def atr(df: pd.DataFrame, period=14):
    prev_close = df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"], (df["high"] - prev_close).abs(),
                    (df["low"] - prev_close).abs()], axis=1).max(axis=1)
    return tr.rolling(period, min_periods=period).mean()


def swing_points(hi, lo, n):
    """سقف/کف: کندلی که از n کندل قبل و n کندل بعدش بالاتر/پایین‌تر است."""
    N = len(hi)
    sh = np.zeros(N, dtype=bool)
    sl = np.zeros(N, dtype=bool)
    if N < 2 * n + 1:
        return sh, sl
    from numpy.lib.stride_tricks import sliding_window_view as _sw
    wh, wl = _sw(hi, n), _sw(lo, n)
    c = np.arange(n, N - n)
    sh[c] = (hi[c] > wh[c - n].max(axis=1)) & (hi[c] > wh[c + 1].max(axis=1))
    sl[c] = (lo[c] < wl[c - n].min(axis=1)) & (lo[c] < wl[c + 1].min(axis=1))
    return sh, sl


def structure_trend(df, n=3):
    """روند از روی ساختار بازار، بدون نگاه به آینده (سقف/کف بعد از n کندل تأیید می‌شود). 1/-1/0
    - BOS صعودی: کلوز بالای آخرین سقف شکسته‌نشده → «کف محافظ‌شده» = پایین‌ترین کف از آن سقف تا الان.
    - چاک نزولی: کلوز زیر کف محافظ‌شده → روند نزولی (برعکسش برای روند نزولی).
      کف/سقف‌های ریزِ داخل اصلاح روند را عوض نمی‌کنند."""
    hi = df["high"].to_numpy(dtype=float)
    lo = df["low"].to_numpy(dtype=float)
    cl = df["close"].to_numpy(dtype=float)
    N = len(df)
    out = np.zeros(N, dtype=int)
    sh, sl = swing_points(hi, lo, n)
    trend, prot, prot_i = 0, np.nan, -1
    last_sh, sh_live, last_sl, sl_live = -1, False, -1, False
    for i in range(N):
        k = i - n
        if k >= 0:
            if sh[k]:
                last_sh, sh_live = k, True
            if sl[k]:
                last_sl, sl_live = k, True
        c = cl[i]
        new = 0
        if trend == 0:
            if sh_live and c > hi[last_sh]:
                sh_live, new = False, 1
            elif sl_live and c < lo[last_sl]:
                sl_live, new = False, -1
        elif trend > 0:
            if sh_live and c > hi[last_sh]:                       # BOS صعودی
                sh_live = False
                k2 = last_sh + int(np.argmin(lo[last_sh:i + 1]))
                prot, prot_i = lo[k2], k2
            elif c < prot:                                        # چاک نزولی
                new = -1
        else:
            if sl_live and c < lo[last_sl]:                       # BOS نزولی
                sl_live = False
                k2 = last_sl + int(np.argmax(hi[last_sl:i + 1]))
                prot, prot_i = hi[k2], k2
            elif c > prot:                                        # چاک صعودی
                new = 1
        if new > 0:
            s0 = prot_i if (trend < 0 and prot_i >= 0) else max(last_sh, 0)
            k2 = s0 + int(np.argmin(lo[s0:i + 1]))
            prot, prot_i = lo[k2], k2
            if last_sh >= 0 and c > hi[last_sh]:
                sh_live = False
            trend = 1
        elif new < 0:
            s0 = prot_i if (trend > 0 and prot_i >= 0) else max(last_sl, 0)
            k2 = s0 + int(np.argmax(hi[s0:i + 1]))
            prot, prot_i = hi[k2], k2
            if last_sl >= 0 and c < lo[last_sl]:
                sl_live = False
            trend = -1
        out[i] = trend
    return pd.Series(out, index=df.index)


class Zone:
    def __init__(self, direction, proximal, distal, created_time, base_start, base_end):
        self.direction = direction
        self.proximal = float(proximal)
        self.distal = float(distal)
        self.created_time = created_time   # از این لحظه قابل معامله (کندل کنسالیدیشن اوی، بعداً کندل چاک)
        self.base_start = base_start
        self.base_end = base_end
        self.superseded_time = None        # بیس جدیدِ هم‌پوشان از این لحظه جایش را می‌گیرد
        self.replaced_at = None            # زمان تولد همان بیس جدید (برای شمردن سی‌پی‌ها)
        self.conf_body_atr = 0.0           # بدنه‌ی کندل لگ‌اوت نسبت به ATR

    def low(self):
        return min(self.proximal, self.distal)

    def high(self):
        return max(self.proximal, self.distal)


def build_zones(df, max_base_len, atr_s, legout_clear=None, weak_out=None):
    """بیس‌ها با کنسالیدیشن اوی. بیس = ۱ تا max_base_len کندل با بدنه ≤ نصف طول کندل؛ لگ‌اوت = اولین کندل
    بعدی با بدنه > نصف طول که بیرون از بیس بسته شود. پراکسیمال = لبه‌ی بدنه‌ها (اگر همه‌ی کندل‌های بیس دوجی
    کوچک باشند، لبه‌ی سایه‌ها). legout_clear = تعداد کندل کنسالیدیشن اوی (۰ = بدون این شرط).
    weak_out: بیس‌هایی که کنسالیدیشن اوی ندادند هم به این فهرست اضافه می‌شوند (برای بیس‌های چسبیده‌ی چاک)."""
    o = df["open"].to_numpy(dtype=float)
    h = df["high"].to_numpy(dtype=float)
    l = df["low"].to_numpy(dtype=float)
    c = df["close"].to_numpy(dtype=float)
    times = df["time"].to_numpy()
    atr_a = np.asarray(atr_s, dtype=float)
    n = len(df)
    lc = LEGOUT_CLEAR_BARS if legout_clear is None else legout_clear

    rng = h - l
    body = np.abs(c - o)
    with np.errstate(invalid="ignore", divide="ignore"):
        ratio = np.where(rng > 0, body / rng, np.inf)
    is_base = (rng > 0) & (body <= 0.5 * rng)
    is_strong = (rng > 0) & (body > 0.5 * rng)
    is_doji = (rng > 0) & np.isfinite(atr_a) & (atr_a > 0) & (ratio <= 0.20) & (rng <= 0.80 * atr_a)
    body_max = np.maximum(o, c)
    body_min = np.minimum(o, c)

    zones = []
    i = 0
    while i < n - 3:
        made = None
        for L in range(1, max_base_len + 1):
            if i + L >= n or not is_base[i:i + L].all():
                break
            base_high = float(h[i:i + L].max())
            base_low = float(l[i:i + L].min())
            j = i + L
            if not is_strong[j]:
                continue
            bull, bear = c[j] > base_high, c[j] < base_low
            if not (bull or bear):
                continue
            doji = bool(is_doji[i:i + L].all())
            if bull:
                direction = "BUY"
                proximal = base_high if doji else float(body_max[i:i + L].max())
                distal = base_low
            else:
                direction = "SELL"
                proximal = base_low if doji else float(body_min[i:i + L].min())
                distal = base_high
            # کنسالیدیشن اوی: تا lc کندل (از کندل لگ‌اوت) یک کندل کامل بیرون از بیس؛ بیس از بسته شدن آن معتبر است
            born = j
            if lc:
                born = None
                for k2 in range(j, min(j + lc, n)):
                    if (direction == "BUY" and l[k2] > proximal) or (direction == "SELL" and h[k2] < proximal):
                        born = k2
                        break
                if born is None:
                    if weak_out is not None:
                        weak_out.append(Zone(direction, proximal, distal, times[j], times[i], times[j - 1]))
                    break
            z = Zone(direction, proximal, distal, times[born], times[i], times[j - 1])
            atr_j = atr_a[j] if j < len(atr_a) else np.nan
            z.conf_body_atr = float(body[j] / atr_j) if (np.isfinite(atr_j) and atr_j > 0) else 0.0
            made = (L, z)
            break
        if made:
            zones.append(made[1])
            i += made[0] + 1
        else:
            i += 1
    return zones


def choch_confirm_zones(zones, df, min_body_atr=0.0, weak=None, cluster_gap_atr=None, cluster_max_bars=None):
    """فقط بیس‌هایی که لگ‌اوت قوی دارند (بدنه ≥ min_body_atr × ATR) و چاک داده‌اند.

    چاک = لگ‌اوتِ بیس، سقف/کفی را که «بیس مخالف خودش» ساخته با بادی (کلوز کندل) رد کند:
      دیمند: بیس مخالف = آخرین سوپلایِ شکسته‌نشده‌ی بالای بیس که پیش از شروع بیس متولد شده و
             کنسالیدیشن اوی داده. سطح چاک = بالاترین high از شروع آن سوپلای تا شروع دیمند.
      سوپلای: برعکس — آخرین دیمند زیر بیس؛ سطح چاک = پایین‌ترین low.
    بیس‌های مخالفِ چسبیده به آن (با یا بدون کنسالیدیشن اوی؛ weak = بیس‌های بدون اوی) یک بیس حساب
    می‌شوند و چاک باید پشت دورترینشان بسته شود. چسبیده = حداکثر cluster_max_bars کندل و
    cluster_gap_atr × ATR فاصله (فاصله‌ی قیمتی دو بیس یا دور شدن قیمت بینشان). ۰ = خاموش.
    چاک باید پیش از برگشت قیمت به بیس اتفاق بیفتد. بیس از بسته شدن دیرترینِ کندل کنسالیدیشن
    اوی و کندل چاک قابل معامله است (بدون نگاه به آینده)."""
    if not zones:
        return []
    gap_k = CHOCH_CLUSTER_GAP_ATR if cluster_gap_atr is None else cluster_gap_atr
    gap_n = CHOCH_CLUSTER_MAX_BARS if cluster_max_bars is None else cluster_max_bars
    tt = df["time"].to_numpy(dtype="datetime64[ns]")
    cl = df["close"].to_numpy(dtype=float)
    hi = df["high"].to_numpy(dtype=float)
    lo = df["low"].to_numpy(dtype=float)
    atr_a = (df["atr"] if "atr" in df.columns else atr(df)).to_numpy(dtype=float)
    N = len(cl)
    B = 256
    nb = (N + B - 1) // B
    pad = nb * B - N
    cmax = np.pad(cl, (0, pad), constant_values=-np.inf).reshape(nb, B).max(axis=1)
    cmin = np.pad(cl, (0, pad), constant_values=np.inf).reshape(nb, B).min(axis=1)

    def first_beyond(start, level, above):
        """اولین کندل از start به بعد که کلوزش بالای level (above) یا زیر آن بسته شده؛ N = هیچ‌وقت"""
        if start >= N:
            return N
        b0 = start // B
        seg = cl[start:min((b0 + 1) * B, N)]
        m = (seg > level) if above else (seg < level)
        if m.any():
            return start + int(np.argmax(m))
        bm = (cmax[b0 + 1:] > level) if above else (cmin[b0 + 1:] < level)
        if not bm.any():
            return N
        b = b0 + 1 + int(np.argmax(bm))
        seg = cl[b * B:min((b + 1) * B, N)]
        m = (seg > level) if above else (seg < level)
        return b * B + int(np.argmax(m))

    def idx(t):
        return int(np.searchsorted(tt, np.datetime64(pd.Timestamp(t), "ns")))

    allz = list(zones) + list(weak or [])
    nq = len(zones)
    born = np.array([idx(z.created_time) for z in allz], dtype=np.int64)   # کندل کنسالیدیشن اوی
    bs = np.array([idx(z.base_start) for z in allz], dtype=np.int64)       # اولین کندل بیس
    be = np.array([idx(z.base_end) for z in allz], dtype=np.int64)         # آخرین کندل بیس
    buy = np.array([z.direction == "BUY" for z in allz], dtype=bool)
    oe = np.arange(len(allz)) < nq                                         # کنسالیدیشن اوی داده؟
    zlo = np.array([z.low() for z in allz], dtype=float)
    zhi = np.array([z.high() for z in allz], dtype=float)
    # کندلی که هر بیس در آن شکست: دیمند با کلوز زیر کفش، سوپلای با کلوز بالای سقفش
    brk = np.array([first_beyond(int(born[q]) + 1, zlo[q] if buy[q] else zhi[q], not buy[q])
                    for q in range(len(allz))], dtype=np.int64)

    # بیس‌های «زنده» هر جهت به ترتیب پایان بیس؛ بیس‌ها به ترتیب شروع بررسی می‌شوند
    ins = np.argsort(born, kind="stable")
    alive = {True: [], False: []}
    p_ins = 0
    out = []
    for q in sorted(range(nq), key=lambda q_: bs[q_]):
        z = zones[q]
        s0 = int(bs[q])
        while p_ins < len(allz) and born[ins[p_ins]] < s0:
            k_ = int(ins[p_ins])
            bisect.insort(alive[bool(buy[k_])], (int(be[k_]), k_))
            p_ins += 1
        if min_body_atr > 0 and z.conf_body_atr < min_body_atr:
            continue
        lst = alive[not buy[q]]

        def beyond(k_):
            return (zhi[k_] > zhi[q]) if buy[q] else (zlo[k_] < zlo[q])

        # بیس مخالف خودش = آخرین بیس مخالفِ زنده با کنسالیدیشن اوی که آن طرف بیس است
        j = len(lst) - 1
        opp = -1
        while j >= 0:
            k_ = lst[j][1]
            if brk[k_] < s0:                    # شکسته شده؛ دیگر هیچ‌وقت زنده نمی‌شود
                del lst[j]
                j -= 1
                continue
            if oe[k_] and beyond(k_):
                opp = k_
                break
            j -= 1
        if opp < 0:
            continue
        # بیس‌های مخالفِ چسبیده به آن (قدیمی‌ترها) هم جزو همان بیس‌اند
        a0 = int(bs[opp])
        c_lo, c_hi = zlo[opp], zhi[opp]
        atr_q = atr_a[min(int(be[q]), N - 1)]
        if gap_k > 0 and np.isfinite(atr_q) and atr_q > 0:
            jj = j - 1
            while jj >= 0:
                k_ = lst[jj][1]
                jj -= 1
                if brk[k_] < s0:
                    continue
                if not beyond(k_):
                    break
                if a0 - int(be[k_]) - 1 > gap_n:
                    break
                # فاصله = فاصله‌ی قیمتی دو بیس یا اینکه قیمت بینشان چقدر دور شد (هر کدام بیشتر)
                dist_ = max(0.0, zlo[k_] - c_hi, c_lo - zhi[k_])
                e0, e1 = int(be[k_]) + 1, a0
                if e1 > e0:
                    if buy[q]:
                        dist_ = max(dist_, min(zlo[k_], c_lo) - float(lo[e0:e1].min()))
                    else:
                        dist_ = max(dist_, float(hi[e0:e1].max()) - max(zhi[k_], c_hi))
                if dist_ > gap_k * atr_q:
                    break
                c_lo, c_hi = min(c_lo, zlo[k_]), max(c_hi, zhi[k_])
                a0 = min(a0, int(bs[k_]))
        if buy[q]:
            level = float(hi[a0:s0].max())                              # سقفِ دورترین بیس مخالف
        else:
            level = float(lo[a0:s0].min())                              # کفِ دورترین بیس مخالف
        k = first_beyond(int(be[q]) + 1, level, bool(buy[q]))           # کلوز بادی پشت سطح = چاک
        if k >= N:
            continue
        b = int(born[q])
        if k > b:
            touched = (lo[b + 1:k + 1].min() <= zhi[q]) if buy[q] else (hi[b + 1:k + 1].max() >= zlo[q])
            if touched:                                                  # قیمت پیش از چاک به بیس برگشت
                continue
        z.created_time = tt[max(k, b)]
        # برای نمودار معاملات: سطح چاک، از کجا (شروع بیس مخالف) و کندل چاک
        z.choch_level, z.choch_from, z.choch_time = level, tt[a0], tt[k]
        out.append(z)
    out.sort(key=lambda z_: pd.Timestamp(z_.created_time))
    return out


def _first_close_beyond(cl, start, level, above):
    """اولین کندل از start به بعد که کلوزش بالای level (above) یا زیر آن بسته شده؛ len(cl) = هیچ‌وقت"""
    n_ = len(cl)
    a_ = max(int(start), 0)
    while a_ < n_:
        seg = cl[a_:min(a_ + 4096, n_)]
        m_ = (seg > level) if above else (seg < level)
        if m_.any():
            return a_ + int(np.argmax(m_))
        a_ += 4096
    return n_


def overlap_ratio(a_low, a_high, b_low, b_high):
    inter = max(0.0, min(a_high, b_high) - max(a_low, b_low))
    uni = max(a_high, b_high) - min(a_low, b_low)
    return inter / uni if uni > 0 else 0.0


def dedup_zones_pit(zones, lag, thr=0.55):
    """حذف بیس‌های هم‌پوشان بدون نگاه به آینده: هر بیس جدید، بیس‌های هم‌پوشانِ قبلی را از بسته شدن کندلی که
    خودش را تأیید می‌کند (زمان تولد + lag = طول کندل) به بعد جایگزین می‌کند و محدوده‌اش با آن‌ها تنگ‌تر می‌شود."""
    zones = sorted(zones, key=lambda z: z.created_time)
    active = []
    for z in zones:
        for old in active:
            if overlap_ratio(z.low(), z.high(), old.low(), old.high()) >= thr:
                old.superseded_time = np.datetime64(pd.Timestamp(z.created_time) + lag, "ns")
                old.replaced_at = z.created_time
                low = max(z.low(), old.low()); high = min(z.high(), old.high())
                if low < high:
                    if z.direction == "BUY":
                        z.proximal = high; z.distal = low
                    else:
                        z.proximal = low; z.distal = high
        active = [a for a in active if a.superseded_time is None]
        active.append(z)
    return zones


def dirs_allowed(dtr, htr):
    """جهت مجاز: روند ۴ساعته (dtr) و روند ۱۵دقیقه (htr) هر دو هم‌جهت معامله."""
    if dtr == htr == 1:
        return ("BUY",)
    if dtr == htr == -1:
        return ("SELL",)
    return ()


# ============================================================================
# موتور بک‌تست
# ============================================================================
class AccountBook:
    """حساب مشترک همه‌ی نمادها."""
    def __init__(self):
        self.equity = self.start_equity = self.peak = START_EQUITY
        self.max_dd = 0.0

    def risk_amount(self):
        return self.equity * RISK_PER_TRADE

    def apply_result(self, risk_amt, result_r):
        self.equity += float(risk_amt) * float(result_r)
        self.peak = max(self.peak, self.equity)
        if self.peak > 0:
            self.max_dd = max(self.max_dd, (self.peak - self.equity) / self.peak)


# شمارنده‌های هر اجرا (برای قیف و جدول «کلی»)
COUNT_KEYS = ("reach", "choch1", "filled", "market", "f_all", "f_oe", "f_strong", "f_choch", "f_dedup", "f_ready")
# دلیل آماده‌نشدن بیس (برای قیف)
_BLOCK_CODE = {"trend4": 1, "inside": 2, "near": 3, "cp": 4, "trend15": 5, "trend_both": 6, "origin": 7}
_LAST_FATE = {0: "n_dead", 1: "n_trend4", 2: "n_inside", 3: "n_near", 4: "n_cp", 5: "n_trend15",
              6: "n_trend_both", 7: "n_origin"}


def _symbol_metrics(symbol, trades, equity, max_dd, spread_ref):
    pip = pip_size(symbol)
    m = {"نماد": symbol, "تعداد": len(trades), "درصد_برد": 0.0, "فاکتور_سود": 0.0, "میانگین_R": 0.0,
         "بازده_خالص٪": 0.0, "حداکثر_افت٪": 0.0, "فاصله_استاپ_پیپ": 0.0, "هزینه_هر_معامله_R": 0.0,
         "اسپرد_پیپ": round(spread_ref / pip, 2)}
    if trades.empty:
        return m
    R = trades["نتیجه_R"]
    loss = R[R < 0].abs().sum()
    m.update({"درصد_برد": round(float((R > 0).mean() * 100.0), 2),
              "فاکتور_سود": round(float(R[R > 0].sum() / loss) if loss > 0 else 999.0, 3),
              "میانگین_R": round(float(R.mean()), 3),
              "بازده_خالص٪": round(float((equity - START_EQUITY) / START_EQUITY * 100.0), 2),
              "حداکثر_افت٪": round(max_dd * 100.0, 2),
              "فاصله_استاپ_پیپ": round(float(((trades["ورود"] - trades["حدضرر"]).abs() / pip).mean()), 1),
              # میانه: چند استاپ خیلی ریز میانگین را گمراه می‌کنند
              "هزینه_هر_معامله_R": round(float(trades["هزینه_R"].median()), 3)})
    return m


_M1_CACHE = {}


def backtest_symbol(symbol, df15, df4, m1, spread, book,
                    htf_opp_no_oe=False, legout_atr=None, counter_htf=False, keep_on_htf_flip=False,
                    live_from=None):
    """موتور استراتژی برای یک نماد (generator): سر هر کندل ۱۵دقیقه زمانش را yield می‌کند تا همه‌ی نمادها
    هم‌قدم روی یک حساب جلو بروند. خروجی: (کارنامه، شمارنده‌ها، جدول معاملات)

    htf_opp_no_oe: همه‌ی بیس‌های ۴ساعته‌ی مخالف (حتی بدون کنسالیدیشن اوی) جلوی معامله را می‌گیرند
    legout_atr: ضریب لگ‌اوت قوی بیس ۱۵دقیقه به‌جای MIN_LEGOUT_BODY_ATR
    counter_htf: روند ۴ساعته لازم نیست؛ خلاف روند ۴ساعته فقط اگر قیمت از بیس ۴ساعته‌ی هم‌جهت آن روند نمی‌آید
    keep_on_htf_flip: برگشت روند ۴ساعته پیش از ورود اوردر را لغو نمی‌کند (فقط برگشت روند ۱۵دقیقه)
    live_from: حالت ربات لایو (live_state) — معامله از این زمان تا انتهای دیتا و خروجی = وضعیت همین الان"""
    bt_start = BACKTEST_START if live_from is None else pd.Timestamp(live_from)
    bt_end = BACKTEST_END if live_from is None else None
    warm_start = bt_start - pd.Timedelta(days=WARMUP_DAYS)
    spread_ref = float(spread) if float(spread) > 0 else float(SPREAD_TABLE.get(symbol, 0.0))
    spr = float(spread)        # قیمت‌ها Bid اند: خرید لیمیت با Ask (= Bid + اسپرد) پر و فروش با Ask بسته می‌شود
    swap_per_night = SWAP_SPREAD_MULT_PER_NIGHT * float(spread)
    counts = dict.fromkeys(COUNT_KEYS, 0)       # + سرنوشت هر بیس (کلیدهای FATE_ROWS)

    df15 = df15.copy(); df4 = df4.copy()
    for df in (df15, df4):
        for col in ("open", "high", "low", "close"):
            df[col] = df[col].astype(float)
        df["atr"] = atr(df)                 # روی کل دیتا (گرم)
    if bt_end is not None:
        df15 = df15[df15["time"] <= bt_end].copy()
        df4 = df4[df4["time"] <= bt_end].copy()
        m1 = m1[m1["time"] <= bt_end].copy()
    a15, a4 = df15[df15["time"] >= warm_start], df4[df4["time"] >= warm_start]
    if a15.empty or a4.empty or m1.empty:
        if live_from is not None:
            return {"time": None, "allowed": (), "orders": [], "watching": [], "positions": [], "closed": []}
        return _symbol_metrics(symbol, pd.DataFrame(), START_EQUITY, 0.0, spread_ref), counts, pd.DataFrame()
    global_start = max(warm_start, a15["time"].min(), a4["time"].min())
    df15 = df15[df15["time"] >= global_start].reset_index(drop=True)
    df4 = df4[df4["time"] >= global_start].reset_index(drop=True)
    df15["trend"] = structure_trend(df15, n=STRUCT_SWING_N)
    df4["trend"] = structure_trend(df4, n=STRUCT_SWING_N)

    def _span(df, default):
        dd = df["time"].diff().dropna()
        return pd.Timedelta(dd.median()) if len(dd) else default
    span15 = _span(df15, pd.Timedelta(minutes=15))
    span4 = _span(df4, pd.Timedelta(hours=4))

    # ---------- بیس‌های ۱۵دقیقه: کنسالیدیشن اوی → لگ‌اوت قوی + تأیید چاک → حذف هم‌پوشان‌ها ----------
    lo_atr = MIN_LEGOUT_BODY_ATR if legout_atr is None else float(legout_atr)
    weak15 = []
    raw = build_zones(df15, BASE_MAX_CANDLES, df15["atr"], weak_out=weak15)
    # قیف: فقط بیس‌هایی که در بازه‌ی معامله متولد شده‌اند
    p0 = pd.Timestamp(bt_start)
    p1 = pd.Timestamp(bt_end) if bt_end is not None else pd.Timestamp.max
    in_p = lambda t_: p0 <= pd.Timestamp(t_) <= p1
    counts["f_oe"] = sum(in_p(z.created_time) for z in raw)
    counts["f_strong"] = sum(in_p(z.created_time) for z in raw if z.conf_body_atr >= lo_atr)
    counts["f_all"] = counts["f_oe"] + sum(in_p(z.base_end) for z in weak15)
    raw = choch_confirm_zones(raw, df15, min_body_atr=lo_atr, cluster_gap_atr=0.0)   # بیس‌های چسبیده فقط ۱دقیقه
    counts["f_choch"] = sum(in_p(z.created_time) for z in raw)
    zones = dedup_zones_pit(raw, span15)
    # شناسه‌ی پایدار هر بیس (ربات لایو سفارش‌ها را با همین شناسه در کامنت سفارش پیدا می‌کند)
    seen = {}
    for z in zones:
        zid = f"{symbol}_M15_{pd.Timestamp(z.created_time):%y%m%d%H%M}{'B' if z.direction == 'BUY' else 'S'}"
        seen[zid] = seen.get(zid, 0) + 1
        z.zone_id = zid if seen[zid] == 1 else f"{zid}{seen[zid]}"

    # ---------- بیس‌های ۴ساعته (با کنسالیدیشن اوی): زون مخالف و سی‌پی‌ها ----------
    zones4 = dedup_zones_pit(build_zones(df4, BASE_MAX_CANDLES, df4["atr"]), span4)

    def _htf_arrays(zs):
        """هر زون ۴ساعته از بسته شدن کندل تولدش معتبر است تا جایگزین شود یا کندل ۴ساعته پشت دیستالش بسته شود."""
        n_ = len(zs)
        f_ = np.empty(n_, dtype="datetime64[ns]")
        u_ = np.empty(n_, dtype="datetime64[ns]")
        tt = df4["time"].to_numpy(dtype="datetime64[ns]")
        cc = df4["close"].to_numpy(dtype=float)
        lag64 = np.timedelta64(pd.Timedelta(span4).value, "ns")
        for q, hz in enumerate(zs):
            f_[q] = np.datetime64(pd.Timestamp(hz.created_time) + span4, "ns")
            end = (np.datetime64(pd.Timestamp(hz.superseded_time), "ns") if hz.superseded_time is not None
                   else np.datetime64("2262-01-01", "ns"))
            k0 = int(np.searchsorted(tt, f_[q], side="left"))
            if k0 < len(tt):
                bad = (cc[k0:] < hz.low()) if hz.direction == "BUY" else (cc[k0:] > hz.high())
                if bad.any():
                    end = min(end, tt[k0 + int(np.argmax(bad))] + lag64)
            u_[q] = end
        return (f_, u_, np.array([hz.low() for hz in zs], dtype=float),
                np.array([hz.high() for hz in zs], dtype=float),
                np.array([hz.direction == "BUY" for hz in zs], dtype=bool))

    hz_from = None
    if len(zones4):
        opp4 = (dedup_zones_pit(build_zones(df4, BASE_MAX_CANDLES, df4["atr"], legout_clear=0), span4)
                if htf_opp_no_oe else zones4)
        hz_from, hz_until, hz_lo, hz_hi, hz_buy = _htf_arrays(opp4)
        hz_f_ns, hz_u_ns = hz_from.astype(np.int64), hz_until.astype(np.int64)

    def htf_zone_block(direction, price, t_now):
        """قیمت داخل دیمند ۴ساعته → سل ممنوع | داخل سوپلای ۴ساعته → بای ممنوع"""
        if hz_from is None:
            return False
        tt = np.datetime64(pd.Timestamp(t_now), "ns")
        m = (hz_from <= tt) & (tt < hz_until) & (hz_lo <= price) & (price <= hz_hi)
        return bool((m & hz_buy).any()) if direction == "SELL" else bool((m & ~hz_buy).any())

    def opp_room_block(direction, entry_price, risk_price, t_now):
        """فاصله‌ی ورود تا نزدیک‌ترین زون مخالف ۴ساعته (در مسیر تارگت) کمتر از OPP_ZONE_ROOM_R برابر ریسک؟"""
        if hz_from is None or OPP_ZONE_ROOM_R <= 0 or risk_price <= 0:
            return False
        tt = np.datetime64(pd.Timestamp(t_now), "ns")
        m = (hz_from <= tt) & (tt < hz_until)
        if direction == "BUY":
            s_ = m & ~hz_buy & (hz_lo > entry_price)
            return bool(s_.any()) and (float(hz_lo[s_].min()) - entry_price) < OPP_ZONE_ROOM_R * risk_price
        s_ = m & hz_buy & (hz_hi < entry_price)
        return bool(s_.any()) and (entry_price - float(hz_hi[s_].max())) < OPP_ZONE_ROOM_R * risk_price

    # سی‌پی‌های پشت‌سرهم روی ۴ساعته: هنگام تولد هر زون، چند زونِ هم‌جهت پشت‌سرهم (بدون زون مخالف بینشان)
    # تا آن لحظه ساخته شده؛ زونی که جای زون قبلی را گرفته دوبار شمرده نمی‌شود
    cp_zs = sorted(zones4, key=lambda z: z.created_time)
    cp_t = np.array([np.datetime64(pd.Timestamp(z.created_time) + span4, "ns") for z in cp_zs],
                    dtype="datetime64[ns]")
    cp_run = np.zeros(len(cp_zs), dtype=int)
    seq = []
    for q, z in enumerate(cp_zs):
        ct = z.created_time
        seq = [r for r in seq if not (cp_zs[r].replaced_at is not None and cp_zs[r].replaced_at <= ct)]
        seq = (seq + [q])[-60:]
        run = 0
        for r in reversed(seq):
            if cp_zs[r].direction != z.direction:
                break
            run += 1
        cp_run[q] = run

    def cp_block(direction, t_now):
        if not MAX_CONSECUTIVE_CP or not len(cp_zs):
            return False
        k = int(np.searchsorted(cp_t, np.datetime64(pd.Timestamp(t_now), "ns"), side="left")) - 1
        return k >= 0 and cp_zs[k].direction == direction and cp_run[k] >= MAX_CONSECUTIVE_CP

    risk_h = 1.0 + ENTRY_OFF + SL_OFF            # فاصله‌ی ورود تا استاپ برحسب ارتفاع بیس

    def htf_block(z, t_now, price):
        """فیلترهای ۴ساعته؛ None = قبول، وگرنه دلیل رد. price = قیمت باز شدن کندل."""
        height = z.high() - z.low()
        ent = z.proximal + ENTRY_OFF * height if z.direction == "BUY" else z.proximal - ENTRY_OFF * height
        if cp_block(z.direction, t_now):
            return "cp"
        if htf_zone_block(z.direction, price, t_now):
            return "inside"
        if opp_room_block(z.direction, ent, height * risk_h, t_now):
            return "near"
        return None

    # ---------- قیمت از بیس ۴ساعته‌ی کدام طرف می‌آید (برای اجرای «خلاف روند ۴ساعته») ----------
    # برای هر کندل ۴ساعته: آخرین بیس ۴ساعته‌ای (بدون شرط کنسالیدیشن اوی) که قیمت به آن رسید و نشکستش.
    # +1 = قیمت از یک دیمند ۴ساعته می‌آید، -1 = از یک سوپلای، 0 = هیچ (یا آن بیس بعداً شکست).
    origin = None
    if counter_htf:
        oz = dedup_zones_pit(build_zones(df4, BASE_MAX_CANDLES, df4["atr"], legout_clear=0), span4)
        origin = np.zeros(len(df4), dtype=np.int8)
        if oz:
            d_t = df4["time"].to_numpy(dtype="datetime64[ns]")
            o4, h4, l4, c4 = (df4[k_].to_numpy(dtype=float) for k_ in ("open", "high", "low", "close"))
            zf = np.array([np.datetime64(pd.Timestamp(z_.created_time) + span4, "ns") for z_ in oz])
            zs = np.array([np.datetime64(pd.Timestamp(z_.superseded_time), "ns") if z_.superseded_time is not None
                           else np.datetime64("2262-01-01", "ns") for z_ in oz])
            zlo = np.array([z_.low() for z_ in oz]); zhi = np.array([z_.high() for z_ in oz])
            zb = np.array([z_.direction == "BUY" for z_ in oz])
            dead = np.zeros(len(oz), dtype=bool)
            st, stz = 0, -1
            for k4 in range(len(df4)):
                v = (zf <= d_t[k4]) & (d_t[k4] < zs) & ~dead
                br = v & ((zb & (c4[k4] < zlo)) | (~zb & (c4[k4] > zhi)))
                tc = v & ~br & (h4[k4] >= zlo) & (l4[k4] <= zhi)
                dead |= br
                td, ts = tc & zb, tc & ~zb
                if td.any() or ts.any():
                    if td.any() and (not ts.any() or c4[k4] >= o4[k4]):
                        st, stz = 1, int(np.flatnonzero(td)[-1])
                    else:
                        st, stz = -1, int(np.flatnonzero(ts)[-1])
                if stz >= 0 and dead[stz]:
                    st, stz = 0, -1
                origin[k4] = st

    # ---------- تأیید ۱دقیقه: بیس‌های ۱دقیقه‌ای که چاک داده‌اند (همان قوانین بیس ۱۵دقیقه) ----------
    m1_t = m1["time"].values
    m1_o = m1["open"].astype(float).values
    m1_h = m1["high"].astype(float).values
    m1_l = m1["low"].astype(float).values
    m1_c = m1["close"].astype(float).values
    m1_t_ns = m1_t.astype("datetime64[ns]").astype(np.int64)
    key1 = (len(m1), m1_t_ns[0], m1_t_ns[-1], MIN_LEGOUT_BODY_ATR, CHOCH_CLUSTER_GAP_ATR, CHOCH_CLUSTER_MAX_BARS,
            LEGOUT_CLEAR_BARS, BASE_MAX_CANDLES)
    cached = _M1_CACHE.get(symbol)
    if live_from is None and cached is not None and cached[0] == key1:
        z1, L_buy, L_lo, L_hi, L_be, conf_at = cached[1]
    else:
        m1df = pd.DataFrame({"time": m1_t, "open": m1_o, "high": m1_h, "low": m1_l, "close": m1_c})
        m1df["atr"] = atr(m1df)
        weak1 = []
        z1 = build_zones(m1df, BASE_MAX_CANDLES, m1df["atr"], weak_out=weak1)
        z1 = choch_confirm_zones(z1, m1df, min_body_atr=MIN_LEGOUT_BODY_ATR, weak=weak1)
        L_buy = np.array([z.direction == "BUY" for z in z1], dtype=bool)
        L_lo = np.array([z.low() for z in z1], dtype=float)
        L_hi = np.array([z.high() for z in z1], dtype=float)
        L_be = np.array([np.searchsorted(m1_t, np.datetime64(pd.Timestamp(z.base_end), "ns")) for z in z1],
                        dtype=np.int64)
        conf_at = {}                     # کندل ۱دقیقه‌ای که چاک در آن بسته شد → بیس‌های ۱دقیقه
        for q1, z in enumerate(z1):
            conf_at.setdefault(int(np.searchsorted(m1_t, np.datetime64(pd.Timestamp(z.created_time), "ns"))),
                               []).append(q1)
        if live_from is None:            # بیس‌های ۱دقیقه در همه‌ی اجراها یکی‌اند؛ یک بار ساخته می‌شوند
            _M1_CACHE[symbol] = (key1, (z1, L_buy, L_lo, L_hi, L_be, conf_at))
    span15_ns = np.timedelta64(span15.value, "ns")

    def m1_range(t_bar):
        """کندل‌های ۱دقیقه‌ی داخل یک کندل ۱۵دقیقه → (i0, i1) یا None"""
        t0 = t_bar.to_datetime64()
        i0 = int(np.searchsorted(m1_t, t0, side="left"))
        i1 = int(np.searchsorted(m1_t, t0 + span15_ns, side="left"))
        return (i0, i1) if i1 > i0 else None

    # ---------- پوزیشن‌ها ----------
    equity, peak, max_dd = START_EQUITY, START_EQUITY, 0.0
    trades = []

    def process_pos_candle(pos, h, l, fav=None):
        """خروج/سیو سود یک پوزیشن در یک کندل — بدبینانه (اگر استاپ و تارگت هر دو لمس شدند، استاپ).
        fav: در کندل ورود، بهترین قیمتی که «بعد از پر شدن» دیده شده؛ None = کل کندل."""
        buy_ = pos["direction"] == "BUY"
        sl, tp = pos["sl"], pos["tp"]
        if buy_:
            f = h if fav is None else fav
            hit_sl, hit_tp = l <= sl, f >= tp
        else:
            f = l if fav is None else fav
            hit_sl, hit_tp = h + spr >= sl, f + spr <= tp
        if not pos["managed"] and not hit_sl:
            if (f >= pos["trigger"]) if buy_ else (f + spr <= pos["trigger"]):
                pos["managed"] = True                         # نصف حجم در 2R نقد می‌شود
                pos["banked"] = PARTIAL_AT_R * PARTIAL_FRAC
                pos["frac"] = 1.0 - PARTIAL_FRAC
        if hit_sl and hit_tp:
            return True, sl, "هر دو در یک کندل: حدضرر"
        if hit_sl:
            return True, sl, "حدضرر"
        if hit_tp:
            return True, tp, "حدسود"
        return False, None, None

    def step_position(pos, h, l, t_bar):
        """یک کندل ۱۵دقیقه برای پوزیشن باز — روی کندل‌های ۱دقیقه؛ اگر ۱دقیقه نبود، روی خود ۱۵دقیقه."""
        rng = m1_range(t_bar)
        if rng is None:
            return process_pos_candle(pos, h, l)
        for j in range(*rng):
            ex = process_pos_candle(pos, m1_h[j], m1_l[j])
            if ex[0]:
                return ex
        return False, None, None

    def finalize_trade(pos, exit_time, exit_price, reason):
        nonlocal equity, peak, max_dd
        risk = pos["risk"]
        if risk <= 0:
            return
        buy_ = pos["direction"] == "BUY"
        raw_r = (exit_price - pos["eff_entry"]) / risk if buy_ else (pos["eff_entry"] - exit_price) / risk
        # سهم سیوشده در 2R + سهم باقی‌مانده، منهای سواپ هر شب نگهداری
        result_r = pos.get("banked", 0.0) + pos.get("frac", 1.0) * float(raw_r)
        try:
            nights = max(0, int((pd.Timestamp(exit_time).normalize()
                                 - pd.Timestamp(pos["fill_time"]).normalize()).days))
        except Exception:
            nights = 0
        result_r = float(result_r) - (swap_per_night * nights) / risk
        cost_r = (spread_ref + swap_per_night * nights) / risk     # هزینه‌ی کل: اسپرد + سواپ
        book.apply_result(pos["risk_amt"], result_r)
        equity += pos["risk_amt"] * float(result_r)
        peak = max(peak, equity)
        max_dd = max(max_dd, (peak - equity) / peak if peak > 0 else 0.0)
        z, ltf = pos["z"], pos["ltf"]
        trades.append({
            "نماد": symbol, "جهت": "خرید" if buy_ else "فروش",
            "زمان_ورود": pos["fill_time"], "ورود": pos["eff_entry"], "حدضرر": pos["sl"], "حدسود": pos["tp"],
            "زمان_خروج": exit_time, "قیمت_خروج": float(exit_price), "نتیجه_R": float(result_r),
            "علت_خروج": reason, "ZoneID": z.zone_id, "پراکسیمال": z.proximal, "دیستال": z.distal,
            "بیس_شروع": z.base_start, "بیس_پایان": z.base_end, "هزینه_R": float(cost_r),
            "زمان_تأیید_بیس": z.created_time, "سطح_چاک_بیس": float(getattr(z, "choch_level", np.nan)),
            "چاک_بیس_از": getattr(z, "choch_from", None),
            "زمان_رسیدن_به_بیس": ltf["reach"], "زمان_چاک_۱دقیقه": ltf["conf"], "_ltf": ltf,
        })

    # ---------- سفارش‌ها (تأیید ۱دقیقه) ----------
    pending = []      # هر بیس آماده: armed (منتظر رسیدن قیمت) → watch (منتظر چاک ۱دقیقه) → order (اوردر لیمیت)
    open_pos = []

    # ---------- لغو با زون‌های مخالف ----------
    # زون مخالف ۴ساعته: اگر قیمت از وقتی بیس تأیید شده به یک زون مخالف ۴ساعته‌ی معتبر خورده و آن زون تا رسیدن
    # قیمت به بیس نشکسته، یعنی قیمت از آن آمده → لغو. بعد از رسیدن قیمت هم خوردن به زون مخالف ۴ساعته → لغو.
    # بیس مخالف ۱۵دقیقه: آمدن قیمت از آن اشکالی ندارد، ولی بعد از چاک ۱دقیقه اگر قیمت پیش از پر شدن اوردر به یک
    # بیس مخالف معتبر ۱۵دقیقه (کنسالیدیشن اوی + لگ‌اوت قوی + چاک، نشکسته) خورد → لغو.
    no_idx = np.zeros(0, dtype=np.int64)

    def opp4_candidates(buy_, e):
        """زون‌های مخالف ۴ساعته‌ی آن طرف نقطه‌ی ورود (برای خرید: سوپلای‌های بالای ورود)"""
        if hz_from is None:
            return no_idx
        return np.flatnonzero(~hz_buy & (hz_lo > e)) if buy_ else np.flatnonzero(hz_buy & (hz_hi < e))

    def touched4(c, t_ns, h_, l_):
        """کدام زون‌های c در زمان t معتبرند و قیمت (h_, l_) به آن‌ها خورد"""
        if not len(c):
            return c
        return c[(hz_f_ns[c] <= t_ns) & (t_ns < hz_u_ns[c]) & (h_ >= hz_lo[c]) & (l_ <= hz_hi[c])]

    def came_from4(p, t_ns):
        """قیمت از زون مخالف ۴ساعته‌ای آمده که هنوز (لحظه‌ی t) نشکسته؟"""
        return any(hz_u_ns[q] > t_ns for q in p["came4"])

    def opp15_candidates(buy_, e):
        return np.flatnonzero(~Z_BUY & (Z_LO > e)) if buy_ else np.flatnonzero(Z_BUY & (Z_HI < e))

    def touched15(c, t_ns, h_, l_):
        return bool(len(c)) and bool(((Z_VFROM[c] <= t_ns) & (t_ns < Z_VUNTIL[c]) & (h_ >= Z_LO[c])
                                      & (l_ <= Z_HI[c])).any())

    # سرنوشت هر بیس آماده (برای سربرگ قیف): مرحله + دلیل
    STAGE_KEY = {"armed": "a", "watch": "w", "order": "o"}
    Z_FATE = {}

    def trend_reason(direction):
        """کدام روند جلوی این جهت را گرفته: trend4 / trend15 / trend_both / origin (اجرای خلاف روند)"""
        s_ = 1 if direction == "BUY" else -1
        if counter_htf:
            return "trend15" if htr != s_ else "origin"
        ok4, ok15 = dtr == s_, htr == s_
        return "trend_both" if not (ok4 or ok15) else ("trend4" if not ok4 else "trend15")

    def make_order(z, k, t_now, o_now, i_now):
        height = z.high() - z.low()
        if height <= 0:
            height = 1e-9
        if z.direction == "BUY":
            entry = z.proximal + ENTRY_OFF * height
            sl = z.distal - SL_OFF * height
            risk = entry - sl
            tp = entry + RR * risk
            at = entry >= o_now + spr
        else:
            entry = z.proximal - ENTRY_OFF * height
            sl = z.distal + SL_OFF * height
            risk = sl - entry
            tp = entry - RR * risk
            at = entry <= o_now
        rg = m1_range(t_now)
        # اگر قیمت همین حالا روی نقطه‌ی ورود است، مستقیم منتظر چاک می‌ماند
        stage = "watch" if (at and rg is not None) else "armed"
        p = {"z": z, "k": k, "entry": float(entry), "sl": float(sl), "tp": float(tp), "risk": float(risk),
             "active": True, "filled": False, "stage": stage,
             "j_reach": rg[0] if rg is not None else 0, "away": False,
             "c4": opp4_candidates(z.direction == "BUY", entry), "came4": set(), "c15": no_idx}
        # زون‌های مخالف ۴ساعته‌ای که قیمت از تأیید بیس تا الان به آن‌ها خورده
        c = p["c4"]
        a = int(np.searchsorted(t15_ns, pd.Timestamp(z.created_time).value, side="right"))
        if len(c) and a < i_now:
            tb, hb, lb = t15_ns[a:i_now], h15[a:i_now], l15[a:i_now]
            hit = ((hz_f_ns[c][:, None] <= tb) & (tb < hz_u_ns[c][:, None])
                   & (hb >= hz_lo[c][:, None]) & (lb <= hz_hi[c][:, None])).any(axis=1)
            p["came4"] = set(c[hit].tolist())
        if stage == "watch":
            counts["reach"] += 1
            if came_from4(p, t_now.value):
                ltf_cancel(p, "from4", "watch")
        return p

    def ltf_cancel(p, key, stage=None):
        p["active"] = False
        Z_FATE[p["k"]] = f"{STAGE_KEY[stage or p['stage']]}_{key}"

    def ltf_open(p, t_bar, j, j1, eff_entry, in_bar_fill):
        """پوزیشن از کندل ۱دقیقه‌ی j؛ in_bar_fill = لیمیت داخل همین کندل پر شد (وگرنه ورود با کلوز j).
        بقیه‌ی همین کندل ۱۵دقیقه روی ۱دقیقه جلو می‌رود. خروجی: پوزیشن باز یا None (بسته شد)."""
        direction = p["z"].direction
        risk = (eff_entry - p["sl"]) if direction == "BUY" else (p["sl"] - eff_entry)
        if risk <= 0:
            ltf_cancel(p, "badstop")
            return None
        fill_t = pd.Timestamp(m1_t[j])
        p["filled"], p["active"] = True, False
        counts["filled"] += 1
        Z_FATE[p["k"]] = "traded"
        trigger = eff_entry + PARTIAL_AT_R * risk if direction == "BUY" else eff_entry - PARTIAL_AT_R * risk
        pos = {"direction": direction, "eff_entry": float(eff_entry), "sl": float(p["sl"]), "tp": float(p["tp"]),
               "risk": float(risk), "risk_amt": float(book.risk_amount()), "fill_time": fill_t, "z": p["z"],
               "trigger": float(trigger), "managed": False, "ltf": p["ltf"]}
        if in_bar_fill:
            # کندل ورود: سقف (برای خرید) یا کف (برای فروش) فقط اگر بعد از پر شدن آمده باشد (مسیر از رنگ کندل)
            o_, h_, l_, c_ = m1_o[j], m1_h[j], m1_l[j], m1_c[j]
            if direction == "BUY":
                fav = h_ if c_ >= o_ else max(c_, eff_entry)
            else:
                fav = l_ if c_ <= o_ else min(c_, eff_entry)
            ex = process_pos_candle(pos, m1_h[j], m1_l[j], fav=fav)
            if ex[0]:
                finalize_trade(pos, t_bar, float(ex[1]), ex[2])
                return None
        for jj in range(j + 1, j1):
            ex = process_pos_candle(pos, m1_h[jj], m1_l[jj])
            if ex[0]:
                finalize_trade(pos, t_bar, float(ex[1]), ex[2])
                return None
        return pos

    def ltf_step(p, t_bar, l_bar, h_bar):
        """یک کندل ۱۵دقیقه برای یک بیس آماده، روی کندل‌های ۱دقیقه. خروجی: پوزیشن باز یا None.
        تست اول = رسیدن قیمت به نقطه‌ی ورود. اگر قیمت LTF_TEST_AWAY_R از بیس دور شد و پیش از چاک دوباره
        رسید (تست دوم) → لغو."""
        buy_ = p["z"].direction == "BUY"
        e, r = p["entry"], p["risk"]
        rng = m1_range(t_bar)
        # میان‌بر: اگر کل همین کندل ۱۵دقیقه به نقطه‌ی ورود نرسیده (یا ۱دقیقه ندارد)، فقط خود کندل ۱۵دقیقه
        # برای لمس زون‌های مخالف بررسی می‌شود
        if rng is None or (p["stage"] == "armed" and ((buy_ and l_bar + spr > e) or (not buy_ and h_bar < e))):
            hit = touched4(p["c4"], t_bar.value, h_bar, l_bar)
            if p["stage"] == "armed":
                p["came4"].update(hit.tolist())
            elif len(hit):
                ltf_cancel(p, "touch4")
            elif p["stage"] == "order" and touched15(p["c15"], t_bar.value, h_bar, l_bar):
                ltf_cancel(p, "touch15")
            return None
        j, j1 = rng
        while j < j1:
            tj = int(m1_t_ns[j])
            reach = (m1_l[j] + spr <= e) if buy_ else (m1_h[j] >= e)
            if p["stage"] == "armed":
                p["came4"].update(touched4(p["c4"], tj, m1_h[j], m1_l[j]).tolist())
                if reach:
                    counts["reach"] += 1
                    if came_from4(p, tj):                 # قیمت از زون مخالف ۴ساعته آمده
                        ltf_cancel(p, "from4", "watch")
                        return None
                    p["stage"], p["j_reach"], p["away"] = "watch", j, False
            elif p["stage"] == "watch":
                if len(touched4(p["c4"], tj, m1_h[j], m1_l[j])):
                    ltf_cancel(p, "touch4")
                    return None
                if not p["away"]:
                    if (m1_h[j] >= e + LTF_TEST_AWAY_R * r) if buy_ else (m1_l[j] + spr <= e - LTF_TEST_AWAY_R * r):
                        p["away"] = True
                elif reach:
                    ltf_cancel(p, "test2")
                    return None
                for q1 in conf_at.get(j, ()):
                    # بیس ۱دقیقه‌ی هم‌جهت، بعد از رسیدن قیمت، و روی همان بیس ۱۵دقیقه
                    if L_buy[q1] != buy_ or L_be[q1] < p["j_reach"]:
                        continue
                    if (buy_ and L_lo[q1] > e) or (not buy_ and L_hi[q1] < e):
                        continue
                    counts["choch1"] += 1
                    zc = z1[q1]
                    p["ltf"] = {"reach": pd.Timestamp(m1_t[p["j_reach"]]), "conf": pd.Timestamp(m1_t[j]),
                                "b0": pd.Timestamp(zc.base_start), "prox": float(zc.proximal),
                                "dist": float(zc.distal), "lvl": float(getattr(zc, "choch_level", np.nan)),
                                "lvl_from": pd.Timestamp(getattr(zc, "choch_from", zc.base_start))}
                    p["stage"] = "order"
                    p["c15"] = opp15_candidates(buy_, e)
                    # قیمتِ لحظه‌ی چاک از نقطه‌ی ورود گذشته؟ → ورود با قیمت بازار
                    if (buy_ and m1_c[j] + spr <= e) or (not buy_ and m1_c[j] >= e):
                        counts["market"] += 1
                        return ltf_open(p, t_bar, j, j1, m1_c[j] + spr if buy_ else m1_c[j], False)
                    break
            else:  # order
                if (buy_ and m1_l[j] + spr <= e) or (not buy_ and m1_h[j] >= e):
                    return ltf_open(p, t_bar, j, j1, e, True)
                if len(touched4(p["c4"], tj, m1_h[j], m1_l[j])):
                    ltf_cancel(p, "touch4")
                    return None
                if touched15(p["c15"], tj, m1_h[j], m1_l[j]):
                    ltf_cancel(p, "touch15")
                    return None
                if (m1_h[j] >= e + LTF_CANCEL_R * r) if buy_ else (m1_l[j] + spr <= e - LTF_CANCEL_R * r):
                    ltf_cancel(p, "far")
                    return None
            j += 1
        return None

    def cancel_orders_of_zone(z):
        for p in pending:
            if p["active"] and not p["filled"] and p["z"] is z:
                ltf_cancel(p, "replaced")

    # ---------- وضعیت بیس‌ها (آرایه؛ شماره‌ی هر بیس در zones) ----------
    nz = len(zones)
    Z_LO = np.array([z.low() for z in zones], dtype=float)
    Z_HI = np.array([z.high() for z in zones], dtype=float)
    Z_DIST = np.array([z.distal for z in zones], dtype=float)
    Z_BUY = np.array([z.direction == "BUY" for z in zones], dtype=bool)
    Z_SUP = np.array([pd.Timestamp(z.superseded_time).value if z.superseded_time is not None
                      else np.iinfo(np.int64).max for z in zones], dtype=np.int64)
    Z_TOUCHED = np.zeros(nz, dtype=bool)           # کندل ۱۵دقیقه به بیس خورد (پیش از آماده شدن)
    Z_TOUCH_I = np.full(nz, -1, dtype=np.int64)    # کندل آن لمس
    Z_USED = np.zeros(nz, dtype=bool)              # آماده شد، رد شد یا پیش از بازه لمس شد → دیگر بررسی نمی‌شود
    Z_LAST = np.zeros(nz, dtype=np.int8)           # قیف: آخرین دلیل آماده‌نشدن
    Z_PLACED = np.zeros(nz, dtype=bool)            # قیف: آماده‌ی معامله شد
    # اعتبار هر بیس به‌عنوان «بیس مخالف»: از بسته شدن کندل تأییدش تا جایگزینی یا کلوز ۱۵دقیقه پشت دیستالش
    t15_ns = df15["time"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
    Z_VFROM = np.array([pd.Timestamp(z.created_time).value for z in zones], dtype=np.int64) + span15.value
    Z_VUNTIL = Z_SUP.copy()
    cl15_ = df15["close"].to_numpy(dtype=float)
    for k in range(nz):
        kb = _first_close_beyond(cl15_, int(np.searchsorted(t15_ns, Z_VFROM[k] - span15.value)), Z_DIST[k],
                                 not Z_BUY[k])
        if kb < len(cl15_):
            Z_VUNTIL[k] = min(Z_VUNTIL[k], t15_ns[kb] + span15.value)

    t15 = df15["time"].to_numpy()
    o15 = df15["open"].to_numpy(dtype=float); h15 = df15["high"].to_numpy(dtype=float)
    l15 = df15["low"].to_numpy(dtype=float);  c15 = df15["close"].to_numpy(dtype=float)
    tr15 = df15["trend"].to_numpy()
    t4 = df4["time"].values
    tr4 = df4["trend"].to_numpy()
    zptr = 0
    live_k = np.zeros(0, dtype=np.int64)     # بیس‌های متولدشده و باطل‌نشده (به ترتیب تولد)
    dtr = htr = 0
    allowed = ()

    for i in range(len(df15)):
        di = np.searchsorted(t4, t15[i], side="right") - 1
        if di < 1 or i < 1:
            continue
        t = pd.Timestamp(t15[i])
        o, h, l, c = float(o15[i]), float(h15[i]), float(l15[i]), float(c15[i])
        c_prev = float(c15[i - 1])
        # روندها فقط از کندل‌های بسته‌شده: آخرین کندل ۴ساعته‌ی کامل و کندل ۱۵دقیقه‌ی قبلی
        dtr, htr = int(tr4[di - 1]), int(tr15[i - 1])
        if counter_htf:
            # روند ۱۵دقیقه لازم است؛ خلاف روند ۴ساعته فقط اگر قیمت از بیس ۴ساعته‌ی هم‌جهتِ روند ۴ساعته نمی‌آید
            d = {1: "BUY", -1: "SELL"}.get(htr)
            allowed = (d,) if d and not (dtr == -htr and int(origin[di - 1]) == dtr) else ()
        else:
            allowed = dirs_allowed(dtr, htr)

        # ---------- خروج پوزیشن‌های باز ----------
        still_open = []
        for pos in open_pos:
            exited, exit_price, reason = step_position(pos, h, l, t)
            if exited:
                finalize_trade(pos, t, float(exit_price), reason)
            else:
                still_open.append(pos)
        open_pos = still_open

        # ---------- بیس‌های تازه متولدشده ----------
        z0 = zptr
        while zptr < nz and zones[zptr].created_time < t:
            zptr += 1
        if zptr > z0:
            live_k = np.concatenate([live_k, np.arange(z0, zptr, dtype=np.int64)])

        # ---------- باطل شدن و لمس بیس‌ها ----------
        # باطل: بیس جدیدِ هم‌پوشان جایش را گرفت، یا (پیش از آماده شدن) کندل قبلی پشت دیستال بسته شد
        if len(live_k):
            lk = live_k
            dead = (Z_SUP[lk] <= t.value) | (np.where(Z_BUY[lk], c_prev < Z_DIST[lk], c_prev > Z_DIST[lk])
                                              & ~Z_USED[lk])
            for k in lk[dead]:
                cancel_orders_of_zone(zones[k])
            first = lk[(h >= Z_LO[lk]) & (l <= Z_HI[lk]) & ~Z_TOUCHED[lk] & ~Z_USED[lk] & ~dead]
            Z_TOUCHED[first], Z_TOUCH_I[first] = True, i
            if dead.any():
                live_k = lk[~dead]

        if t < bt_start:
            # گرم‌کردن: بیسی که پیش از شروع بازه لمس شده، مصرف‌شده است
            Z_USED[live_k[Z_TOUCHED[live_k]]] = True
            continue

        # ---------- بیس‌های لمس‌شده (تصمیم از کندل بعد از لمس، مثل لایو) ----------
        touched = []
        for k in live_k[Z_TOUCHED[live_k] & ~Z_USED[live_k]]:
            if Z_TOUCH_I[k] == i:
                continue
            z = zones[k]
            if z.direction not in allowed:
                Z_LAST[k], Z_USED[k] = _BLOCK_CODE[trend_reason(z.direction)], True
                continue
            why = htf_block(z, t, o)
            if why:
                Z_LAST[k], Z_USED[k] = _BLOCK_CODE[why], True
                continue
            touched.append(k)

        # ---------- بیس‌های لمس‌نشده (اگر الان مجاز نیستند، بعداً دوباره بررسی می‌شوند) ----------
        untouched = []
        lu = live_k[~Z_TOUCHED[live_k] & ~Z_USED[live_k]]
        for d_, m_ in (("BUY", Z_BUY[lu]), ("SELL", ~Z_BUY[lu])):
            if d_ not in allowed and m_.any():
                Z_LAST[lu[m_]] = _BLOCK_CODE[trend_reason(d_)]
        if allowed:
            for k in lu:
                z = zones[k]
                if z.direction not in allowed or z.high() - z.low() <= 0:
                    continue
                why = htf_block(z, t, o)
                if why:
                    Z_LAST[k] = _BLOCK_CODE[why]
                    continue
                untouched.append(k)
            untouched.sort(key=lambda k_: abs(c - zones[k_].proximal))
        touched.sort(key=lambda k_: abs(c - zones[k_].proximal))

        yield t      # هم‌قدمی با بقیه‌ی نمادها (حساب مشترک)

        for k in touched + untouched:
            pending.append(make_order(zones[k], k, t, o, i))
            Z_PLACED[k] = Z_USED[k] = True

        # ---------- بی‌اعتبار شدن بیس: کندل ۱۵دقیقه‌ی قبلی پشت دیستال بسته شد ----------
        for p in pending:
            if p["active"] and not p["filled"]:
                zz = p["z"]
                if (zz.direction == "BUY" and c_prev < zz.distal) or (zz.direction == "SELL" and c_prev > zz.distal):
                    ltf_cancel(p, "breach")

        # ---------- رسیدن قیمت، چاک ۱دقیقه و ورود ----------
        for p in pending:
            if not p["active"] or p["filled"]:
                continue
            d_ = p["z"].direction                      # روند پیش از ورود برگشت → لغو
            if (d_ != {1: "BUY", -1: "SELL"}.get(htr)) if keep_on_htf_flip else (d_ not in allowed):
                ltf_cancel(p, trend_reason(d_))
                continue
            pos = ltf_step(p, t, l, h)
            if pos is not None:
                open_pos.append(pos)
        pending = [p for p in pending if p["active"] and not p["filled"]]

    if live_from is not None:
        # ربات لایو: اوردرهایی که الان باید روی حساب باشند، بیس‌های منتظر و پوزیشن‌هایی که استراتژی دارد
        def _o(p):
            return {"id": p["z"].zone_id, "direction": p["z"].direction, "stage": p["stage"],
                    "entry": p["entry"], "sl": p["sl"], "tp": p["tp"], "risk": p["risk"]}
        return {"time": pd.Timestamp(t15[-1]) if len(t15) else None, "allowed": allowed,
                "trend4": dtr, "trend15": htr,
                "orders": [_o(p) for p in pending if p["stage"] == "order"],      # چاک ۱دقیقه آمده: اوردر لیمیت
                "watching": [_o(p) for p in pending if p["stage"] != "order"],    # منتظر رسیدن قیمت یا چاک
                "positions": [{"id": pos["z"].zone_id, "direction": pos["direction"], "entry": pos["eff_entry"],
                               "sl": pos["sl"], "tp": pos["tp"], "risk": pos["risk"], "fill_time": pos["fill_time"],
                               "partial_price": pos["trigger"], "partial_done": pos["managed"]}
                              for pos in open_pos],
                "closed": [{"id": r["ZoneID"], "exit_time": r["زمان_خروج"], "reason": r["علت_خروج"],
                            "result_r": r["نتیجه_R"]} for r in trades]}

    # ---------- پایان دیتا: پوزیشن‌های باز با آخرین کلوز بسته می‌شوند ----------
    if len(df15):
        endt, c_last = df15["time"].iloc[-1], float(df15["close"].iloc[-1])
        for pos in open_pos:
            finalize_trade(pos, endt, c_last, "پایان دیتا")

    # ---------- قیف: سرنوشت هر بیس (فقط بیس‌های متولد در بازه‌ی معامله) ----------
    for p in pending:
        Z_FATE[p["k"]] = f"{STAGE_KEY[p['stage']]}_end"           # تا آخر دیتا منتظر ماند
    inz = np.array([in_p(z.created_time) for z in zones], dtype=bool) if nz else np.zeros(0, dtype=bool)
    counts.update({"f_dedup": int(inz.sum()), "f_ready": int((inz & Z_PLACED).sum())})
    for k in np.flatnonzero(inz):
        f = Z_FATE.get(k, "a_end") if Z_PLACED[k] else _LAST_FATE[int(Z_LAST[k])]
        counts[f] = counts.get(f, 0) + 1
    tdf = pd.DataFrame(trades)
    return _symbol_metrics(symbol, tdf, equity, max_dd, spread_ref), counts, tdf


def live_state(symbol, df15, df4, m1, spread, trade_from, **kw):
    """مغز ربات لایو: همان موتور بک‌تست روی دیتای تازه‌ی بروکر تا همین لحظه → وضعیتی که حساب باید داشته باشد.
    df15 و df4: کندل‌ها به‌همراه کندلِ در حال شکل‌گیری (آخرین ردیف) | m1: فقط کندل‌های بسته‌شده.
    trade_from: معامله از این زمان (مثلاً زمان روشن شدن ربات)؛ دیتای ۱دقیقه باید از پیش از آن باشد و
    ۱۵دقیقه/۴ساعته دست‌کم WARMUP_DAYS قبل‌ترش. بیسی که پیش از trade_from لمس شده، مصرف‌شده است.
    خروجی: orders (اوردرهای لیمیتی که الان باید باشند)، watching، positions (با partial_done برای سیو 2R)،
    closed (معاملات بسته‌شده از trade_from) — شناسه‌ی هر کدام = شناسه‌ی بیس (برای کامنت سفارش)."""
    gen = backtest_symbol(symbol, df15, df4, m1, spread, AccountBook(), live_from=trade_from, **kw)
    while True:
        try:
            next(gen)
        except StopIteration as stop:
            return stop.value


def run_portfolio(frames, spreads, **kw):
    """همه‌ی نمادها هم‌زمان روی یک حساب، کندل‌به‌کندل. frames: {نماد: (۱۵دقیقه، ۴ساعته، ۱دقیقه)}
    خروجی: ({نماد: (کارنامه، شمارنده‌ها، معاملات)}، حساب)"""
    book = AccountBook()
    gens, nxt, results = {}, {}, {}
    for sym in frames:
        gen = backtest_symbol(sym, *frames[sym], spreads.get(sym, 0.0), book, **kw)
        try:
            nxt[sym] = next(gen)
            gens[sym] = gen
        except StopIteration as stop:
            results[sym] = stop.value
    while gens:
        t_min = min(nxt.values())
        for s in [s for s in frames if s in gens and nxt[s] == t_min]:
            try:
                nxt[s] = next(gens[s])
            except StopIteration as stop:
                results[s] = stop.value
                del gens[s], nxt[s]
    return results, book


# ============================================================================
# گزارش
# ============================================================================
def _all_trades(results):
    tr = [r[2] for r in results.values() if r[2] is not None and not r[2].empty]
    return pd.concat(tr, ignore_index=True) if tr else pd.DataFrame(columns=["نماد", "نتیجه_R", "زمان_ورود"])


def _pf(r):
    win = float(r[r > 0].sum())
    los = float(r[r < 0].abs().sum())
    return round(win / los, 3) if los > 0 else 999.0


def symbol_table(results, book):
    """ردیف «کل» (کل حساب) + یک ردیف برای هر نماد."""
    tr = _all_trades(results)
    R = tr["نتیجه_R"].astype(float)
    C = tr["هزینه_R"].astype(float) if "هزینه_R" in tr.columns else pd.Series(dtype=float)
    rows = [{"نماد": "کل", "تعداد": int(len(R)),
             "درصد_برد": round(float((R > 0).mean() * 100.0), 2) if len(R) else 0.0,
             "فاکتور_سود": _pf(R), "میانگین_R": round(float(R.mean()), 3) if len(R) else 0.0,
             "سهم_از_بازده_حساب٪": round((book.equity / book.start_equity - 1.0) * 100.0, 2),
             "افت_سهم_این_نماد٪": round(book.max_dd * 100.0, 2),
             "هزینه_هر_معامله_R": round(float(C.median()), 3) if len(C) else 0.0}]
    for sym, r in results.items():
        m = r[0]
        rows.append({"نماد": sym, "تعداد": int(m["تعداد"]), "درصد_برد": m["درصد_برد"],
                     "فاکتور_سود": m["فاکتور_سود"], "میانگین_R": m["میانگین_R"],
                     "سهم_از_بازده_حساب٪": m["بازده_خالص٪"], "افت_سهم_این_نماد٪": m["حداکثر_افت٪"],
                     "فاصله_استاپ_پیپ": m["فاصله_استاپ_پیپ"], "هزینه_هر_معامله_R": m["هزینه_هر_معامله_R"],
                     "اسپرد_پیپ": m["اسپرد_پیپ"]})
    return pd.DataFrame(rows, columns=["نماد", "تعداد", "درصد_برد", "فاکتور_سود", "میانگین_R", "سهم_از_بازده_حساب٪",
                                       "افت_سهم_این_نماد٪", "فاصله_استاپ_پیپ", "هزینه_هر_معامله_R", "اسپرد_پیپ"])


def stop_causes(trades, frames, max_days=None):
    """دلیل هر استاپ کامل (معامله‌ی ضررده که با حدضرر بسته شد) — فقط برای گزارش:
      «روند ۴ساعته»: بعد از ورود، روند ۴ساعته خلاف جهت معامله شد پیش از آنکه قیمت به تارگت برسد.
      «بیس ۱۵دقیقه»: روند ۴ساعته سر جایش ماند و قیمت بعد از زدن استاپ به تارگت رسید.
      «نامشخص»: تا max_days روز نه روند برگشت نه تارگت خورد.
    خروجی: (برچسب هر معامله — "" برای غیر استاپ، عمق خلاف جهت برحسب R برای «بیس» یا NaN)."""
    max_days = STOP_CAUSE_DAYS if max_days is None else max_days
    labels = pd.Series("", index=trades.index, dtype=object)
    depth = pd.Series(np.nan, index=trades.index, dtype=float)
    if trades.empty:
        return labels, depth
    win = np.timedelta64(pd.Timedelta(days=max_days))
    for sym, g in trades.groupby("نماد"):
        if sym not in frames:
            continue
        zdf, tdf_ = frames[sym][0], frames[sym][1]
        sgn = np.sign(structure_trend(tdf_, n=STRUCT_SWING_N).to_numpy())
        tsp = tdf_["time"].diff().dropna().median()
        known = (pd.to_datetime(tdf_["time"]) + tsp).to_numpy(dtype="datetime64[ns]")   # روند از بسته شدن کندل
        zt = pd.to_datetime(zdf["time"]).to_numpy(dtype="datetime64[ns]")
        zh = zdf["high"].to_numpy(dtype=float)
        zl = zdf["low"].to_numpy(dtype=float)
        lost = g[(pd.to_numeric(g["نتیجه_R"], errors="coerce") < 0)
                 & g["علت_خروج"].astype(str).str.contains("حدضرر")]
        for ix, r in lost.iterrows():
            d = 1 if r["جهت"] == "خرید" else -1
            te = np.datetime64(pd.Timestamp(r["زمان_ورود"]), "ns")
            tx = np.datetime64(pd.Timestamp(r["زمان_خروج"]), "ns")
            tend = te + win
            a, b = np.searchsorted(known, te), np.searchsorted(known, tend, side="right")
            m = sgn[a:b] == -d
            flip_t = known[a + int(np.argmax(m))] if m.any() else None
            a2, b2 = np.searchsorted(zt, tx), np.searchsorted(zt, tend, side="right")
            tp = float(r["حدسود"])
            m2 = (zh[a2:b2] >= tp) if d == 1 else (zl[a2:b2] <= tp)
            tp_t = zt[a2 + int(np.argmax(m2))] if m2.any() else None
            if flip_t is not None and (tp_t is None or flip_t <= tp_t):
                labels[ix] = "روند ۴ساعته"
            elif tp_t is not None:
                labels[ix] = "بیس ۱۵دقیقه"
                risk = abs(float(r["ورود"]) - float(r["حدضرر"]))
                a3, k3 = np.searchsorted(zt, te), a2 + int(np.argmax(m2))
                if risk > 0 and k3 >= a3:
                    adv = (float(r["ورود"]) - zl[a3:k3 + 1].min()) if d == 1 else (zh[a3:k3 + 1].max() - float(r["ورود"]))
                    depth[ix] = adv / risk
            else:
                labels[ix] = "نامشخص"
    return labels, depth


def stop_cause_table(trades, frames):
    """جدول دلیل استاپ‌ها: ردیف «کل» + هر نماد."""
    cols = ["نماد", "تعداد_معامله", "استاپ_کامل", "روند_۴ساعته_برگشت", "٪_روند",
            "بیس_۱۵دقیقه_(جهت_درست_بود)", "٪_بیس", "نامشخص", "٪_نامشخص", "بیس_عمق_خلاف_جهت_R_(میانه)"]
    if trades.empty:
        return pd.DataFrame(columns=cols)
    labels, depth = stop_causes(trades, frames)

    def row(name, idx):
        lb = labels[idx]
        n_sl = int((lb != "").sum())
        cnt = {k: int((lb == v).sum()) for k, v in (("trend", "روند ۴ساعته"), ("base", "بیس ۱۵دقیقه"),
                                                     ("unk", "نامشخص"))}
        pct = (lambda k: round(cnt[k] / n_sl * 100.0, 1) if n_sl else 0.0)
        dp = depth[idx].dropna()
        return {"نماد": name, "تعداد_معامله": int(len(idx)), "استاپ_کامل": n_sl,
                "روند_۴ساعته_برگشت": cnt["trend"], "٪_روند": pct("trend"),
                "بیس_۱۵دقیقه_(جهت_درست_بود)": cnt["base"], "٪_بیس": pct("base"),
                "نامشخص": cnt["unk"], "٪_نامشخص": pct("unk"),
                "بیس_عمق_خلاف_جهت_R_(میانه)": round(float(dp.median()), 2) if len(dp) else None}
    rows = [row("کل", trades.index)]
    for sym, g in sorted(trades.groupby("نماد"), key=lambda x: x[0]):
        rows.append(row(sym, g.index))
    return pd.DataFrame(rows, columns=cols)


def _fmt_t(t):
    try:
        return "" if t is None or pd.isna(t) else pd.Timestamp(t).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return ""


def trades_review_table(name, results, frames):
    """همه‌ی معاملات یک اجرا با زمان‌ها (ساعت سرور بروکر، همان ساعت چارت متاتریدر).
    خروجی: (جدول برای اکسل، جدول خام برای نمودارها)"""
    tr = _all_trades(results)
    if tr.empty:
        return tr, tr
    tr = tr.sort_values("زمان_ورود").reset_index(drop=True)
    tr["دلیل_استاپ"] = stop_causes(tr, frames)[0]
    tr["شماره"] = np.arange(1, len(tr) + 1)
    pips = tr["نماد"].map(pip_size)
    out = pd.DataFrame({
        "اجرا": name, "شماره": tr["شماره"], "نماد": tr["نماد"], "جهت": tr["جهت"],
        "نتیجه_R": tr["نتیجه_R"].astype(float).round(2), "علت_خروج": tr["علت_خروج"],
        "دلیل_استاپ": tr["دلیل_استاپ"],
        "شروع_بیس_۱۵دقیقه": tr["بیس_شروع"].map(_fmt_t), "پایان_بیس_۱۵دقیقه": tr["بیس_پایان"].map(_fmt_t),
        "تأیید_بیس_(کندل_چاک)": tr["زمان_تأیید_بیس"].map(_fmt_t),
        "پراکسیمال": tr["پراکسیمال"], "دیستال": tr["دیستال"], "سطح_چاک_بیس": tr["سطح_چاک_بیس"],
        "رسیدن_قیمت_به_بیس": tr["زمان_رسیدن_به_بیس"].map(_fmt_t), "چاک_۱دقیقه": tr["زمان_چاک_۱دقیقه"].map(_fmt_t),
        "زمان_ورود": tr["زمان_ورود"].map(_fmt_t), "ورود": tr["ورود"], "حدضرر": tr["حدضرر"],
        "حدسود": tr["حدسود"], "زمان_خروج": tr["زمان_خروج"].map(_fmt_t),
        "استاپ_پیپ": ((tr["ورود"] - tr["حدضرر"]).abs() / pips).round(1),
    })
    return out, tr


def draw_trade_charts(chart_dir, run_idx, name, raw, frames, max_n=None):
    """یک عکس برای هر معامله: بالا ۱۵دقیقه (بیس، سطح چاک بیس، ورود/استاپ/تارگت)، پایین ۱دقیقه
    (رسیدن قیمت به بیس، بیس ۱دقیقه، سطح و لحظه‌ی چاک ۱دقیقه). نوشته‌ها انگلیسی‌اند چون
    matplotlib حروف فارسی را درست نمی‌چسباند."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import Rectangle
    except ImportError:
        print("   ⚠️ برای نمودار معاملات پکیج matplotlib لازم است. یک بار در CMD بزن:  pip install matplotlib")
        return 0
    if raw is None or raw.empty:
        return 0
    max_n = TRADE_CHARTS_MAX if max_n is None else max_n
    sub = os.path.join(chart_dir, f"{run_idx}_{name}")
    os.makedirs(sub, exist_ok=True)
    reason_en = {"حدسود": "TP", "حدضرر": "SL", "پایان دیتا": "end of data",
                 "هر دو در یک کندل: حدضرر": "SL (TP+SL same bar)"}
    cause_en = {"روند ۴ساعته": "H4 trend turned", "بیس ۱۵دقیقه": "15m base failed (trend held)",
                "نامشخص": "unclear", "": "-"}

    def candles(ax, df):
        x = np.arange(len(df))
        o, h, l, c = (df[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close"))
        up = c >= o
        ax.vlines(x, l, h, color="#555555", linewidth=0.6, zorder=2)
        ax.bar(x[up], (c - o)[up], bottom=o[up], width=0.65, color="#26a69a", zorder=3)
        ax.bar(x[~up], (o - c)[~up], bottom=c[~up], width=0.65, color="#ef5350", zorder=3)
        step = max(1, len(df) // 8)
        ax.set_xticks(x[::step])
        ax.set_xticklabels([pd.Timestamp(t).strftime("%m-%d %H:%M") for t in df["time"].iloc[::step]],
                           fontsize=7)
        ax.set_xlim(-1, len(df))
        ax.grid(alpha=0.2)

    def xi(df, t):
        if t is None or (not isinstance(t, pd.Timestamp) and pd.isna(t)):
            return None
        return int(np.searchsorted(df["time"].to_numpy(dtype="datetime64[ns]"),
                                   np.datetime64(pd.Timestamp(t), "ns")))

    n_done = 0
    for _, r in raw.head(max_n).iterrows():
        sym = r["نماد"]
        if sym not in frames:
            continue
        z15, m1 = frames[sym][0], frames[sym][2]
        t_in, t_out = pd.Timestamp(r["زمان_ورود"]), pd.Timestamp(r["زمان_خروج"])
        t_b0 = pd.Timestamp(r["بیس_شروع"])
        t_from = pd.Timestamp(r["چاک_بیس_از"]) if r.get("چاک_بیس_از") is not None and not pd.isna(r.get("چاک_بیس_از")) else t_b0
        tt = z15["time"].to_numpy(dtype="datetime64[ns]")
        i0 = int(np.searchsorted(tt, np.datetime64(min(t_b0, t_from), "ns"))) - 25
        i1 = int(np.searchsorted(tt, np.datetime64(t_out, "ns"))) + 25
        ie = int(np.searchsorted(tt, np.datetime64(t_in, "ns")))
        if i1 - i0 > 500:
            i0, i1 = max(i0, ie - 300), min(i1, ie + 200)
        w = z15.iloc[max(0, i0):min(len(z15), i1)].reset_index(drop=True)
        if w.empty:
            continue
        ltf = r.get("_ltf") if isinstance(r.get("_ltf"), dict) else None
        has_m1 = ltf is not None and m1 is not None and len(m1)
        fig, axes = plt.subplots(2 if has_m1 else 1, 1, figsize=(15, 9 if has_m1 else 5.5),
                                 gridspec_kw={"height_ratios": [3, 2]} if has_m1 else None)
        ax = axes[0] if has_m1 else axes
        candles(ax, w)
        buy = r["جهت"] == "خرید"
        zc = "#2e7d32" if buy else "#c62828"
        xb0, xin, xout = xi(w, t_b0), xi(w, t_in), xi(w, t_out)
        lo_, hi_ = min(r["پراکسیمال"], r["دیستال"]), max(r["پراکسیمال"], r["دیستال"])
        ax.add_patch(Rectangle((xb0 - 0.5, lo_), max(1, xout - xb0 + 1), hi_ - lo_, color=zc, alpha=0.15, zorder=1))
        lvl = r.get("سطح_چاک_بیس")
        if lvl is not None and np.isfinite(lvl):
            xf, xc = xi(w, t_from), xi(w, r.get("زمان_تأیید_بیس"))
            ax.hlines(lvl, xf, xc, colors="orange", linestyles=":", linewidth=1.6, label="15m CHoCH level", zorder=4)
        xl = max(xout, xin + 6)          # حتی اگر ورود و خروج در یک کندل باشد خط‌ها دیده شوند
        ax.hlines(r["ورود"], xin, xl, colors="#1565c0", linewidth=1.3, label="entry", zorder=4)
        ax.hlines(r["حدضرر"], xin, xl, colors="#c62828", linewidth=1.3, label="SL", zorder=4)
        ax.hlines(r["حدسود"], xin, xl, colors="#2e7d32", linewidth=1.3, label="TP", zorder=4)
        ax.plot([xin], [r["ورود"]], marker="^" if buy else "v", color="#1565c0", markersize=9, zorder=5)
        if ltf:
            for key, col, lab in (("reach", "grey", "price reached base"), ("conf", "purple", "1m CHoCH")):
                xv = xi(w, ltf.get(key))
                if xv is not None and 0 <= xv < len(w):
                    ax.axvline(xv, color=col, linestyle="--", linewidth=1, label=lab)
        ax.axvline(xin, color="#1565c0", linewidth=0.8)
        ax.axvline(min(xout, len(w) - 1), color="black", linewidth=0.8)
        res = float(r["نتیجه_R"])
        ax.set_title(f"#{int(r['شماره'])} {sym} {'BUY' if buy else 'SELL'} | {res:+.2f}R | "
                     f"exit: {reason_en.get(str(r['علت_خروج']), str(r['علت_خروج']))} | "
                     f"stop cause: {cause_en.get(r.get('دلیل_استاپ', ''), '-')} | entry {t_in:%Y-%m-%d %H:%M}",
                     fontsize=10)
        ax.legend(loc="upper left", fontsize=7)
        if has_m1:
            ax2 = axes[1]
            mt = m1["time"].to_numpy(dtype="datetime64[ns]")
            ta = min(ltf["reach"], ltf["b0"], ltf.get("lvl_from") or ltf["b0"]) - pd.Timedelta(minutes=20)
            tb = ltf["conf"] + pd.Timedelta(minutes=60)
            j0 = int(np.searchsorted(mt, np.datetime64(ta, "ns")))
            j1 = int(np.searchsorted(mt, np.datetime64(tb, "ns")))
            if j1 - j0 > 400:
                j0 = max(j0, int(np.searchsorted(mt, np.datetime64(ltf["conf"], "ns"))) - 300)
                j1 = min(j1, j0 + 400)
            w1 = m1.iloc[j0:j1].reset_index(drop=True)
            if len(w1):
                candles(ax2, w1)
                ax2.axhspan(lo_, hi_, color=zc, alpha=0.08)
                xb, xc1 = xi(w1, ltf["b0"]), xi(w1, ltf["conf"])
                l1, h1 = min(ltf["prox"], ltf["dist"]), max(ltf["prox"], ltf["dist"])
                ax2.add_patch(Rectangle((xb - 0.5, l1), max(1, xc1 - xb + 1), h1 - l1, color=zc, alpha=0.3, zorder=1,
                                        label="1m base"))
                if np.isfinite(ltf.get("lvl", np.nan)):
                    ax2.hlines(ltf["lvl"], xi(w1, ltf.get("lvl_from")), xc1, colors="orange", linestyles=":",
                               linewidth=1.6, label="1m CHoCH level")
                for key, col, lab in (("reach", "grey", "price reached 15m base"), ("conf", "purple", "1m CHoCH")):
                    xv = xi(w1, ltf.get(key))
                    if xv is not None and 0 <= xv < len(w1):
                        ax2.axvline(xv, color=col, linestyle="--", linewidth=1, label=lab)
                ax2.axhline(r["ورود"], color="#1565c0", linewidth=1, label="entry")
                ax2.set_title("1 minute: 15m base (light band), 1m base, 1m CHoCH", fontsize=9)
                ax2.legend(loc="upper left", fontsize=7)
        fig.tight_layout()
        fn = f"{int(r['شماره']):03d}_{sym}_{t_in:%Y%m%d-%H%M}_{'WIN' if res > 0 else 'LOSS'}.png"
        fig.savefig(os.path.join(sub, fn), dpi=90)
        plt.close(fig)
        n_done += 1
    return n_done


def hour_to_session(h):
    for a, b, name in SESSION_RANGES:
        if a <= h < b:
            return name
    return "نامشخص"


def session_results_table(runs):
    """برد، باخت، سود و ضرر هر سشن (از روی ساعت ورود، تبدیل‌شده به UTC با SESSION_HOUR_SHIFT)."""
    rows = []
    risk_pct = RISK_PER_TRADE * 100.0
    for name, results, _book in runs:
        tr = _all_trades(results)
        if tr.empty:
            continue
        ses = (pd.to_datetime(tr["زمان_ورود"]) + pd.Timedelta(hours=SESSION_HOUR_SHIFT)).dt.hour.map(hour_to_session)
        R = tr["نتیجه_R"].astype(float)
        for a, b, sname in list(SESSION_RANGES) + [(None, None, "کل")]:
            r = R[ses == sname] if a is not None else R
            win, loss = r[r > 0], r[r <= 0]
            rows.append({
                "اجرا": name, "سشن": sname if a is None else f"{sname} ({a:02d}-{b:02d} UTC)",
                "تعداد": int(len(r)), "برد": int(len(win)), "باخت": int(len(loss)),
                "درصد_برد": round(len(win) / len(r) * 100.0, 1) if len(r) else 0.0,
                "سود_R": round(float(win.sum()), 2), "ضرر_R": round(float(loss.sum()), 2),
                "خالص_R": round(float(r.sum()), 2),
                "میانگین_R": round(float(r.mean()), 3) if len(r) else 0.0,
                "فاکتور_سود": _pf(r) if len(r) else 0.0,
                "خالص_تقریبی٪_حساب": round(float(r.sum()) * risk_pct, 2),
            })
        rows.append({})
    return pd.DataFrame(rows)


# شمارنده‌های جدول «کلی» و مراحل سربرگ «قیف»
SUMMARY_COUNTS = [("reach", "قیمت_به_بیس_رسید"), ("choch1", "چاک_۱دقیقه_آمد"), ("filled", "معامله"),
                  ("market", "ورود_با_قیمت_بازار")]
FUNNEL_STAGES = [("f_all", "۱. همه‌ی بیس‌های ۱۵دقیقه (با و بدون کنسالیدیشن اوی)"),
                 ("f_oe", "۲. با کنسالیدیشن اوی"),
                 ("f_strong", "۳. با لگ‌اوت قوی"),
                 ("f_choch", "۴. با تأیید چاک"),
                 ("f_dedup", "۵. بعد از حذف بیس‌های هم‌پوشان = بیس‌های معتبر (سرنوشتشان پایین)")]


def _trend_rows(g, verb):
    return [(f"{g}_trend4", f"روند ۴ساعته {verb}"), (f"{g}_trend15", f"روند ۱۵دقیقه {verb}"),
            (f"{g}_trend_both", f"هر دو روند {verb}"),
            (f"{g}_origin", "قیمت از بیس ۴ساعته‌ی هم‌جهت روند ۴ساعته آمد (فقط اجرای خلاف روند)")]


# سرنوشت هر بیس معتبر — هر بیس دقیقاً در یک ردیف شمرده می‌شود
FATE_GROUPS = [
    ("آماده نشد (هیچ‌وقت اجازه‌ی معامله نگرفت)",
     [("n_trend4", "روند ۴ساعته خلاف بیس بود"), ("n_trend15", "روند ۱۵دقیقه خلاف بیس بود"),
      ("n_trend_both", "هر دو روند خلاف بیس بودند (یا بی‌روند)"),
      ("n_origin", "قیمت از بیس ۴ساعته‌ی هم‌جهت روند ۴ساعته می‌آمد (فقط اجرای خلاف روند)"),
      ("n_inside", "داخل زون مخالف ۴ساعته بود"), ("n_near", "نزدیک‌تر از ۳ برابر ریسک به زون مخالف ۴ساعته"),
      ("n_cp", "سه سی‌پی پشت‌سرهم روی ۴ساعته"), ("n_dead", "پیش از بررسی شکست یا بیس جدید جایش را گرفت")]),
    ("آماده شد ولی قیمت به بیس نرسید",
     _trend_rows("a", "برگشت") + [("a_breach", "بیس با کلوز ۱۵دقیقه شکست"),
                                  ("a_replaced", "بیس جدید هم‌پوشان جایش را گرفت"),
                                  ("a_end", "تا آخر دیتا منتظر ماند")]),
    ("قیمت به بیس رسید ولی چاک ۱دقیقه نیامد",
     [("w_from4", "قیمت از زون مخالف ۴ساعته آمده بود"), ("w_touch4", "بعد از رسیدن، قیمت به زون مخالف ۴ساعته خورد"),
      ("w_test2", "قیمت دور شد و بدون چاک برگشت (تست دوم)")] + _trend_rows("w", "برگشت")
     + [("w_breach", "بیس با کلوز ۱۵دقیقه شکست"), ("w_replaced", "بیس جدید هم‌پوشان جایش را گرفت"),
        ("w_end", "تا آخر دیتا منتظر چاک ماند")]),
    ("چاک ۱دقیقه آمد ولی اوردر پر نشد",
     [("o_touch15", "قیمت به بیس مخالف معتبر ۱۵دقیقه خورد"), ("o_touch4", "قیمت به زون مخالف ۴ساعته خورد"),
      ("o_far", "قیمت ۷ آر دور شد و پر نشد")] + _trend_rows("o", "برگشت")
     + [("o_breach", "بیس با کلوز ۱۵دقیقه شکست"), ("o_replaced", "بیس جدید هم‌پوشان جایش را گرفت"),
        ("o_badstop", "لحظه‌ی چاک قیمت پشت استاپ بود"), ("o_end", "تا آخر دیتا اوردر پر نشد")]),
    ("معامله شد", [("traded", "معامله شد")]),
]


def _run_counts(results):
    tot = {}
    for r in results.values():
        for k, v in r[1].items():
            tot[k] = tot.get(k, 0) + int(v)
    return tot


def funnel_table(runs):
    """سربرگ قیف: مراحل ساخته شدن بیس، بعد سرنوشت هر بیس معتبر (ردیف‌هایی که در همه‌ی اجراها صفرند حذف)."""
    counts = [(name, _run_counts(results)) for name, results, _b in runs]
    main_n = counts[0][1].get("f_dedup", 0) if counts else 0

    def row(label, key_list, top=False):
        r = {"مرحله": label}
        for name, c in counts:
            r[name] = sum(c.get(k, 0) for k in key_list)
        if counts:
            v = r[counts[0][0]]
            r["٪ اجرای اصلی (از بیس‌های معتبر)"] = round(v / main_n * 100.0, 1) if (main_n and not top) else None
        return r

    rows = [row(lab, [k], top=True) for k, lab in FUNNEL_STAGES]
    rows.append({"مرحله": ""})
    rows.append({"مرحله": "سرنوشت هر بیس معتبر (هر بیس فقط در یک ردیف):"})
    for title, items in FATE_GROUPS:
        rows.append(row(f"■ {title}", [k for k, _ in items]))
        if len(items) > 1:
            for k, lab in items:
                r = row(f"      {lab}", [k])
                if any(c.get(k, 0) for _n, c in counts):
                    rows.append(r)
    return pd.DataFrame(rows)


def yearly_table(runs):
    """نتیجه‌ی هر سال (از روی زمان ورود) برای هر اجرا."""
    rows = []
    for name, results, _book in runs:
        tr = _all_trades(results)
        if tr.empty:
            continue
        yrs = pd.to_datetime(tr["زمان_ورود"]).dt.year
        R = tr["نتیجه_R"].astype(float)
        for y in sorted(yrs.unique()):
            r = R[yrs == y]
            rows.append({"اجرا": name, "سال": int(y), "تعداد": int(len(r)),
                         "درصد_برد": round(float((r > 0).mean() * 100.0), 1), "فاکتور_سود": _pf(r),
                         "جمع_R": round(float(r.sum()), 2), "میانگین_R": round(float(r.mean()), 3)})
        rows.append({})
    return pd.DataFrame(rows)


def write_excel(sw, runs, frames):
    """سربرگ‌ها: «کلی»، «دلیل_استاپ‌ها»، «قیف»، «سال‌ها»، «سشن‌ها» و «معاملات».
    runs: [(اسم اجرا, results, book)] — خروجی: [(اسم اجرا، جدول معاملات، جدول خام)] برای نمودارها"""
    parts, causes = [], []
    for name, results, book in runs:
        tbl = symbol_table(results, book)
        tbl.insert(0, "اجرا", name)
        parts += [tbl, pd.DataFrame([{}])]
        ct = stop_cause_table(_all_trades(results), frames)
        ct.insert(0, "اجرا", name)
        causes += [ct, pd.DataFrame([{}])]
        if not ct.empty:
            t0 = ct.iloc[0]
            print(f"   دلیل {int(t0['استاپ_کامل'])} استاپ «{name}»: روند ۴ساعته {t0['٪_روند']}٪ | "
                  f"بیس ۱۵دقیقه {t0['٪_بیس']}٪ | نامشخص {t0['٪_نامشخص']}٪")
    main_tbl = pd.concat(parts, ignore_index=True)
    main_tbl.to_excel(sw, sheet_name="کلی", index=False)
    counts = {name: _run_counts(results) for name, results, _b in runs}
    pd.DataFrame([{"اجرا": "قیف هر اجرا (جزئیات کامل در سربرگ قیف)"}]).to_excel(
        sw, sheet_name="کلی", index=False, header=False, startrow=len(main_tbl) + 2)
    pd.DataFrame([{"اجرا": name, **{lab: counts[name].get(k, 0) for k, lab in SUMMARY_COUNTS}}
                  for name, _r, _b in runs]).to_excel(sw, sheet_name="کلی", index=False, startrow=len(main_tbl) + 3)

    cdf = pd.concat(causes, ignore_index=True)
    cdf.to_excel(sw, sheet_name="دلیل_استاپ‌ها", index=False)
    pd.DataFrame({"توضیح": [
        "استاپ_کامل = معامله‌ی ضررده که با حدضرر بسته شد (معامله‌ای که در 2R نصفش سیو شده حساب نمی‌شود).",
        "روند_۴ساعته_برگشت = بعد از ورود، روند ۴ساعته خلاف جهت معامله شد پیش از آنکه قیمت به تارگت برسد → مشکل از روند ۴ساعته.",
        "بیس_۱۵دقیقه = روند ۴ساعته سر جایش ماند و قیمت بعد از زدن استاپ به تارگت رسید → جهت درست بود، بیس ۱۵دقیقه نگه نداشت.",
        f"نامشخص = تا {STOP_CAUSE_DAYS} روز بعد از ورود نه روند برگشت نه تارگت خورد.",
        "بیس_عمق_خلاف_جهت_R = در استاپ‌های «بیس»، قیمت پیش از رسیدن به تارگت چند R خلاف جهت رفت "
        "(نزدیک ۱ تا ۱.۵ = استاپ فقط کمی کوچک بود؛ خیلی بیشتر = خود بیس اشتباه بود).",
    ]}).to_excel(sw, sheet_name="دلیل_استاپ‌ها", index=False, startrow=len(cdf) + 2)

    fun = funnel_table(runs)
    fun.to_excel(sw, sheet_name="قیف", index=False)
    pd.DataFrame({"توضیح": [
        "فقط بیس‌هایی شمرده می‌شوند که در بازه‌ی معامله متولد شده‌اند.",
        "«آماده نشد»: هیچ‌وقت اجازه‌ی معامله نگرفت؛ آخرین دلیلی که جلویش را گرفت شمرده شده است.",
        "«آماده شد»: ربات منتظر رسیدن قیمت به آن بیس ماند (روندها و فیلترهای ۴ساعته اجازه دادند).",
        "جمع ردیف‌های ■ = مرحله‌ی ۵. ستون ٪ = سهم هر ردیف از بیس‌های معتبر اجرای اصلی.",
    ]}).to_excel(sw, sheet_name="قیف", index=False, startrow=len(fun) + 2)
    ydf = yearly_table(runs)
    if not ydf.empty:
        ydf.to_excel(sw, sheet_name="سال‌ها", index=False)

    sdf = session_results_table(runs)
    if not sdf.empty:
        sdf.to_excel(sw, sheet_name="سشن‌ها", index=False)
        pd.DataFrame({"توضیح": [
            f"سشن از روی ساعت ورود معامله؛ ساعت دیتا {SESSION_HOUR_SHIFT:+d} ساعت = UTC (SESSION_HOUR_SHIFT).",
            f"خالص_تقریبی٪_حساب = خالص R × ریسک هر معامله ({RISK_PER_TRADE * 100:g}٪) — بدون اثر مرکب.",
        ]}).to_excel(sw, sheet_name="سشن‌ها", index=False, startrow=len(sdf) + 2)

    reviews = [(name,) + trades_review_table(name, results, frames) for name, results, _b in runs]
    tabs = [t for _, t, _raw in reviews if not t.empty]
    if tabs:
        pd.concat(tabs, ignore_index=True).to_excel(sw, sheet_name="معاملات", index=False)
    # راست‌به‌چپ و عرض ستون‌ها
    for ws in sw.book.worksheets:
        ws.sheet_view.rightToLeft = True
        for col in ws.columns:
            w = max((len(str(c.value)) for c in col[:300] if c.value is not None), default=8)
            ws.column_dimensions[col[0].column_letter].width = min(max(10, w * 1.1), 70)
    return reviews


# ============================================================================
# اجرا
# ============================================================================
def main():
    global BACKTEST_START, BACKTEST_END
    outdir = os.path.join(os.getcwd(), "خروجی")
    os.makedirs(outdir, exist_ok=True)
    datadir = os.path.join(os.path.expandvars(r"%USERPROFILE%"), "Desktop", "0")

    sources = find_data_sources(datadir)
    if not sources:
        hint = (" — فایل‌های اینجا RAR هستند؛ بازشان کن (Extract) یا همان ZIPهای خروجی export_data را بگذار."
                if glob.glob(os.path.join(datadir, "*.rar")) else "")
        raise FileNotFoundError(f"هیچ دیتایی (ZIP یا پوشه‌ی CSV) در مسیر دیتا پیدا نشد: {datadir}{hint}")

    spreads = dict(SPREAD_TABLE)
    mt5_spreads = load_mt5_spreads(datadir)
    if mt5_spreads:
        spreads.update(mt5_spreads)
        SPREAD_TABLE.update(mt5_spreads)
        print("📏 اسپرد هر نماد از spreads.csv (متاتریدر خودت): " + " | ".join(
            f"{k} {v / pip_size(k):.1f}" for k, v in sorted(mt5_spreads.items())) + " پیپ")
    else:
        print("⚠️ spreads.csv در پوشه‌ی دیتا نیست → اسپرد از جدول تقریبی. برای اسپرد واقعی export_spreads.bat را اجرا کن.")

    print("📐 قوانین:")
    print(f"   بیس ۱۵دقیقه: کنسالیدیشن اوی تا {LEGOUT_CLEAR_BARS} کندل | لگ‌اوت قوی ≥ {MIN_LEGOUT_BODY_ATR:g}×ATR | "
          f"تأیید چاک | باطل با کلوز پشت دیستال")
    print(f"   روند ۴ساعته و ۱۵دقیقه هم‌جهت (سقف/کف {STRUCT_SWING_N} کندل هر طرف) | داخل زون مخالف ۴ساعته نه | "
          f"تا زون مخالف ≥ {OPP_ZONE_ROOM_R:g}R | سی‌پی پشت‌سرهم: {MAX_CONSECUTIVE_CP}")
    print(f"   تأیید ۱دقیقه: فقط تست اول (تست تازه = برگشت بعد از {LTF_TEST_AWAY_R:g}R دور شدن) | بیس‌های چسبیده "
          f"≤{CHOCH_CLUSTER_MAX_BARS} کندل و ≤{CHOCH_CLUSTER_GAP_ATR:g}×ATR | اوردر پرنشده با {LTF_CANCEL_R:g}R لغو")
    print(f"   ورود +{ENTRY_OFF * 100:.0f}٪ | استاپ {SL_OFF * 100:.0f}٪ پشت دیستال | تارگت {RR:g}R | "
          f"نصف حجم در {PARTIAL_AT_R:g}R | ریسک {RISK_PER_TRADE * 100:g}٪ حساب | کمیسیون ندارد")

    frames = {}
    for sym, src in sources.items():
        if ONLY_SYMBOLS and sym not in ONLY_SYMBOLS:
            continue
        df15, df4, m1 = load_symbol(src)
        if m1 is None or m1.empty:
            print(f"⚠️ {sym}: دیتای ۱دقیقه (فایل -1.csv) نیست → کنار گذاشته شد. export_data را با تایم M1 اجرا کن.")
            continue
        frames[sym] = (df15, df4, m1)
    if ONLY_SYMBOLS:
        miss = [s for s in ONLY_SYMBOLS if s not in sources]
        print(f"🎯 نمادها: {', '.join(frames) or '—'}" + (f" (دیتای {', '.join(miss)} پیدا نشد)" if miss else ""))
    if not frames:
        raise ValueError("هیچ نمادی با دیتای کامل (-1، -15 و -240) در پوشه‌ی دیتا نیست.")

    # بازه‌ی بک‌تست با دیتای ۱دقیقه هماهنگ می‌شود: جایی که همه‌ی نمادها دیتای ۱دقیقه‌ی پیوسته دارند
    # (اگر وسط دیتای ۱دقیقه جای خالیِ بیش از ۷ روز باشد، از بعد از آخرین جای خالی)
    def m1_start(sym, m1):
        tt = m1["time"].to_numpy(dtype="datetime64[ns]")
        gaps = np.flatnonzero(np.diff(tt) > np.timedelta64(7, "D"))
        if not len(gaps):
            return pd.Timestamp(tt[0])
        g = gaps[-1]
        print(f"⚠️ {sym}: دیتای ۱دقیقه از {pd.Timestamp(tt[g]):%Y-%m-%d} تا {pd.Timestamp(tt[g + 1]):%Y-%m-%d} "
              f"جای خالی دارد → بک‌تست از بعد از آن")
        return pd.Timestamp(tt[g + 1])

    l0 = max(m1_start(s, f[2]) for s, f in frames.items())
    l1 = min(pd.Timestamp(f[2]["time"].max()) for f in frames.values())
    s0, e0 = BACKTEST_START, (BACKTEST_END if BACKTEST_END is not None else l1)
    ns, ne = max(s0, l0), min(e0, l1)
    if ns >= ne:                      # هیچ هم‌پوشانی ندارند → کل بازه‌ی دیتای ۱دقیقه
        ns, ne = l0, l1
    BACKTEST_START, BACKTEST_END = pd.Timestamp(ns), pd.Timestamp(ne)

    d0 = min(f[0]["time"].min() for f in frames.values())
    d1 = max(f[0]["time"].max() for f in frames.values())
    print(f"\n📂 دیتا از: {datadir}")
    print(f"   {len(frames)} نماد | از {pd.Timestamp(d0).date()} تا {pd.Timestamp(d1).date()}"
          f"  ({(pd.Timestamp(d1) - pd.Timestamp(d0)).days / 365.25:.1f} سال)")
    print(f"   معامله‌ها از {BACKTEST_START.date()} تا "
          f"{BACKTEST_END.date() if BACKTEST_END is not None else 'پایان دیتا'}؛ {WARMUP_DAYS} روز قبلش فقط برای "
          f"گرم‌کردن روند و بیس‌ها.")

    plan = [(MAIN_RUN, {}, "قوانین بالای فایل")] + [(nm, kw, desc) for nm, (kw, desc) in EXTRA_RUNS.items()]
    runs = []
    print(f"\n🧪 {len(plan)} اجرا (هر کدام جدا، همه‌ی نمادها روی یک حساب):")
    for k, (name, kw, desc) in enumerate(plan, start=1):
        print(f"   [{k}/{len(plan)}] {name}: {desc} ...", flush=True)
        try:
            res, book = run_portfolio(frames, spreads, **kw)
        except Exception as e:
            if k == 1:
                raise
            print(f"   ⚠️ اجرای {name} ناموفق بود: {e}")
            continue
        R = _all_trades(res)["نتیجه_R"].astype(float)
        print(f"        بازده {(book.equity / book.start_equity - 1) * 100:.2f}٪ | افت {book.max_dd * 100:.2f}٪ | "
              f"برد {float((R > 0).mean() * 100) if len(R) else 0.0:.1f}٪ | معامله {len(R)}")
        runs.append((name.replace("_", " "), res, book))

    summary_path = os.path.join(outdir, "خلاصه_نتایج.xlsx")
    reviews = None
    try:
        with pd.ExcelWriter(summary_path, engine="openpyxl") as sw:
            reviews = write_excel(sw, runs, frames)
    except Exception as e:
        import traceback
        print("⚠️ ساخت فایل خروجی ناموفق بود:", str(e))
        traceback.print_exc()

    # نمودار هر معامله (بعد از ذخیره‌ی اکسل، تا اگر مشکلی پیش آمد اکسل از دست نرود)
    if TRADE_CHARTS and reviews:
        chart_dir = os.path.join(outdir, "نمودار_معاملات")
        print(f"\n🖼️ نمودار معاملات در «{chart_dir}» ...", flush=True)
        for k, (nm, _tb, raw) in enumerate(reviews, start=1):
            try:
                print(f"   {nm}: {draw_trade_charts(chart_dir, k, nm, raw, frames)} نمودار")
            except Exception as e:
                print(f"   ⚠️ نمودار «{nm}» ساخته نشد: {e}")

    print("تمام شد ✅")
    print("خلاصه_نتایج.xlsx ساخته شد ✅ |", summary_path)


if __name__ == "__main__":
    main()
