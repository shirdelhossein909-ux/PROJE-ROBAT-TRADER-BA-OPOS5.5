# -*- coding: utf-8 -*-
"""ربات معامله‌گر لایو (نسخه ۲) — استراتژی زون عرضه/تقاضا روی متاتریدر ۵.

ویژگی‌ها:
  - مغز ربات همان backtest_one از run_backtest.py است (یک مغز برای بک‌تست و لایو).
  - سفارش‌ها «از قبل» گذاشته می‌شوند: زونی که فیلترهایش سبز است، سفارش لیمیتش داخل
    متاتریدر آماده است؛ اگر وسط کندل قیمت برسد، سرور بروکر همان لحظه پر می‌کند
    (جا ماندن به‌خاطر انتظار برای کلوز کندل وجود ندارد).
  - حد ضرر و حد سود روی خود سفارش ست می‌شود — اجرا با سرور بروکر است، حتی اگر
    کامپیوتر خاموش شود پوزیشن‌ها بی‌محافظ نمی‌مانند.
  - فقط روی نمادهای سبد انتخابی کار می‌کند و فقط به سفارش‌های خودش (امضای MAGIC)
    دست می‌زند — با معاملات دستی یا ربات‌های دیگر هیچ کاری ندارد.
  - لاگ کامل فارسی: دلیل هر سفارش، دلیل سفارش نگذاشتن، پر شدن، بسته شدن با سود/ضرر،
    قطع و وصل ارتباط — هم در CMD هم در فایل (پوشه‌ی logs کنار همین فایل).
  - ضدضربه: قطع ارتباط → اخطار + تلاش دوباره هر چند ثانیه تا وصل شود؛ هیچ خطایی
    ربات را ساکت نمی‌کند؛ فایل ضربان قلب (logs/heartbeat.txt) هر دور به‌روز می‌شود.

  - نسخه ۳ (رفع ایرادهای ۶ هفته لایو):
      · سیو سود فقط یک بار (حجم پوزیشن با حجم ورودش مقایسه می‌شود؛ کد برگشتی 0 دیگر گولش نمی‌زند)
      · نتیجه‌ی هر دستور با خواندن دوباره‌ی حساب تأیید می‌شود
      · شناسه‌ی پایدار زون + تطبیق با قیمت → سفارش تکراری نمی‌گذارد و تکراری‌های قبلی را جمع می‌کند
      · نمادی که بازارش بسته است (طلا ۰۰ تا ۰۱): دستورهایش صف می‌شوند و با باز شدن بازار انجام می‌شوند
      · حجم سفارش‌ها فقط وقتی سشن واقعاً عوض می‌شود تغییر می‌کند (نه سر هر کندل و نه ساعت ۰۰)
      · فقط یک ربات هم‌زمان؛ نگهبان (watchdog.py) اگر ربات افتاد یا گیر کرد دوباره بالا می‌آوردش
      · توکن بله از فایل bale_token.txt خوانده می‌شود، نه از داخل کد

اجرا:  start_robot.bat          (متاتریدر ۵ باز، لاگینِ دمو، Algo Trading روشن)
توقف:  Ctrl+C  یا  stop_robot.bat   (در هر دو حالت نگهبان دوباره روشنش نمی‌کند)
"""

import os
import sys
import math
import json
import time as _time
import datetime as dt
import urllib.request

import pandas as pd

import run_backtest as rb

# ================== تنظیمات ==================
# فقط همین نمادها — سبد انتخابی. ربات سراغ هیچ نماد دیگری نمی‌رود.
# ترتیب مهم است: در سهمیه‌بندی دوری، نماد اولِ هر دور اولویت می‌گیرد.
# باید عیناً با LIVE_BASKET_ORDER در run_backtest.py یکی بماند.
#
# USDCAD و NZDUSD حذف شدند. دلیل: در هر دو دیتاست (۶ ساله‌ی این بروکر و ۸ ساله‌ی
# بروکر قبلی) تنها نمادهای ضررده بودند، تست پایداری هم هر دو نیمه را منفی نشان داد،
# و تست حذف تک‌نماد گفت برداشتنشان حساب را واضح بهتر می‌کند.
BASKET = ["XAUUSD", "AUDJPY", "AUDUSD", "CHFJPY", "EURCAD", "EURNZD",
          "GBPJPY", "GBPNZD", "NZDCAD", "USDCHF"]

RISK_PER_TRADE = 0.005    # ریسک هر معامله: نیم درصد از اکویتی

# سیو سود (برنده‌ی بک‌تست): وقتی سود پوزیشن به ۲ برابر ریسک رسید، نصف حجم نقد می‌شود
MANAGE_PARTIAL = True
MANAGE_TRIGGER_R = 2.0
PARTIAL_FRAC = 0.5

# --- وزن‌دهی ریسک بر اساس سشن (برنده‌ی بک‌تست: حالت تهاجمی) ---
# ضریب ریسک هر سشن؛ ۱ = ریسک پایه (RISK_PER_TRADE)
USE_SESSION_WEIGHTS = True
SESSION_WEIGHTS = {
    "لندن": 1.5,
    "همپوشانی لندن-نیویورک": 1.25,
    "سیدنی/پایان روز": 1.0,
    "آسیا (توکیو)": 0.75,
    "آسیا (پایان)": 0.5,
    "نیویورک": 0.5,
}
# اگر وزن سشن عوض شد، سفارش‌های در انتظار با حجم جدید دوباره چیده شوند
# (تا رفتار لایو با بک‌تست یکی بماند — بک‌تست وزن را بر اساس سشنِ لحظه‌ی ورود می‌گیرد)
SESSION_REPLACE_ORDERS = True
SESSION_REPLACE_TOLERANCE = 0.15   # اختلاف حجم کمتر از ۱۵٪ → دست نمی‌زنیم
RESERVE = 0.15            # سرمایه‌ی رزرو (مثل بک‌تست)
MAX_OPEN_TOTAL = 8        # سقف تریدهای باز هم‌زمان کل حساب — پر شود، اوردرهای در انتظار موقتاً جمع می‌شوند
MAX_PENDING_TOTAL = 8     # سقف کل اوردرهای در انتظار روی کل حساب (هر نماد حداکثر ۳)
MAX_RISK_HARD_CAP = 0.01  # قفل ایمنی: ریسک واقعی هیچ معامله‌ای از ۱٪ اکویتی بیشتر نشود
ENTRY_OFF = -0.50         # ورود وسط زون (مثل بک‌تست)
RR = 3.0                  # حد سود = ۳ برابر ریسک

POLL_SECONDS = 30         # هر چند ثانیه وضعیت را چک کند
RECONNECT_SECONDS = 5     # فاصله‌ی تلاش‌های اتصال دوباره
RETRY_POLL_SECONDS = 5    # وقتی دستوری مانده (بازار نماد بسته بود / قیمت نبود)، هر چند ثانیه دوباره تلاش شود
STALE_TICK_SECONDS = 120  # آخرین قیمت نماد از این قدیمی‌تر باشد (نسبت به بقیه) → بازار آن نماد بسته حساب می‌شود
H4_BARS = 2000            # عمق تاریخچه برای بازپخش استراتژی
D1_BARS = 500
W1_BARS = 300

MAGIC = 777001            # امضای سفارش‌های این ربات
ALLOW_REAL = False        # قفل ایمنی: فقط حساب دمو
# مسیر لاگ باید مطلق باشد. با مسیر نسبی، هر چیزی که پوشه‌ی جاری را عوض کند
# (از جمله mt5.initialize وقتی خودش ترمینال را بالا می‌آورد) باعث می‌شود لاگ‌ها
# جای دیگری بیفتند — بدون هیچ خطایی. یک بار همین اتفاق افتاد و روزها طول کشید
# تا معلوم شود لاگ کجا رفته.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "logs")

# --- خبررسانی به پیام‌رسان «بله» ---
# توکن ربات بله را اینجا ننویس (این فایل روی گیت‌هاب می‌رود و هر کسی توکن را ببیند، ربات بله‌ات را در اختیار دارد).
# توکن را در یک فایل متنی به اسم bale_token.txt کنار همین فایل بگذار (فقط خود توکن، در یک خط).
# اگر هیچ توکنی نباشد، خبررسانی بله خاموش است و ربات کارش را می‌کند.
BALE_TOKEN = ""
BALE_CHAT_ID = ""         # خالی بگذار تا خودش پیدا کند (فقط اول یک پیام به ربات بله‌ات بده)
DAILY_REPORT_HOUR = 12    # ساعت ارسال گزارش‌های روزانه/هفتگی/ماهانه (به وقت VPS)
START_BALANCE = 100000.0  # سرمایه‌ی اولیه — برای محاسبه‌ی «سود کل حساب از شروع» (روی حساب جدید عوضش کن)
# =============================================

def _read_secret(fname, env_name):
    """اول متغیر محیطی، بعد فایل کنار ربات (utf-8-sig تا BOM نوت‌پد مشکلی نسازد)."""
    v = os.environ.get(env_name, "").strip()
    if v:
        return v
    try:
        with open(os.path.join(BASE_DIR, fname), encoding="utf-8-sig") as f:
            return f.read().strip()
    except Exception:
        return ""


if not BALE_TOKEN:
    BALE_TOKEN = _read_secret("bale_token.txt", "BALE_TOKEN")

# کدهای برگشتی متاتریدر
RC_DONE = {10008, 10009, 10010}           # ثبت شد / انجام شد / بخشی انجام شد
# خطاهای گذرا (بازار بسته، نبود قیمت، قطعی، شلوغی...) — بعداً دوباره تلاش می‌شود
RC_TRANSIENT = {0, 10004, 10011, 10012, 10018, 10020, 10021, 10024, 10027, 10031}
EXIT_NO_RESTART = 3       # کد خروجی که به start_robot.bat می‌گوید «دوباره راه‌اندازی نکن»

# بازپخش لایو باید کل پنجره‌ی دیتا را ببیند (بدون برش تاریخ بک‌تست)
rb.BACKTEST_START = pd.Timestamp("2000-01-01")
rb.BACKTEST_END = None
rb.USE_M15 = False

try:
    import MetaTrader5 as mt5
except ImportError:
    print("پکیج MetaTrader5 نصب نیست. نصب:  pip install MetaTrader5")
    sys.exit(1)


# ---------------- لاگ و ضربان قلب ----------------
os.makedirs(LOG_DIR, exist_ok=True)

_log_fail = {"n": 0, "reported": False}

def log(msg, symbol="", bale=True):
    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{stamp}] {symbol + ' | ' if symbol else ''}{msg}"

    # چاپ در پنجره نباید هیچ‌وقت ربات را بیندازد. اگر پنجره‌ی CMD از بین رفته
    # باشد، نوشتن روی خروجی خطا می‌دهد — و آن خطا نباید به بیرون درز کند.
    try:
        print(line, flush=True)
    except Exception:
        pass

    fname = os.path.join(LOG_DIR, "گزارش_" + dt.datetime.now().strftime("%Y%m%d") + ".txt")
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(fname, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        _log_fail["n"] = 0
    except Exception as e:
        # شکستِ بی‌صدا ممنوع: اگر نوشتن لاگ کار نکند، دست‌کم یک بار از راه بله بگو.
        _log_fail["n"] += 1
        if not _log_fail["reported"] and _log_fail["n"] >= 3:
            _log_fail["reported"] = True
            try:
                bale_send(f"⚠️ نوشتن فایل لاگ کار نمی‌کند ({e}) — مسیر: {LOG_DIR}\n"
                          f"ربات به کارش ادامه می‌دهد ولی لاگ روی دیسک ثبت نمی‌شود.")
            except Exception:
                pass

    # خط‌های لاگ به بله هم فرستاده می‌شوند (مگر آن‌هایی که در پیام ترکیبی می‌روند)
    if bale:
        bale_send(line)


# ---------------- خبررسانی به بله ----------------
from collections import deque

_bale_chat_id = None
_bale_fail_logged = False
_bale_queue = deque(maxlen=500)  # پیام‌های نرفته نگه داشته می‌شوند تا ارتباط برگردد

def _bale_detect_chat():
    """اگر چت‌آیدی تنظیم نشده باشد، از آخرین پیامی که به ربات بله داده‌ای پیدایش می‌کند."""
    try:
        with urllib.request.urlopen(
                f"https://tapi.bale.ai/bot{BALE_TOKEN}/getUpdates", timeout=10) as r:
            data = json.loads(r.read().decode("utf-8"))
        for u in reversed(data.get("result", [])):
            chat = (u.get("message") or {}).get("chat") or {}
            if chat.get("id"):
                print(f"[بله] چت‌آیدی شناسایی شد: {chat['id']} — برای اطمینان همین را در BALE_CHAT_ID بگذار.")
                return str(chat["id"])
        print("[بله] هنوز پیامی به ربات بله‌ات نداده‌ای — اول در بله به رباتت «سلام» بفرست.")
    except Exception as e:
        print(f"[بله] شناسایی چت‌آیدی ناموفق: {e}")
    return None


def bale_send(text):
    """پیام را در صف می‌گذارد و تلاش می‌کند صف را بفرستد؛ نرفته‌ها گم نمی‌شوند."""
    if not BALE_TOKEN:
        return
    _bale_queue.append(text)
    bale_flush()


def bale_flush():
    """ارسال پیام‌های مانده در صف، به ترتیب؛ اگر ارتباط نبود، صف می‌ماند برای بعد."""
    global _bale_chat_id, _bale_fail_logged
    if not BALE_TOKEN or not _bale_queue:
        return
    if _bale_chat_id is None:
        _bale_chat_id = BALE_CHAT_ID or _bale_detect_chat()
        if _bale_chat_id:
            # نگهبان (watchdog.py) هم از همین چت‌آیدی برای هشدار استفاده می‌کند
            try:
                with open(os.path.join(LOG_DIR, "bale_chat_id.txt"), "w", encoding="utf-8") as f:
                    f.write(str(_bale_chat_id))
            except Exception:
                pass
    if not _bale_chat_id:
        return
    while _bale_queue:
        txt = _bale_queue[0]
        try:
            data = json.dumps({"chat_id": _bale_chat_id, "text": txt}).encode("utf-8")
            req = urllib.request.Request(
                f"https://tapi.bale.ai/bot{BALE_TOKEN}/sendMessage",
                data=data, headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=5)
            _bale_queue.popleft()
            if _bale_fail_logged:
                _bale_fail_logged = False
                print("[بله] ارتباط با بله برگشت — پیام‌های مانده ارسال شدند.")
        except Exception as e:
            if not _bale_fail_logged:
                _bale_fail_logged = True
                print(f"[بله] ارسال فعلاً ناموفق ({e}) — {len(_bale_queue)} پیام در صف می‌ماند و بعداً می‌رود.")
            break

def heartbeat(status="سالم"):
    try:
        with open(os.path.join(LOG_DIR, "heartbeat.txt"), "w", encoding="utf-8") as f:
            f.write(f"{dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | وضعیت: {status}\n")
    except Exception:
        pass


# ---------------- ثبت دلیل بسته شدن ربات ----------------
# اگر ربات بسته شود (کرش، بسته شدن پنجره، Sign out، ری‌استارت ویندوز)، دلیلش اینجا ثبت می‌شود تا
# نگهبان (watchdog.py) و اجرای بعدی ربات آن را در لاگ و بله گزارش کنند. اگر ربات فرصت نوشتن
# نداشت (مثلاً ری‌استارت ناگهانی VPS)، نگهبان دلیل را از رویدادهای ویندوز پیدا می‌کند.
import atexit
import traceback
import faulthandler

EXIT_FILE = os.path.join(LOG_DIR, "last_exit.json")
_exit_state = {"owner": False, "noted": False}


def note_start():
    _exit_state["owner"] = True
    try:
        with open(EXIT_FILE, "w", encoding="utf-8") as f:
            json.dump({"running": True, "pid": os.getpid(),
                       "started": dt.datetime.now().isoformat(timespec="seconds")}, f, ensure_ascii=False)
    except Exception:
        pass


def note_exit(reason, detail=""):
    """دلیل بسته شدن را در فایل می‌نویسد (فقط ربات اصلی، نه نسخه‌ی دومی که بالا نیامد)."""
    if not _exit_state["owner"]:
        return
    _exit_state["noted"] = True
    try:
        with open(EXIT_FILE, "w", encoding="utf-8") as f:
            json.dump({"running": False, "pid": os.getpid(), "reason": reason, "detail": str(detail)[-3000:],
                       "time": dt.datetime.now().isoformat(timespec="seconds")}, f, ensure_ascii=False)
    except Exception:
        pass


def _bale_now(text, timeout=2.5):
    """ارسال فوری به بله (بدون صف) — برای لحظه‌ای که پنجره در حال بسته شدن است و وقت کم است."""
    chat = _bale_chat_id or BALE_CHAT_ID
    if not chat:
        try:
            with open(os.path.join(LOG_DIR, "bale_chat_id.txt"), encoding="utf-8") as f:
                chat = f.read().strip()
        except Exception:
            chat = ""
    if not BALE_TOKEN or not chat:
        return
    try:
        data = json.dumps({"chat_id": chat, "text": text}).encode("utf-8")
        req = urllib.request.Request(f"https://tapi.bale.ai/bot{BALE_TOKEN}/sendMessage",
                                     data=data, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=timeout)
    except Exception:
        pass


def _log_file_only(msg):
    try:
        fname = os.path.join(LOG_DIR, "گزارش_" + dt.datetime.now().strftime("%Y%m%d") + ".txt")
        with open(fname, "a", encoding="utf-8") as f:
            f.write(f"[{dt.datetime.now():%Y-%m-%d %H:%M:%S}] {msg}\n")
    except Exception:
        pass


def _excepthook(tp, val, tb):
    """خطایی که ربات را می‌اندازد، قبل از بسته شدن در لاگ و بله ثبت می‌شود."""
    if issubclass(tp, KeyboardInterrupt):
        note_exit("توقف دستی (Ctrl+C)")
        try:
            _mark_stopped()
        except Exception:
            pass
    else:
        txt = "".join(traceback.format_exception(tp, val, tb))
        note_exit("ربات به‌خاطر یک خطای پیش‌بینی‌نشده بسته شد (کرش پایتون)", txt)
        _log_file_only("💥 ربات به‌خاطر خطا بسته شد:\n" + txt)
        _bale_now("💥 ربات به‌خاطر یک خطا بسته شد و start_robot.bat تا ۱۰ ثانیه دیگر دوباره روشنش می‌کند.\n"
                  + txt[-1500:])
    sys.__excepthook__(tp, val, tb)


def _on_exit():
    if _exit_state["owner"] and not _exit_state["noted"]:
        note_exit("ربات بسته شد (خروج بدون خطا)")


# کرش‌های خیلی شدید (مثلاً داخل خود کتابخانه‌ی متاتریدر) که پایتون فرصت گزارش ندارد:
# ردشان در logs/crash_dump.txt می‌ماند و نگهبان آن را گزارش می‌کند
try:
    os.makedirs(LOG_DIR, exist_ok=True)
    _crash_file = open(os.path.join(LOG_DIR, "crash_dump.txt"), "a", encoding="utf-8")
    faulthandler.enable(file=_crash_file, all_threads=True)
except Exception:
    _crash_file = None

_console_handler = []


def _install_console_handler():
    """ویندوز قبل از بستن پنجره‌ی CMD (دکمه‌ی X)، Sign out یا خاموش شدن، چند ثانیه به برنامه
    وقت می‌دهد؛ در همین چند ثانیه دلیل در فایل و بله ثبت می‌شود."""
    if os.name != "nt":
        return
    try:
        import ctypes
        from ctypes import wintypes
        names = {2: "پنجره‌ی CMD ربات بسته شد (دکمه‌ی X یا بسته شدن پنجره)",
                 5: "کاربر از ویندوز خارج شد (Sign out / Log off) — این کار همه‌ی برنامه‌ها را می‌بندد",
                 6: "ویندوز در حال خاموش/ری‌استارت شدن است"}

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.DWORD)
        def handler(ev):
            if ev in names:
                note_exit(names[ev])
                _log_file_only(f"🛑 {names[ev]} — ربات بسته می‌شود؛ نگهبان دوباره روشنش می‌کند.")
                _bale_now(f"🛑 {names[ev]}. ربات بسته شد؛ نگهبان تا چند دقیقه‌ی دیگر دوباره روشنش می‌کند.")
            return False      # ادامه‌ی رفتار عادی ویندوز (Ctrl+C هم به پایتون می‌رسد)

        _console_handler.append(handler)
        ctypes.windll.kernel32.SetConsoleCtrlHandler(handler, True)
    except Exception:
        pass


# ---------------- اتصال ضدضربه ----------------
def connect_with_retry(bale_notify=True):
    """آن‌قدر تلاش می‌کند تا وصل شود؛ هر مشکل را با زبان ساده گزارش می‌دهد."""
    attempt = 0
    while True:
        attempt += 1
        if not mt5.initialize():
            log(f"⛔ اتصال به متاتریدر برقرار نشد (تلاش {attempt}): {mt5.last_error()} — "
                f"متاتریدر ۵ باید باز و لاگین باشد. {RECONNECT_SECONDS} ثانیه دیگر دوباره تلاش می‌کنم...")
            heartbeat("قطع — در حال تلاش برای اتصال")
            _time.sleep(RECONNECT_SECONDS)
            continue

        ti = mt5.terminal_info()
        if ti is None or not ti.trade_allowed:
            log(f"⛔ دکمه‌ی Algo Trading در متاتریدر خاموش است! روشنش کن (تلاش {attempt}). "
                f"{RECONNECT_SECONDS} ثانیه دیگر دوباره چک می‌کنم...")
            heartbeat("منتظر روشن شدن Algo Trading")
            mt5.shutdown()
            _time.sleep(RECONNECT_SECONDS)
            continue

        acc = mt5.account_info()
        if acc is None:
            log(f"⛔ اطلاعات حساب نیامد — در متاتریدر لاگین نیستی؟ (تلاش {attempt})")
            heartbeat("منتظر لاگین حساب")
            mt5.shutdown()
            _time.sleep(RECONNECT_SECONDS)
            continue

        if acc.trade_mode != mt5.ACCOUNT_TRADE_MODE_DEMO and not ALLOW_REAL:
            log(f"🛑 حساب {acc.login} دمو نیست! این نسخه فقط روی دمو کار می‌کند. ربات خاموش شد.")
            mt5.shutdown()
            sys.exit(EXIT_NO_RESTART)

        log(f"✅ اتصال برقرار شد | حساب {acc.login} ({acc.server}) | "
            f"{'دمو' if acc.trade_mode == mt5.ACCOUNT_TRADE_MODE_DEMO else 'واقعی'} | "
            f"موجودی {acc.balance:,.2f} {acc.currency}", bale=bale_notify)
        heartbeat("سالم")
        return acc


def ensure_connected():
    """اگر وسط کار ارتباط قطع شد: اخطار بده و تا وصل شدن تلاش کن."""
    ti = mt5.terminal_info()
    if ti is None:
        log("⚠️ ارتباط با متاتریدر قطع شد! تلاش خودکار برای اتصال دوباره شروع شد...")
        heartbeat("قطع — در حال تلاش برای اتصال")
        try:
            mt5.shutdown()
        except Exception:
            pass
        connect_with_retry()
        log("🔄 ارتباط دوباره برقرار شد — ادامه می‌دهیم.")


# بازه‌های سشن (مستقل از فایل بک‌تست تعریف شده تا ربات هرگز به‌خاطر نبودِ تابع کرش نکند)
_SESSION_RANGES = [
    (0, 4,  "آسیا (توکیو)"),
    (4, 8,  "آسیا (پایان)"),
    (8, 12, "لندن"),
    (12, 16, "همپوشانی لندن-نیویورک"),
    (16, 20, "نیویورک"),
    (20, 24, "سیدنی/پایان روز"),
]

def _hour_to_session(h):
    for a, b, nm in _SESSION_RANGES:
        if a <= h < b:
            return nm
    return "نامشخص"


def current_session_weight():
    """وزن ریسکِ سشنِ همین لحظه (بر اساس ساعت UTC)."""
    if not USE_SESSION_WEIGHTS:
        return 1.0, "بدون وزن‌دهی"
    h = dt.datetime.now(dt.timezone.utc).hour
    name = _hour_to_session(h)
    return float(SESSION_WEIGHTS.get(name, 1.0)), name


def pick_filling(si, for_market=True):
    """حالت پرکردن سفارش را از خود نماد می‌خواند (رفع خطای 10030).
    برای بستن پوزیشن (market): IOC یا FOK — برای پندینگ: RETURN."""
    modes = getattr(si, "filling_mode", 0) or 0
    if for_market:
        if modes & 2:   # SYMBOL_FILLING_IOC
            return mt5.ORDER_FILLING_IOC
        if modes & 1:   # SYMBOL_FILLING_FOK
            return mt5.ORDER_FILLING_FOK
        return mt5.ORDER_FILLING_IOC
    return mt5.ORDER_FILLING_RETURN


def resolve_symbol(base):
    """پیدا کردن اسم نماد نزد بروکر (با پسوند/پیشوند احتمالی) و فعال‌سازی آن."""
    if mt5.symbol_info(base) is not None:
        mt5.symbol_select(base, True)
        return base
    cands = mt5.symbols_get(f"*{base}*")
    if cands:
        name = sorted((c.name for c in cands), key=len)[0]
        mt5.symbol_select(name, True)
        return name
    return None


# ---------------- ساعت سرور، باز بودن بازار هر نماد، تأیید دستورها ----------------
_symbols_live = {}   # base → اسم نماد نزد بروکر (در main پر می‌شود)


# زمان تیک‌ها و کندل‌ها به «وقت سرور» است (مثلاً UTC+3)، نه UTC. اختلاف ساعت سرور با ساعت واقعی
# از روی تیک‌هایی که همین الان می‌رسند یاد گرفته و در فایل نگه داشته می‌شود (برای آخر هفته و ری‌استارت).
_srv_offset = [None]          # ثانیه: ساعت سرور − ساعت واقعی
_last_tick_seen = {}
_OFFSET_FILE = os.path.join(LOG_DIR, "server_offset.txt")
try:
    with open(_OFFSET_FILE, encoding="utf-8") as _f:
        _srv_offset[0] = int(_f.read().strip())
except Exception:
    pass


def learn_server_offset():
    """فقط از تیکی یاد می‌گیرد که از دور قبل تا الان رسیده (پس واقعاً تازه است)."""
    now = _time.time()
    for name in _symbols_live.values():
        try:
            tk = mt5.symbol_info_tick(name)
        except Exception:
            continue
        if tk is None or not tk.time:
            continue
        prev = _last_tick_seen.get(name)
        _last_tick_seen[name] = tk.time
        if prev is None or tk.time == prev:
            continue
        diff = tk.time - now
        k = int(round(diff / 1800.0)) * 1800          # اختلاف ساعت سرورها مضرب نیم ساعت است
        if abs(diff - k) > 60:
            continue
        if k != _srv_offset[0]:
            _srv_offset[0] = k
            try:
                with open(_OFFSET_FILE, "w", encoding="utf-8") as f:
                    f.write(str(k))
            except Exception:
                pass
        return


def server_now():
    """ساعت فعلی سرور بروکر. اگر اختلاف ساعت سرور هنوز معلوم نیست: تازه‌ترین تیکِ نمادهای سبد.
    (زمان تیک‌ها به وقت سرور است؛ مقایسه‌اش با ساعت ویندوز چند ساعت خطا دارد.)"""
    if _srv_offset[0] is not None:
        return _time.time() + _srv_offset[0]
    best = None
    for name in _symbols_live.values():
        try:
            tk = mt5.symbol_info_tick(name)
        except Exception:
            tk = None
        if tk is not None and tk.time:
            best = tk.time if best is None else max(best, tk.time)
    return best


def symbol_tradeable(name):
    """بازار همین نماد الان باز است؟ (مثلاً طلا ساعت ۰۰ تا ۰۱ سرور بسته است ولی بقیه بازند)"""
    try:
        tk = mt5.symbol_info_tick(name)
    except Exception:
        return False
    if tk is None or not tk.time or tk.bid <= 0:
        return False
    now = server_now()
    return now is None or (now - tk.time) <= STALE_TICK_SECONDS


def _rc(res):
    return getattr(res, "retcode", None)


def _rc_txt(res):
    if res is None:
        return f"پاسخی نیامد ({mt5.last_error()})"
    return f"کد {res.retcode} | {getattr(res, 'comment', '')}"


def _my_orders(name=None):
    try:
        lst = mt5.orders_get(symbol=name) if name else mt5.orders_get()
    except Exception:
        lst = None
    return [o for o in (lst or ()) if o.magic == MAGIC]


def _order_alive(ticket):
    """True = سفارش هنوز روی حساب است | False = نیست | None = معلوم نشد"""
    try:
        r = mt5.orders_get(ticket=ticket)
    except Exception:
        return None
    if r is None:
        return None
    return len(r) > 0


_gone_tickets = set()   # سفارش‌هایی که همین الان لغو کردیم (ممکن است لحظه‌ای هنوز در فهرست باشند)


def _same_order(o, direction, entry, sl, digits):
    otype = mt5.ORDER_TYPE_BUY_LIMIT if direction == "BUY" else mt5.ORDER_TYPE_SELL_LIMIT
    tol = 0.6 * 10 ** (-int(digits))
    return (o.type == otype and abs(o.price_open - entry) <= tol and abs(o.sl - sl) <= tol)


def _find_order(name, direction, entry, sl, digits, exclude=()):
    """سفارش خودمان با همین جهت/ورود/استاپ روی حساب هست؟ (تأیید ثبت + جلوگیری از سفارش تکراری)"""
    for o in _my_orders(name):
        if o.ticket in _gone_tickets or o.ticket in exclude:
            continue
        if _same_order(o, direction, entry, sl, digits):
            return o
    return None


# دستورهایی که به‌خاطر بسته بودن بازار نماد / نبود قیمت انجام نشدند و باید دوباره تلاش شوند.
# با هر همگام‌سازی کامل (sync_all) از نو ساخته می‌شوند.
_retry_cancel = {}   # ticket → {"base", "name", "o", "why", "nxt", "filters"}
_retry_place = {}    # (base, zone_id) → {"base", "name", "p"}


def _order_dict(o):
    """مشخصات یک سفارش موجود به شکل خواسته‌ی استراتژی (برای چیدن دوباره با حجم تازه)."""
    return {"zone_id": o.comment, "direction": "BUY" if o.type == mt5.ORDER_TYPE_BUY_LIMIT else "SELL",
            "entry": float(o.price_open), "sl": float(o.sl), "tp": float(o.tp)}


# ---------------- دیتا و بازپخش استراتژی ----------------
def fetch_df(broker_name, timeframe, count):
    """فقط کندل‌های بسته‌شده (کندل در حال شکل‌گیری حذف می‌شود)."""
    rates = mt5.copy_rates_from_pos(broker_name, timeframe, 1, count)
    if rates is None or len(rates) == 0:
        return None
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    return df[["time", "open", "high", "low", "close"]].astype(
        {"open": float, "high": float, "low": float, "close": float})


def replay_state(base, broker_name):
    """بازپخش استراتژی روی تاریخچه‌ی بروکر → سفارش‌هایی که همین الان باید وجود داشته باشند."""
    h4 = fetch_df(broker_name, mt5.TIMEFRAME_H4, H4_BARS)
    d1 = fetch_df(broker_name, mt5.TIMEFRAME_D1, D1_BARS)
    w1 = fetch_df(broker_name, mt5.TIMEFRAME_W1, W1_BARS)
    if h4 is None or d1 is None or w1 is None:
        log("⚠️ دیتا از بروکر نیامد — این دور بررسی نشد.", base)
        return None
    out = rb.backtest_one(base, h4, d1, w1, None, 0.0,
                          entry_off=ENTRY_OFF, rr=RR, m15=None, return_state=True)
    return out[6]


# ---------------- سفارش‌گذاری ----------------
def calc_volume(broker_name, si, direction, entry, sl, risk_amt, equity):
    """حجم از روی ریسک ثابت — محاسبه‌ی ضرر با تابع رسمی خود متاتریدر (order_calc_profit)
    که برای هر نمادی (طلا، ین، ...) مشخصات قرارداد همان بروکر را دقیق حساب می‌کند.
    + قفل ایمنی دوبل: ریسک واقعی حجم نهایی دوباره چک می‌شود."""
    order_type = mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL

    loss_1lot = mt5.order_calc_profit(order_type, broker_name, 1.0, entry, sl)
    if loss_1lot is None or loss_1lot >= 0:
        return None, "متاتریدر ضررِ یک لات را حساب نکرد"
    loss_1lot = abs(loss_1lot)

    vol = risk_amt / loss_1lot
    step = si.volume_step or 0.01
    vol = math.floor(vol / step) * step
    if vol < si.volume_min:
        return None, f"حجم لازم ({vol}) از حداقل مجاز نماد ({si.volume_min}) کمتر است"
    vol = min(vol, si.volume_max)
    vol = round(vol, 8)

    # قفل ایمنی دوبل: ریسک واقعی این حجم چقدر است؟
    real_loss = mt5.order_calc_profit(order_type, broker_name, vol, entry, sl)
    if real_loss is None:
        return None, "چک نهایی ریسک ممکن نشد"
    real_loss = abs(real_loss)
    if real_loss > risk_amt * 1.2:
        return None, f"ریسک واقعی ({real_loss:,.0f}$) از حد مجاز ({risk_amt:,.0f}$) بیشتر شد — سفارش رد شد"
    if real_loss > equity * MAX_RISK_HARD_CAP:
        return None, f"ریسک واقعی ({real_loss:,.0f}$) از قفل ایمنی {MAX_RISK_HARD_CAP*100:g}٪ حساب بیشتر است — سفارش رد شد"
    return vol, f"ریسک واقعی {real_loss:,.0f}$"


def _queue_place(base, broker_name, p, why):
    key = (base, str(p["zone_id"]))
    first = key not in _retry_place
    _retry_place[key] = {"base": base, "name": broker_name, "p": p}
    if first:
        log(f"⏳ زون {p['zone_id']}: سفارش فعلاً گذاشته نشد ({why}) — "
            f"هر چند ثانیه دوباره تلاش می‌کنم تا بازار این نماد باز شود.", base)
    return "retry"


def place_pending(base, broker_name, p):
    """سفارش لیمیت یک زون را می‌گذارد.
    خروجی: "ok" (روی حساب هست) | "retry" (بعداً دوباره) | "skip" (دیگر معنا ندارد) | "fail" (رد شد)
    نتیجه فقط از روی کد برگشتی قضاوت نمی‌شود: بعد از ارسال، فهرست سفارش‌های حساب دوباره خوانده
    می‌شود (یک بار متاتریدر برای دستورهای موفق کد 0 برگرداند و ربات فکر کرد رد شده‌اند)."""
    key = (base, str(p["zone_id"]))
    si = mt5.symbol_info(broker_name)
    tick = mt5.symbol_info_tick(broker_name)
    acc = mt5.account_info()
    if si is None or tick is None or acc is None or tick.bid <= 0 or not symbol_tradeable(broker_name):
        return _queue_place(base, broker_name, p, "بازار این نماد بسته است یا قیمت نیامد")

    entry = round(p["entry"], si.digits)
    sl = round(p["sl"], si.digits)
    tp = round(p["tp"], si.digits)

    # همین سفارش (همین جهت/ورود/استاپ) از قبل روی حساب هست؟ دومی نگذار.
    ex = _find_order(broker_name, p["direction"], entry, sl, si.digits)
    if ex is not None:
        _retry_place.pop(key, None)
        log(f"✔️ زون {p['zone_id']}: سفارشش از قبل روی حساب هست (تیکت {ex.ticket}) — سفارش دوم گذاشته نمی‌شود.",
            base, bale=False)
        return "ok"

    if p["direction"] == "BUY" and entry >= tick.ask:
        _retry_place.pop(key, None)
        log(f"⏭️ زون {p['zone_id']}: قیمت الان ({tick.ask}) پایین‌تر از نقطه‌ی ورود خرید ({entry}) است — سفارش معنا ندارد.", base)
        return "skip"
    if p["direction"] == "SELL" and entry <= tick.bid:
        _retry_place.pop(key, None)
        log(f"⏭️ زون {p['zone_id']}: قیمت الان ({tick.bid}) بالاتر از نقطه‌ی ورود فروش ({entry}) است — سفارش معنا ندارد.", base)
        return "skip"

    w, sess_name = current_session_weight()
    risk_amt = acc.equity * (1.0 - RESERVE) * RISK_PER_TRADE * w
    vol, vol_msg = calc_volume(broker_name, si, p["direction"], entry, sl, risk_amt, acc.equity)
    if vol is None:
        _retry_place.pop(key, None)
        log(f"⚠️ زون {p['zone_id']}: سفارش گذاشته نشد — {vol_msg}", base)
        return "fail"

    req = {
        "action": mt5.TRADE_ACTION_PENDING,
        "symbol": broker_name,
        "volume": vol,
        "type": mt5.ORDER_TYPE_BUY_LIMIT if p["direction"] == "BUY" else mt5.ORDER_TYPE_SELL_LIMIT,
        "price": entry, "sl": sl, "tp": tp,
        "magic": MAGIC,
        "comment": str(p["zone_id"])[:31],
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_RETURN,
    }
    res = mt5.order_send(req)
    rc = _rc(res)
    side = "خرید" if p["direction"] == "BUY" else "فروش"
    placed = _find_order(broker_name, p["direction"], entry, sl, si.digits)
    if rc in RC_DONE or placed is not None:
        _retry_place.pop(key, None)
        ticket = placed.ticket if placed is not None else getattr(res, "order", "?")
        note = "" if rc in RC_DONE else f" | (کد برگشتی متاتریدر {rc} بود ولی سفارش واقعاً ثبت شده)"
        log(f"🟢 سفارش {side} گذاشته شد | زون {p['zone_id']} | حجم {vol} لات ({vol_msg}) | "
            f"سشن: {sess_name} × {w:g} | ورود {entry} | استاپ {sl} | تارگت {tp} | تیکت {ticket}{note}", base)
        return "ok"
    if res is None or rc in RC_TRANSIENT:
        return _queue_place(base, broker_name, p, _rc_txt(res))
    _retry_place.pop(key, None)
    log(f"❌ سفارش زون {p['zone_id']} رد شد | {_rc_txt(res)}", base)
    return "fail"


def _age_txt(ts):
    """عمر سفارش را به زبان ساده می‌نویسد. زمان ثبت سفارش به وقت سرور است، پس با ساعت سرور
    مقایسه می‌شود (قبلاً با ساعت ویندوز مقایسه می‌شد و عمر را ۳ ساعت کمتر نشان می‌داد)."""
    try:
        now = server_now() or _time.time()
        sec = max(0, int(now - int(ts)))
    except Exception:
        return "نامشخص"
    d, rem = divmod(sec, 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    if d: return f"{d} روز و {h} ساعت"
    if h: return f"{h} ساعت و {m} دقیقه"
    return f"{m} دقیقه"


def cancel_order(base, o, why="طبق قوانین استراتژی دیگر معتبر نیست",
                 next_action="دوباره چیده نمی‌شود (زون دیگر معتبر نیست)", filters="", broker_name=None):
    """لغو سفارش با گزارش مهندسی کامل: مشخصات سفارش، دلیل دقیق، وضعیت بازار و اقدام بعدی.
    خروجی: "ok" (دیگر روی حساب نیست) | "retry" (بازار نماد بسته/قیمت نبود؛ بعداً دوباره) | "fail"
    نتیجه با خواندن دوباره‌ی فهرست سفارش‌ها تأیید می‌شود، نه فقط با کد برگشتی."""
    name = broker_name or o.symbol
    side = "خرید" if o.type in (mt5.ORDER_TYPE_BUY_LIMIT, mt5.ORDER_TYPE_BUY_STOP) else "فروش"
    price_now = ""
    try:
        tk = mt5.symbol_info_tick(name)
        if tk is not None:
            price_now = f" | قیمت فعلی: {tk.bid}"
    except Exception:
        pass

    res = mt5.order_send({"action": mt5.TRADE_ACTION_REMOVE, "order": o.ticket})
    rc = _rc(res)
    alive = _order_alive(o.ticket)
    if rc not in RC_DONE and alive is False:
        try:
            filled = bool(mt5.positions_get(ticket=o.ticket))
        except Exception:
            filled = False
        if filled:
            _retry_cancel.pop(o.ticket, None)
            _gone_tickets.add(o.ticket)
            log(f"⚠️ سفارش زون {o.comment} (تیکت {o.ticket}) قبل از لغو پر شد و حالا پوزیشن باز است "
                f"(استاپ و تارگتش روی خودش است). دلیلی که می‌خواستیم لغو کنیم: {why}", base)
            return "ok"
    if rc in RC_DONE or alive is False:
        _retry_cancel.pop(o.ticket, None)
        _gone_tickets.add(o.ticket)
        lines = [
            f"🗑️ سفارش لغو شد | زون {o.comment} | {side} | تیکت {o.ticket}",
            f"    ├ مشخصات: ورود {o.price_open} | استاپ {o.sl} | تارگت {o.tp} | حجم {o.volume_current} لات",
            f"    ├ عمر سفارش: {_age_txt(o.time_setup)}{price_now}",
            f"    ├ دلیل دقیق: {why}",
        ]
        if filters:
            lines.append(f"    ├ وضعیت فیلترها: {filters}")
        if rc not in RC_DONE:
            lines.append(f"    ├ (کد برگشتی متاتریدر {rc} بود ولی سفارش واقعاً حذف شده)")
        lines.append(f"    └ اقدام بعدی: {next_action}")
        log("\n".join(lines), base)
        return "ok"

    if res is None or rc in RC_TRANSIENT or not symbol_tradeable(name):
        first = o.ticket not in _retry_cancel
        _retry_cancel[o.ticket] = {"base": base, "name": name, "o": o, "why": why,
                                   "nxt": next_action, "filters": filters}
        if first:
            log(f"⏳ لغو سفارش {o.ticket} (زون {o.comment}) فعلاً ممکن نشد | {_rc_txt(res)} — "
                f"بازار این نماد بسته است یا قیمت ندارد؛ هر چند ثانیه دوباره تلاش می‌کنم. "
                f"(دلیل لغو: {why})", base)
        return "retry"

    _retry_cancel.pop(o.ticket, None)
    log(f"⚠️ لغو سفارش {o.ticket} (زون {o.comment}) موفق نبود | {_rc_txt(res)} | "
        f"دلیلی که می‌خواستیم لغو کنیم: {why}", base)
    return "fail"


def refresh_volumes(b, name, orders, filters=""):
    """اگر وزن ریسک سشن عوض شده، سفارش‌های در انتظار با حجم متناسب سشن فعلی دوباره چیده می‌شوند
    (بک‌تست وزن را بر اساس سشنِ لحظه‌ی ورود می‌گیرد). اول سفارش قدیمی لغو می‌شود، بعد جدید گذاشته
    می‌شود؛ اگر لغو ممکن نشد، سفارش جدید هم صبر می‌کند تا دو سفارش برای یک زون روی حساب نباشد."""
    if not (SESSION_REPLACE_ORDERS and USE_SESSION_WEIGHTS) or not orders:
        return
    if not symbol_tradeable(name):
        return   # بازار این نماد بسته است؛ دور بعد (با باز شدن بازار) دوباره بررسی می‌شود
    si_ = mt5.symbol_info(name)
    acc_ = mt5.account_info()
    if si_ is None or acc_ is None:
        return
    w_now, sess_now = current_session_weight()
    risk_amt_ = acc_.equity * (1.0 - RESERVE) * RISK_PER_TRADE * w_now
    for o in orders:
        p = _order_dict(o)
        target, _ = calc_volume(name, si_, p["direction"], p["entry"], p["sl"], risk_amt_, acc_.equity)
        # توجه: در متاتریدر، «سفارش» فیلد volume_current دارد و «پوزیشن» فیلد volume
        cur_vol = float(getattr(o, "volume_current", 0) or 0)
        if target is None or cur_vol <= 0:
            continue
        if abs(target - cur_vol) / cur_vol <= SESSION_REPLACE_TOLERANCE:
            continue
        r = cancel_order(b, o,
                         why=f"وزن ریسک سشن عوض شد → سشن فعلی: {sess_now} (ضریب {w_now:g}) | "
                             f"حجم فعلی {o.volume_current} → حجم درست {target}",
                         next_action="بلافاصله با حجم متناسب سشن جدید دوباره چیده می‌شود",
                         filters=filters, broker_name=name)
        if r == "ok":
            place_pending(b, name, p)
        elif r == "retry":
            _queue_place(b, name, p, "منتظر لغو سفارش قبلیِ همین زون")


_last_note = {}   # آخرین پیام وضعیت هر نماد — برای جلوگیری از تکرار

def sync_all(symbols, reason_txt="بازبینی"):
    """بازپخش استراتژی روی همه‌ی نمادها + سهمیه‌بندی منصفانه‌ی اوردرها:
    دور اول به هر نماد یک اوردر (بهترین زونش)، بعد دور دوم و سوم —
    تا سقف کل (MAX_PENDING_TOTAL). طبق بک‌تست: هر چارت تا ۳، سقف کل ۸."""

    # ۱) خواسته‌های استراتژی برای هر نماد (به ترتیب اولویت خود نماد)
    all_wanted = {}
    notes = {}
    filters_txt = {}
    zone_reasons = {}
    for b, name in symbols.items():
        try:
            st = replay_state(b, name)
        except Exception as e:
            log(f"❌ خطا در بازپخش استراتژی: {e}", b)
            st = None
        if st is None:
            continue
        all_wanted[b] = list(st["pending"]) + list(st.get("armed", []))
        notes[b] = st.get("دلیل_نبود", "") or st.get("فیلتر_توضیح", "")
        filters_txt[b] = st.get("فیلتر_توضیح", "")
        zone_reasons[b] = st.get("دلایل_زون", {})

    # ۲) سهمیه‌بندی منصفانه (طبق نتیجه‌ی بک‌تست «هر چارت ۳ + سقف ۸»):
    # دور اول به هر نماد یک اوردر، بعد دور دوم و سوم — تا سقف کل
    alloc = {}
    total = 0
    for r in range(3):  # حداکثر ۳ اوردر برای هر نماد
        for b in symbols:
            lst = all_wanted.get(b, [])
            if len(lst) > r and total < MAX_PENDING_TOTAL:
                alloc.setdefault(b, {})[str(lst[r]["zone_id"])] = lst[r]
                total += 1

    # ۳) همگام‌سازی هر نماد با سهمیه‌اش
    # دستورهای مانده از دور قبل دیگر معتبر نیستند؛ همین همگام‌سازی همه را از نو حساب می‌کند
    _retry_cancel.clear()
    _retry_place.clear()
    _gone_tickets.clear()
    my_positions = [p for p in (mt5.positions_get() or ()) if p.magic == MAGIC]
    for b, name in symbols.items():
        desired = alloc.get(b, {})
        si_ = mt5.symbol_info(name)
        digits = si_.digits if si_ is not None else 5
        orders = _my_orders(name)

        # تطبیق سفارش‌های روی حساب با خواسته‌ها: اول با شناسه‌ی زون (کامنت سفارش)، بعد با
        # جهت + قیمت ورود + استاپ (مثلاً سفارشی که با شناسه‌ی قدیمی گذاشته شده). هر سفارش فقط
        # به یک زون می‌خورد؛ سفارش دوم با همان شناسه «تکراری» است و لغو می‌شود.
        matched = {}
        taken = set()
        for zid in desired:
            for o in orders:
                if o.ticket not in taken and o.comment == zid:
                    matched[zid] = o
                    taken.add(o.ticket)
                    break
        for zid, p in desired.items():
            if zid in matched:
                continue
            e_, s_ = round(p["entry"], digits), round(p["sl"], digits)
            for o in orders:
                if o.ticket not in taken and _same_order(o, p["direction"], e_, s_, digits):
                    matched[zid] = o
                    taken.add(o.ticket)
                    break

        for o in orders:
            if o.ticket in taken:
                continue
            cm = o.comment
            # دلیل دقیق لغو: اول از موتور استراتژی، وگرنه سهمیه/سقف
            zr = zone_reasons.get(b, {}).get(str(cm), "")
            still_wanted = any(str(p["zone_id"]) == str(cm) for p in all_wanted.get(b, []))
            twin = any(k.ticket != o.ticket and k.type == o.type and abs(k.price_open - o.price_open) <= 0.6 * 10 ** (-int(digits))
                       and abs(k.sl - o.sl) <= 0.6 * 10 ** (-int(digits)) for k in matched.values())
            if cm in matched or twin:
                why = "سفارش تکراری — برای همین زون سفارش دیگری روی حساب هست"
                nxt = "فقط یک سفارش برای هر زون نگه داشته می‌شود"
            elif zr:
                why, nxt = zr, "دوباره چیده نمی‌شود (زون طبق قوانین استراتژی باطل شد)"
            elif still_wanted:
                why = f"زون معتبر است ولی سهمیه‌ی اوردر پر شد (سقف {MAX_PENDING_TOTAL} اوردر در کل حساب)"
                nxt = "به‌محض آزاد شدن سهمیه، دوباره چیده می‌شود"
            else:
                why = f"دیگر در فهرست زون‌های معتبر نیست — {notes.get(b, 'شرایط بازار عوض شد')}"
                nxt = "اگر شرایط دوباره سبز شود و زون معتبر بماند، دوباره بررسی می‌شود"
            cancel_order(b, o, why=why, next_action=nxt,
                         filters=filters_txt.get(b, ""), broker_name=name)

        # سفارش زونی که سطح‌هایش عوض شده (مثلاً زون قدیمیِ هم‌پوشان از پنجره‌ی ۲۰۰۰ کندلی بیرون
        # افتاد و محدوده‌ی این زون پهن‌تر شد) با سطح‌های جدید دوباره چیده می‌شود
        tol = 0.6 * 10 ** (-int(digits))
        for zid, o in list(matched.items()):
            p = desired[zid]
            e_, s_, t_ = round(p["entry"], digits), round(p["sl"], digits), round(p["tp"], digits)
            if _same_order(o, p["direction"], e_, s_, digits) and abs(o.tp - t_) <= tol:
                continue
            r = cancel_order(b, o, why=f"سطح‌های زون عوض شد (ورود {o.price_open}→{e_} | "
                                      f"استاپ {o.sl}→{s_} | تارگت {o.tp}→{t_})",
                             next_action="بلافاصله با سطح‌های جدید دوباره چیده می‌شود",
                             filters=filters_txt.get(b, ""), broker_name=name)
            if r in ("ok", "retry"):
                matched.pop(zid)

        # اگر وزن سشن عوض شده باشد، سفارش موجود با حجم متناسبِ سشن جدید دوباره چیده می‌شود
        refresh_volumes(b, name, list(matched.values()), filters=filters_txt.get(b, ""))

        # تا وقتی لغوِ سفارشی از همین نماد مانده (بازارش بسته بود)، سفارش تازه گذاشته نمی‌شود
        # (وگرنه چند لحظه سفارش قدیمی و جدید با هم روی حساب می‌مانند)
        blocked = any(it["name"] == name for it in _retry_cancel.values())
        placed_something = False
        for zid, p in desired.items():
            if zid in matched:
                continue
            if len(my_positions) >= MAX_OPEN_TOTAL:
                log(f"⏸️ زون {zid}: سقف {MAX_OPEN_TOTAL} ترید باز حساب پر است — فعلاً سفارش جدید نمی‌گذارم.", b)
                continue
            if blocked:
                _queue_place(b, name, p, "اول باید سفارش قبلیِ این نماد لغو شود")
                continue
            if place_pending(b, name, p) == "ok":
                placed_something = True

        # گزارش وضعیت هر چارت — فقط وقتی وضعیت نسبت به دفعه‌ی قبل عوض شده باشد
        note = notes.get(b, "")
        n_open_sym = len([p for p in my_positions if p.symbol == name])
        waiting = any(it["name"] == name for it in list(_retry_cancel.values()) + list(_retry_place.values()))
        if waiting:
            msg = "⏳ تغییرات این نماد منتظر باز شدن بازارش است (هر چند ثانیه دوباره تلاش می‌شود)"
        elif not all_wanted.get(b):
            if note == "فیلترها سبزند":
                why = "فیلترها سبزند ولی زون معتبرِ لمس‌نشده‌ای نزدیک قیمت نیست"
            else:
                why = note
            msg = f"⛔ معامله نمی‌کند | دلیل: {why} | اوردر فعال: {len(matched)} | ترید باز: {n_open_sym}"
        elif not desired:
            msg = (f"⏸️ زون آماده دارد ولی سهمیه‌ی اوردر (سقف {MAX_PENDING_TOTAL} کل حساب) پر است | "
                   f"زون‌های واجد شرایط: {len(all_wanted.get(b, []))}")
        elif not placed_something:
            msg = f"✔️ بدون تغییر | اوردر فعال: {len(matched)} | ترید باز: {n_open_sym} | وضعیت فیلترها: {note}"
        else:
            msg = None

        if msg is not None:
            if _last_note.get(b) != msg:
                _last_note[b] = msg
                log(msg, b)
            else:
                console(f"{b} | (بدون تغییر) {msg}")   # فقط در CMD، نه در بله

    log(f"همگام‌سازی کامل شد ({reason_txt}) | اوردرهای تخصیص‌یافته: {total} از سقف {MAX_PENDING_TOTAL}")
    # نگهبان (watchdog.py) از روی این فایل می‌فهمد همگام‌سازی‌ها به‌موقع انجام می‌شوند یا نه
    try:
        with open(os.path.join(LOG_DIR, "last_sync.txt"), "w", encoding="utf-8") as f:
            f.write(dt.datetime.now().isoformat(timespec="seconds"))
    except Exception:
        pass


def process_retries():
    """دستورهای مانده (لغو/ثبت سفارش در نمادی که بازارش بسته بود) را دوباره امتحان می‌کند.
    خروجی True یعنی هنوز دستوری مانده و حلقه‌ی اصلی باید زودتر برگردد."""
    if not _retry_cancel and not _retry_place:
        return False
    for tk, it in list(_retry_cancel.items()):
        alive = _order_alive(tk)
        if alive is False:          # دیگر روی حساب نیست (دستور قبلی دیر اثر کرد یا سفارش پر شد)
            _retry_cancel.pop(tk, None)
            continue
        if not symbol_tradeable(it["name"]):
            continue
        cancel_order(it["base"], it["o"], why=it["why"], next_action=it["nxt"],
                     filters=it["filters"], broker_name=it["name"])
    blocked = {it["name"] for it in _retry_cancel.values()}
    n_open = len([p for p in (mt5.positions_get() or ()) if p.magic == MAGIC])
    for key, it in list(_retry_place.items()):
        if it["name"] in blocked or n_open >= MAX_OPEN_TOTAL or not symbol_tradeable(it["name"]):
            continue
        place_pending(it["base"], it["name"], it["p"])
    return bool(_retry_cancel or _retry_place)


_last_sess = [None]


def maybe_session_refresh(symbols):
    """وقتی سشن عوض می‌شود (نه سر هر کندل ۴ساعته)، حجم سفارش‌های در انتظار بازبینی می‌شود.
    قبلاً این کار فقط موقع همگام‌سازی ۴ساعته انجام می‌شد: هم حجم تا ۳ ساعت با سشن واقعی ورود
    نمی‌خواند، هم همه‌ی سفارش‌ها ساعت ۰۰ (رول‌اوور، بدون قیمت) لغو و دوباره چیده می‌شدند."""
    if not (SESSION_REPLACE_ORDERS and USE_SESSION_WEIGHTS):
        return
    w, sess = current_session_weight()
    if sess == _last_sess[0]:
        return
    first = _last_sess[0] is None
    _last_sess[0] = sess
    if first:
        return
    log(f"🕐 سشن عوض شد → {sess} (ضریب ریسک {w:g}) — حجم سفارش‌های در انتظار بازبینی می‌شود.", bale=False)
    for b, name in symbols.items():
        refresh_volumes(b, name, _my_orders(name))


# ---------------- سلامت‌سنجی و اعلام وضعیت ----------------
def console(msg):
    """چاپ فقط در CMD (بدون نوشتن در فایل — که فایل لاگ شلوغ نشود)."""
    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{stamp}] {msg}", flush=True)


_market_closed = [False]

def market_is_open(symbols):
    """تشخیص باز/بسته بودن بازار از روی تازگی آخرین تیک قیمت.
    اگر برای همه‌ی نمادها بیش از ۵ دقیقه تیک نیامده باشد، بازار تعطیل است.
    (زمان تیک به وقت سرور است؛ قبلاً با ساعت ویندوز مقایسه می‌شد و تا ~۳ ساعت بعد از بسته شدن
    بازارِ جمعه، بازار را باز حساب می‌کرد.)"""
    now = _time.time() + (_srv_offset[0] or 0)
    fresh = 0
    checked = 0
    for name in symbols.values():
        tk = mt5.symbol_info_tick(name)
        if tk is None or tk.time == 0:
            continue
        checked += 1
        if now - tk.time < 300:
            fresh += 1
    if checked == 0:
        return True   # نتوانستیم بسنجیم → مانع کار نمی‌شویم
    return fresh > 0


def health_check():
    """همه‌ی پیش‌نیازها را می‌سنجد؛ لیست مشکلات را برمی‌گرداند (خالی = همه‌چیز سالم)."""
    ti = mt5.terminal_info()
    if ti is None:
        return None  # اتصال به خود متاتریدر قطع است — ensure_connected حلش می‌کند
    problems = []
    if not ti.connected:
        problems.append("متاتریدر به سرور بروکر وصل نیست (اینترنت یا سرور بروکر قطع است)!")
    if not ti.trade_allowed:
        problems.append("دکمه‌ی Algo Trading خاموش شده! تا روشنش نکنی هیچ سفارشی ارسال نمی‌شود!")
    if mt5.account_info() is None:
        problems.append("اطلاعات حساب در دسترس نیست — لاگین حساب قطع شده؟")
    return problems


_status_cycle = 0

def report_status():
    """هر ۳۰ ثانیه در CMD اعلام سلامت می‌کند؛ هر ~۵ دقیقه یک بار هم در فایل لاگ."""
    global _status_cycle
    try:
        n_orders = len([o for o in (mt5.orders_get() or ()) if o.magic == MAGIC])
        n_open = len([p for p in (mt5.positions_get() or ()) if p.magic == MAGIC])
        msg = (f"🟢 ربات در حال اجراست | همه‌چیز سالم است | "
               f"اوردرهای در انتظار: {n_orders} | تریدهای باز: {n_open}")
        console(msg)
        _status_cycle += 1
        if _status_cycle >= 10:
            _status_cycle = 0
            log(msg)
    except Exception:
        pass


# ---------------- گزارش روزانه‌ی درصدی ----------------
_daily_file = os.path.join(LOG_DIR, "last_daily.txt")

def _pct_txt(pct):
    if pct > 0.005:
        return f"{pct:+.2f}٪ در سود"
    if pct < -0.005:
        return f"{pct:+.2f}٪ در ضرر"
    return "سربه‌سر (0.0٪)"


def daily_report(symbols_rev):
    """وضعیت همه‌ی تریدهای باز به «درصدِ حساب» + برایند کل — در یک پیام."""
    acc = mt5.account_info()
    if acc is None or acc.balance <= 0:
        return
    poss = [p for p in (mt5.positions_get() or ()) if p.magic == MAGIC]
    lines = ["📊 گزارش روزانه‌ی حساب"]

    if poss:
        for p in poss:
            b = symbols_rev.get(p.symbol, p.symbol)
            side = "خرید" if p.type == mt5.POSITION_TYPE_BUY else "فروش"
            pct = (p.profit + p.swap) / acc.balance * 100.0
            lines.append(f"{b} ({side}): {_pct_txt(pct)}")
    else:
        lines.append("هیچ ترید بازی نیست.")

    total_open = (acc.equity - acc.balance) / acc.balance * 100.0
    lines.append(f"— برایند تریدهای باز: {_pct_txt(total_open)}")

    # معاملات بسته‌شده‌ی ۲۴ ساعت اخیر
    try:
        frm = dt.datetime.now() - dt.timedelta(days=1)
        deals = mt5.history_deals_get(frm, dt.datetime.now() + dt.timedelta(days=1)) or ()
        outs = [d for d in deals if d.magic == MAGIC and d.entry == mt5.DEAL_ENTRY_OUT]
        if outs:
            pnl = sum(d.profit + d.swap + d.commission for d in outs)
            lines.append(f"— بسته‌شده‌های ۲۴ ساعت اخیر: {len(outs)} معامله ({_pct_txt(pnl / acc.balance * 100.0)})")
    except Exception:
        pass

    n_orders = len([o for o in (mt5.orders_get() or ()) if o.magic == MAGIC])
    lines.append(f"— اوردرهای در انتظار: {n_orders}")
    lines.append(f"— بالانس: {acc.balance:,.0f} | اکویتی: {acc.equity:,.0f} {acc.currency}")
    log("\n".join(lines))


def _marker_differs(fname, key):
    """جلوگیری از ارسال تکراری گزارش‌ها (حتی بعد از ری‌استارت)."""
    path = os.path.join(LOG_DIR, fname)
    try:
        with open(path, encoding="utf-8") as f:
            if f.read().strip() == key:
                return False
    except Exception:
        pass
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(key)
    except Exception:
        pass
    return True


def period_report(symbols_rev, since, title):
    """همه‌ی معاملات بسته‌شده‌ی یک دوره در یک پیام: نماد، تاریخ، خرید/فروش،
    نتیجه (حد سود/حد ضرر)، درصد سود/ضرر — و در آخر برایند دوره و کل حساب."""
    acc = mt5.account_info()
    if acc is None or acc.balance <= 0:
        return
    try:
        deals = mt5.history_deals_get(since, dt.datetime.now() + dt.timedelta(days=1)) or ()
    except Exception:
        deals = ()
    outs = sorted([d for d in deals if d.magic == MAGIC and d.entry == mt5.DEAL_ENTRY_OUT],
                  key=lambda d: d.time)

    lines = [title]
    wins = losses = 0
    total_pct = 0.0
    best = worst = None
    for d in outs:
        b = symbols_rev.get(d.symbol, d.symbol)
        when = dt.datetime.fromtimestamp(d.time).strftime("%m/%d")
        # معامله‌ی بستن، برعکسِ جهت پوزیشن است
        side = "فروش" if d.type == mt5.DEAL_TYPE_BUY else "خرید"
        if d.reason == mt5.DEAL_REASON_TP:
            res = "حد سود ✅"
        elif d.reason == mt5.DEAL_REASON_SL:
            res = "حد ضرر ❌"
        else:
            res = "بسته شد"
        pct = (d.profit + d.swap + d.commission) / acc.balance * 100.0
        total_pct += pct
        if pct > 0: wins += 1
        else: losses += 1
        if best is None or pct > best[1]: best = (b, pct)
        if worst is None or pct < worst[1]: worst = (b, pct)
        lines.append(f"{when} | {b} | {side} | {res} | {pct:+.2f}٪")

    if not outs:
        lines.append("در این دوره هیچ معامله‌ای بسته نشد.")
    else:
        lines.append(f"— تعداد: {len(outs)} | برد: {wins} | باخت: {losses}")
        if best:
            lines.append(f"— بهترین: {best[0]} ({best[1]:+.2f}٪) | بدترین: {worst[0]} ({worst[1]:+.2f}٪)")
    lines.append(f"— برایند دوره: {_pct_txt(total_pct)}")
    floating = (acc.equity - acc.balance) / acc.balance * 100.0
    lines.append(f"— تریدهای بازِ فعلی: {_pct_txt(floating)}")
    total_acc = (acc.equity - START_BALANCE) / START_BALANCE * 100.0
    lines.append(f"— کل حساب از شروع: {_pct_txt(total_acc)} (اکویتی {acc.equity:,.0f} {acc.currency})")

    text = "\n".join(lines)
    log(text, bale=False)  # در فایل و CMD کامل ثبت شود
    # ارسال به بله؛ اگر خیلی بلند بود چند تکه می‌شود که قیچی نشود
    chunk = []
    size = 0
    for ln in lines:
        if size + len(ln) > 3000 and chunk:
            bale_send("\n".join(chunk))
            chunk, size = [], 0
        chunk.append(ln)
        size += len(ln) + 1
    if chunk:
        bale_send("\n".join(chunk))


def maybe_periodic_reports(symbols_rev):
    """گزارش هفتگی (شنبه‌ها) و ماهانه (روز اول ماه)، رأس همان ساعت گزارش روزانه."""
    now = dt.datetime.now()
    if now.hour != DAILY_REPORT_HOUR:
        return
    if now.weekday() == 5:  # شنبه — هفته‌ی معاملاتی تمام شده
        if _marker_differs("last_weekly.txt", now.strftime("%G-W%V")):
            period_report(symbols_rev, now - dt.timedelta(days=7), "🗓 گزارش هفتگی معاملات")
    if now.day == 1:
        if _marker_differs("last_monthly.txt", now.strftime("%Y-%m")):
            prev_month_start = (now.replace(day=1) - dt.timedelta(days=1)).replace(
                day=1, hour=0, minute=0, second=0, microsecond=0)
            period_report(symbols_rev, prev_month_start, "📅 گزارش ماهانه معاملات")


def maybe_daily_report(symbols_rev):
    """هر روز رأس ساعت تعیین‌شده، فقط یک بار (حتی بعد از ری‌استارت)."""
    now = dt.datetime.now()
    if now.hour != DAILY_REPORT_HOUR:
        return
    today = now.strftime("%Y-%m-%d")
    try:
        with open(_daily_file, encoding="utf-8") as f:
            if f.read().strip() == today:
                return
    except Exception:
        pass
    try:
        with open(_daily_file, "w", encoding="utf-8") as f:
            f.write(today)
    except Exception:
        pass
    daily_report(symbols_rev)


# ---------------- سقف تریدهای باز: پر شد → اوردرها موقتاً جمع می‌شوند ----------------
_cap_active = False

def enforce_open_cap(symbols_rev):
    """اگر تعداد تریدهای باز به سقف رسید، همه‌ی اوردرهای در انتظار جمع می‌شوند؛
    وقتی دوباره زیر سقف آمد، اعلام می‌کند تا اوردرها دوباره چیده شوند."""
    global _cap_active
    my_open = [p for p in (mt5.positions_get() or ()) if p.magic == MAGIC]
    my_orders = [o for o in (mt5.orders_get() or ()) if o.magic == MAGIC]

    if len(my_open) >= MAX_OPEN_TOTAL:
        if my_orders:
            log(f"🚧 سقف {MAX_OPEN_TOTAL} ترید باز پر شد — {len(my_orders)} اوردر در انتظار موقتاً جمع می‌شود.")
            for o in my_orders:
                cancel_order(symbols_rev.get(o.symbol, o.symbol), o,
                             why=f"سقف {MAX_OPEN_TOTAL} تریدِ بازِ هم‌زمان پر شد — برای کنترل ریسک کل حساب",
                             next_action=f"به‌محض اینکه تعداد تریدهای باز زیر {MAX_OPEN_TOTAL} برگردد، دوباره چیده می‌شود")
        _cap_active = True
        return "capped"

    if _cap_active:
        _cap_active = False
        log(f"✅ تعداد تریدهای باز زیر {MAX_OPEN_TOTAL} برگشت — اوردرها دوباره چیده می‌شوند.")
        return "resync"
    return "ok"


# ---------------- سیو سود در 2R ----------------
_managed_file = os.path.join(LOG_DIR, "managed_tickets.txt")

def _load_managed():
    try:
        with open(_managed_file, encoding="utf-8") as f:
            return set(int(x) for x in f.read().split() if x.strip().isdigit())
    except Exception:
        return set()

_managed = _load_managed()

def _mark_managed(ticket):
    _managed.add(int(ticket))
    try:
        with open(_managed_file, "a", encoding="utf-8") as f:
            f.write(f"{ticket}\n")
    except Exception:
        pass


_init_vol = {}         # ticket → حجم اولیه‌ی پوزیشن (از معامله‌ی ورود در تاریخچه)
_partial_fail_n = {}   # ticket → تعداد تلاش ناموفق (برای اینکه لاگ هر ۳۰ ثانیه تکرار نشود)


def initial_volume(p):
    """حجم اولیه‌ی پوزیشن از معامله‌ی ورودش (بعد از ری‌استارت هم درست است)."""
    v = _init_vol.get(p.ticket)
    if v:
        return v
    try:
        deals = mt5.history_deals_get(position=p.ticket) or ()
        ins = [d.volume for d in deals if d.entry == mt5.DEAL_ENTRY_IN]
        if ins:
            v = float(sum(ins))
    except Exception:
        v = None
    if v:
        _init_vol[p.ticket] = v
    return v


def _position_volume(ticket):
    """حجم فعلی پوزیشن | 0 = بسته شده | None = معلوم نشد"""
    try:
        r = mt5.positions_get(ticket=ticket)
    except Exception:
        return None
    if r is None:
        return None
    return float(r[0].volume) if len(r) else 0.0


def manage_positions(symbols_rev):
    """سیو سود: هر پوزیشنی که سودش به ۲ برابر ریسک رسید، نصف حجمش نقد می‌شود — فقط یک بار.

    باگ قبلی: متاتریدر چند روز برای دستورهای انجام‌شده کد 0 برگرداند؛ ربات فکر کرد نصف کردن
    انجام نشده و هر ۳۰ ثانیه دوباره نصف کرد (۳٫۶۶ لات → ... → ۰٫۰۱ لات). حالا:
      ۱) اگر حجم پوزیشن از حجم ورودش کمتر است، یعنی قبلاً نصف شده → دیگر دست نمی‌زنیم.
      ۲) نتیجه‌ی دستور با خواندن دوباره‌ی حجم پوزیشن تأیید می‌شود، نه فقط با کد برگشتی."""
    if not MANAGE_PARTIAL:
        return
    for p in (mt5.positions_get() or ()):
        if p.magic != MAGIC or p.ticket in _managed or p.sl <= 0:
            continue
        risk_dist = abs(p.price_open - p.sl)
        if risk_dist <= 0:
            continue
        tick = mt5.symbol_info_tick(p.symbol)
        si = mt5.symbol_info(p.symbol)
        if tick is None or si is None:
            continue
        base = symbols_rev.get(p.symbol, p.symbol)
        step = si.volume_step or 0.01

        # قفل «فقط یک بار»: حجم فعلی کمتر از حجم ورود = قبلاً بخشی بسته شده
        init_v = initial_volume(p)
        if init_v and p.volume < init_v - step / 2:
            _mark_managed(p.ticket)
            log(f"ℹ️ سیو سود {p.comment}: حجم این پوزیشن قبلاً کم شده ({init_v:g} → {p.volume:g} لات) — "
                f"دوباره نصف نمی‌شود.", base, bale=False)
            continue

        if p.type == mt5.POSITION_TYPE_BUY:
            reached = tick.bid >= p.price_open + MANAGE_TRIGGER_R * risk_dist
            close_type, close_price = mt5.ORDER_TYPE_SELL, tick.bid
        else:
            reached = tick.ask <= p.price_open - MANAGE_TRIGGER_R * risk_dist
            close_type, close_price = mt5.ORDER_TYPE_BUY, tick.ask
        if not reached:
            continue

        half = math.floor(p.volume * PARTIAL_FRAC / step) * step
        if half < si.volume_min or (p.volume - half) < si.volume_min:
            _mark_managed(p.ticket)
            log(f"⚠️ سیو سود {p.comment}: حجم برای نصف کردن کافی نیست ({p.volume}) — کامل می‌ماند.", base)
            continue

        req = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": p.symbol,
            "volume": round(half, 8),
            "type": close_type,
            "position": p.ticket,
            "price": close_price,
            "deviation": 50,
            "magic": MAGIC,
            "comment": "TP2-partial",
        }
        # حالت پرکردن را از نماد می‌گیریم؛ اگر رد شد، حالت‌های دیگر را هم امتحان می‌کنیم
        res = None
        tried = []
        for fm in (pick_filling(si, True), mt5.ORDER_FILLING_FOK,
                   mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_RETURN):
            if fm in tried:
                continue
            tried.append(fm)
            req["type_filling"] = fm
            res = mt5.order_send(req)
            if res is not None and res.retcode == mt5.TRADE_RETCODE_DONE:
                break
            if res is not None and res.retcode != 10030:  # فقط خطای «حالت پرکردن» ارزش تلاش دوباره دارد
                break
            if _position_volume(p.ticket) not in (None, p.volume):
                break                                    # انجام شده (هر کدی که برگشته باشد)

        rc = _rc(res)
        vol_now = _position_volume(p.ticket)
        done = rc in RC_DONE or (vol_now is not None and vol_now < p.volume - step / 2)
        if done:
            _mark_managed(p.ticket)
            _partial_fail_n.pop(p.ticket, None)
            note = "" if rc in RC_DONE else f" (کد برگشتی متاتریدر {rc} بود ولی حجم پوزیشن واقعاً کم شده)"
            log(f"💰 سیو سود انجام شد! زون {p.comment} | سود به ۲ برابر ریسک رسید — "
                f"{round(half, 2)} لات از {p.volume} لات نقد شد؛ بقیه به سمت تارگت ادامه می‌دهد.{note}", base)
        else:
            n = _partial_fail_n.get(p.ticket, 0) + 1
            _partial_fail_n[p.ticket] = n
            if n == 1 or n % 20 == 0:
                log(f"⚠️ سیو سود {p.comment} انجام نشد | {_rc_txt(res)} — دور بعد دوباره تلاش می‌شود "
                    f"(تلاش {n}).", base)


# ---------------- رصد پر شدن و بسته شدن معاملات ----------------
_prev_positions = {}

def track_positions(symbols_rev):
    """پر شدن سفارش‌ها و بسته شدن پوزیشن‌ها را کشف و با دلیل لاگ می‌کند."""
    global _prev_positions
    cur = {p.ticket: p for p in (mt5.positions_get() or ()) if p.magic == MAGIC}

    # پوزیشن‌های تازه = سفارشی پر شده
    for tk, p in cur.items():
        if tk not in _prev_positions:
            base = symbols_rev.get(p.symbol, p.symbol)
            side = "خرید" if p.type == mt5.POSITION_TYPE_BUY else "فروش"
            log(f"🎯 سفارش پر شد! پوزیشن {side} باز شد | زون {p.comment} | حجم {p.volume} لات | "
                f"قیمت ورود {p.price_open} | استاپ {p.sl} | تارگت {p.tp}", base)

    # پوزیشن‌های حذف‌شده = معامله بسته شده
    for tk, p in _prev_positions.items():
        if tk not in cur:
            base = symbols_rev.get(p.symbol, p.symbol)
            acc = mt5.account_info()
            bal = acc.balance if (acc and acc.balance > 0) else START_BALANCE
            profit_txt, why = "", "بسته شد"
            try:
                frm = dt.datetime.now() - dt.timedelta(days=7)
                deals = mt5.history_deals_get(frm, dt.datetime.now() + dt.timedelta(days=1), position=tk)
                if deals:
                    outs = [d for d in deals if d.entry == mt5.DEAL_ENTRY_OUT]
                    profit = sum(d.profit + d.swap + d.commission for d in outs)
                    profit_txt = f" | نتیجه‌ی این معامله: {_pct_txt(profit / bal * 100.0)}"
                    if outs:
                        r = outs[-1].reason
                        if r == mt5.DEAL_REASON_SL: why = "حد ضرر خورد"
                        elif r == mt5.DEAL_REASON_TP: why = "حد سود خورد ✨"
            except Exception:
                pass
            # برایند کل حساب از شروع + برایند تریدهای بازِ فعلی
            total_txt = ""
            if acc:
                total = (acc.equity - START_BALANCE) / START_BALANCE * 100.0
                floating = (acc.equity - acc.balance) / bal * 100.0
                total_txt = (f" | برایند کل حساب: {_pct_txt(total)}"
                             f" | تریدهای باز: {_pct_txt(floating)}")
            log(f"🏁 معامله بسته شد ({why}) | زون {p.comment}{profit_txt}{total_txt}", base)

    _prev_positions = cur


# ---------------- فقط یک ربات هم‌زمان + فایل‌های نگهبان ----------------
PID_FILE = os.path.join(LOG_DIR, "robot.pid")
STOP_FLAG = os.path.join(LOG_DIR, "robot_stopped.flag")   # = عمداً خاموش شده؛ نگهبان روشنش نکند
_mutex = []


def single_instance():
    """دو ربات هم‌زمان روی یک حساب، سفارش‌های هم را لغو و تکرار می‌کنند. با یک Mutex ویندوزی
    جلوی اجرای نسخه‌ی دوم گرفته می‌شود."""
    if os.name != "nt":
        return True
    try:
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateMutexW.restype = wintypes.HANDLE
        k32.CreateMutexW.argtypes = (wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
        for scope in ("Global", "Local"):
            h = k32.CreateMutexW(None, False, f"{scope}\\ZoneRobot_{MAGIC}")
            if h:
                if ctypes.get_last_error() == 183:      # ERROR_ALREADY_EXISTS
                    return False
                _mutex.append(h)                   # تا آخر اجرا باز بماند
                return True
    except Exception:
        pass
    return True


def _write_pid():
    try:
        with open(PID_FILE, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
    except Exception:
        pass
    try:
        if os.path.exists(STOP_FLAG):
            os.remove(STOP_FLAG)
    except Exception:
        pass


def report_previous_exit():
    """اگر اجرای قبلی ربات بی‌خبر بسته شده (بدون ثبت دلیل) و نگهبان هم هنوز گزارشش نکرده،
    دلیل احتمالی از رویدادهای ویندوز پیدا و در لاگ و بله گزارش می‌شود."""
    try:
        with open(EXIT_FILE, encoding="utf-8") as f:
            ex = json.load(f)
    except Exception:
        return
    if not ex.get("running"):
        return                       # دلیل قبلاً ثبت و گزارش شده (کرش، بستن پنجره، توقف دستی...)
    try:
        import watchdog as _wd
        since = _wd.last_heartbeat_ts() or (_time.time() - 3600)
        if _wd.already_reported(since):
            return
        reasons = _wd.diagnose(since)
        _wd.mark_reported(since)
    except Exception as e:
        reasons = [f"(بررسی دلیل ممکن نشد: {e})"]
        since = None
    when = f" (آخرین علامت حیات: {dt.datetime.fromtimestamp(since):%Y-%m-%d %H:%M})" if since else ""
    log("🔎 اجرای قبلی ربات بی‌خبر بسته شده بود" + when + ". دلیل احتمالی:\n- " + "\n- ".join(reasons))


def _mark_stopped():
    try:
        with open(STOP_FLAG, "w", encoding="utf-8") as f:
            f.write(dt.datetime.now().isoformat(timespec="seconds"))
    except Exception:
        pass


# ---------------- حلقه‌ی اصلی ----------------
def main():
    if not single_instance():
        print("⛔ یک ربات دیگر همین الان در حال اجراست — این یکی بالا نمی‌آید (دو ربات روی یک حساب = سفارش تکراری).")
        return EXIT_NO_RESTART
    _write_pid()
    report_previous_exit()
    note_start()
    sys.excepthook = _excepthook
    atexit.register(_on_exit)
    _install_console_handler()
    if _crash_file is not None:
        try:
            _crash_file.write(f"\n=== شروع ربات {dt.datetime.now():%Y-%m-%d %H:%M:%S} | پروسه {os.getpid()} ===\n")
            _crash_file.flush()
        except Exception:
            pass
    log("========== شروع ربات (نسخه ۳ — دمو) ==========", bale=False)
    log(f"سبد انتخابی ({len(BASKET)} نماد): {', '.join(BASKET)} — ربات فقط روی همین‌ها کار می‌کند.", bale=False)

    # سبد ربات و سبد بک‌تست باید یکی باشند، وگرنه ربات چیزی معامله می‌کند که
    # بک‌تست نشده و هر مقایسه‌ای بی‌معنی می‌شود. همان اول کار چک می‌شود.
    bt_basket = [s for s in getattr(rb, "LIVE_BASKET_ORDER", BASKET)
                 if s not in getattr(rb, "LIVE_EXCLUDE_SYMBOLS", [])]
    if list(bt_basket) != list(BASKET):
        only_live = [s for s in BASKET if s not in bt_basket]
        only_bt = [s for s in bt_basket if s not in BASKET]
        log("🛑 سبد ربات با سبد بک‌تست یکی نیست — ربات بالا نمی‌آید.", bale=True)
        if only_live:
            log(f"   فقط در ربات: {', '.join(only_live)}", bale=True)
        if only_bt:
            log(f"   فقط در بک‌تست: {', '.join(only_bt)}", bale=True)
        if not only_live and not only_bt:
            log("   نمادها یکی‌اند ولی ترتیبشان فرق دارد — ترتیب روی سهمیه‌بندی اثر دارد.", bale=True)
        log("   BASKET در live_trader.py و LIVE_BASKET_ORDER در run_backtest.py را یکی کن.", bale=True)
        bale_flush()
        return EXIT_NO_RESTART
    acc = connect_with_retry(bale_notify=False)

    symbols = {}
    for b in BASKET:
        name = resolve_symbol(b)
        if name is None:
            log("⚠️ این نماد نزد بروکر پیدا نشد و کنار گذاشته شد!", b)
        else:
            symbols[b] = name
            if name != b:
                log(f"اسم نماد نزد بروکر: {name}", b, bale=False)
    symbols_rev = {v: k for k, v in symbols.items()}
    _symbols_live.clear()
    _symbols_live.update(symbols)
    log(f"آماده | {len(symbols)} نماد فعال | ریسک هر معامله {RISK_PER_TRADE*100:.1f}٪ | "
        f"حد سود {RR:g} برابر ریسک | ورود {abs(ENTRY_OFF)*100:.0f}٪ داخل زون | سقف {MAX_OPEN_TOTAL} پوزیشن", bale=False)

    # پیام راه‌اندازی — با محافظ ضد اسپم: اگر ربات پشت‌سرهم ری‌استارت شود (کرش)،
    # به‌جای پیام کامل، فقط یک هشدار کوتاه و حداکثر هر ۳۰ دقیقه یک بار می‌رود
    startup_file = os.path.join(LOG_DIR, "last_startup.txt")
    since = None
    try:
        with open(startup_file, encoding="utf-8") as f:
            since = (dt.datetime.now() - dt.datetime.fromisoformat(f.read().strip())).total_seconds()
    except Exception:
        pass
    try:
        with open(startup_file, "w", encoding="utf-8") as f:
            f.write(dt.datetime.now().isoformat())
    except Exception:
        pass

    if since is not None and since < 600:
        log(f"⚠️ ربات دوباره راه‌اندازی شد ({int(since)} ثانیه بعد از اجرای قبلی) — احتمال کرش! لاگ را چک کن.",
            bale=(since > 1800))
    else:
        bale_send(
            "🤖 ربات روشن شد\n"
            f"حساب: {acc.login} ({acc.server}) | {'دمو' if acc.trade_mode == mt5.ACCOUNT_TRADE_MODE_DEMO else 'واقعی'}\n"
            f"بالانس: {acc.balance:,.0f} | اکویتی: {acc.equity:,.0f} {acc.currency}\n"
            f"سبد: {len(symbols)} نماد ({', '.join(symbols)})\n"
            f"ریسک {RISK_PER_TRADE*100:.1f}٪ | حد سود {RR:g}R | ورود {abs(ENTRY_OFF)*100:.0f}٪ زون | "
            f"سقف: هر چارت ۳، کل {MAX_OPEN_TOTAL}"
        )

    last_bar = {b: None for b in symbols}

    sync_all(symbols, "شروع ربات")
    for b, name in symbols.items():
        try:
            bar = mt5.copy_rates_from_pos(name, mt5.TIMEFRAME_H4, 1, 1)
            if bar is not None and len(bar):
                last_bar[b] = int(bar[0]["time"])
        except Exception as e:
            log(f"❌ خطا در بررسی اولیه: {e}", b)

    log("در حال کار... با هر کندل ۴ ساعته‌ی جدید همه‌چیز به‌روز می‌شود. (توقف: Ctrl+C)")
    _last_problems = [set()]
    while True:
        try:
            ensure_connected()

            # سلامت‌سنجی هر دور: مشکل جدید → داد بلند (لاگ + بله)؛ مشکل تکراری → فقط CMD
            problems = health_check()
            if problems:
                pset = set(problems)
                if pset != _last_problems[0]:
                    for pr in problems:
                        log(f"🚨 {pr}")
                    _last_problems[0] = pset
                else:
                    for pr in problems:
                        console(f"🚨 {pr}")
                heartbeat("مشکل: " + " | ".join(problems))
                _time.sleep(POLL_SECONDS)
                continue
            elif _last_problems[0]:
                _last_problems[0] = set()
                log("🟢 مشکل برطرف شد — همه‌چیز دوباره سالم است و ربات ادامه می‌دهد.")

            # بازار تعطیل؟ فقط یک بار اعلام کن و منتظر بمان
            learn_server_offset()
            if not market_is_open(symbols):
                if not _market_closed[0]:
                    _market_closed[0] = True
                    log("🌙 بازار تعطیل است — ربات بیدار است و منتظر باز شدن بازار می‌ماند "
                        "(سفارش‌ها و پوزیشن‌ها دست‌نخورده‌اند).")
                heartbeat("بازار تعطیل — منتظر")
                console("🌙 بازار تعطیل است | ربات سالم و در حال انتظار")
                _time.sleep(POLL_SECONDS)
                continue
            elif _market_closed[0]:
                _market_closed[0] = False
                log("☀️ بازار باز شد — ربات دوباره شروع به کار کرد.")
                sync_all(symbols, "باز شدن بازار")

            cap_state = enforce_open_cap(symbols_rev)
            if cap_state == "resync":
                sync_all(symbols, "آزاد شدن سقف تریدهای باز")

            # کندل ۴ ساعته‌ی جدید در هر نمادی → یک همگام‌سازی کامل و عادلانه برای همه
            new_candle = []
            for b, name in symbols.items():
                try:
                    bar = mt5.copy_rates_from_pos(name, mt5.TIMEFRAME_H4, 1, 1)
                    if bar is None or len(bar) == 0:
                        continue
                    t = int(bar[0]["time"])
                    if last_bar[b] is None or t > last_bar[b]:
                        last_bar[b] = t
                        new_candle.append(b)
                except Exception as e:
                    log(f"❌ خطا در چک کندل این نماد: {e}", b)
            if new_candle:
                log(f"کندل ۴ ساعته‌ی جدید بسته شد ({', '.join(new_candle)}) — بررسی دوباره‌ی همه‌ی زون‌ها و فیلترها...")
                sync_all(symbols, "کندل جدید")

            maybe_session_refresh(symbols)
            # دستورهایی که به‌خاطر بسته بودن بازار نماد مانده‌اند (مثلاً طلا ساعت ۰۰ تا ۰۱)
            retry_pending = process_retries()

            manage_positions(symbols_rev)
            track_positions(symbols_rev)
            maybe_daily_report(symbols_rev)
            maybe_periodic_reports(symbols_rev)
            report_status()
            bale_flush()  # پیام‌های مانده در صف بله، هر دور دوباره تلاش می‌شوند
            heartbeat("سالم")
            _time.sleep(RETRY_POLL_SECONDS if retry_pending else POLL_SECONDS)

        except KeyboardInterrupt:
            _mark_stopped()
            note_exit("توقف دستی (Ctrl+C)")
            log("⏹️ توقف دستی (Ctrl+C). سفارش‌ها و پوزیشن‌ها داخل متاتریدر دست‌نخورده می‌مانند "
                "(استاپ و تارگت روی خود سفارش‌هاست و سرور بروکر اجرایشان می‌کند). نگهبان هم ربات را "
                "دوباره روشن نمی‌کند تا خودت دوباره اجرایش کنی.")
            break
        except Exception as e:
            log(f"❌ خطای غیرمنتظره: {e} — ربات خاموش نمی‌شود و ادامه می‌دهد.")
            heartbeat(f"خطا: {e}")
            _time.sleep(POLL_SECONDS)

    mt5.shutdown()
    return EXIT_NO_RESTART


if __name__ == "__main__":
    sys.exit(main() or 0)
