# -*- coding: utf-8 -*-
import os, glob, zipfile, io, json
import re
import numpy as np

from analysis_distribution import distribution_sheets
import pandas as pd

# ============================================================================
# تایم‌فریم‌های استراتژی — باید با فایل‌های داخل ZIPهای دیتا یکی باشد
# ============================================================================
# همان استراتژی (زون، فیلتر روند/رنج، زون بزرگ مخالف) روی یکی از این دو دسته اجرا می‌شود:
#   "H4"  → زون و ورود روی ۴ساعته، روند/رنج روزانه، زون بزرگ هفتگی
#           فایل‌های لازم در ZIP:  -240.csv  -1D.csv  -1W.csv      (همان ربات لایو فعلی)
#   "M15" → بیس و ورود روی ۱۵دقیقه، روند ۴ساعته، فیبو و زون مخالف روزانه
#           فایل‌های لازم در ZIP:  -15.csv   -240.csv  -1D.csv
# برای ترتیب اتفاقات داخل کندل، ریزترین فایلِ ریزتر از تایم زون (مثلاً -5 یا -1) خودکار خوانده می‌شود.
# (ربات لایو همیشه روی H4 کار می‌کند و این تنظیم رویش اثری ندارد.)
STRATEGY_TF = "M15"
TF_SETS = {
    #        (فایل زون/بیس، فایل روند، فایل زون بزرگ و فیبو — None = ندارد)
    "M15": ("15", "240", None),     # روش خودت: بیس ۱۵دقیقه، روند و زون مخالف ۴ساعته (روزانه حذف شد)
    "H4":  ("240", "1D", "1W"),     # نسخه‌ی قدیمی ربات لایو
}

# ============================================================================
# قوانین استراتژی — از روی روش دستی خودت (عکس‌های بکتست دستی)
# ============================================================================
# نقطه‌ی ورود: ۱۰٪ ارتفاع بیس «بیرون» از پراکسیمال‌لاین (نزدیک‌تر به قیمت) — DEFAULT_ENTRY_OFF پایین‌تر
# حد ضرر: ۲۵٪ ارتفاع بیس پشت دیستال‌لاین — DEFAULT_SL_OFF | حد سود: ۳ برابر ریسک — DEFAULT_RR
#
# روند (تایم زون و تایم روند) از روی ساختار بازار — سقف/کف‌های اصلی، نه ریز:
#   "choch"    → روند فقط با «چاک» عوض می‌شود (شکست کف/سقف محافظ‌شده با کلوز کندل)
#   "choch_tl" → روند وقتی عوض می‌شود که «هم چاک بخورد هم ترندلاین با بدنه‌ی کندل بشکند».
#                اگر فقط ترندلاین بشکند، بازار «فاز فشردگی» است و هر دو جهت مجازند.
#   "legacy"   → روش قدیمی ربات (سقف/کف‌های ۳ کندلی ریز) — فقط برای مقایسه
# (در آزمایش‌های آخر فایل هر دو حالت choch و choch_tl جدا اجرا می‌شوند.)
TREND_MODE = "choch"
STRUCT_SWING_N = 3          # سقف/کف ساختار: کندلی که از ۳ کندل قبل و ۳ کندل بعدش بالاتر/پایین‌تر است
TL_SWING_N = 2              # کف‌ها/سقف‌هایی که ترندلاین از رویشان کشیده می‌شود (حالت choch_tl)
TRADE_WITH_TREND_ONLY = True  # فقط هم‌جهت روند: روند صعودی → فقط دیمند | نزولی → فقط سوپلای
#                               (قبلاً ربات جهت زون را با روند چک نمی‌کرد)
# روند ۱۵دقیقه هم باید یار باشد: اگر وقتی قیمت به دیمند می‌رسد روند ۱۵دقیقه نزولی شده (چاک نزولی)، بای نه
# (و برعکس برای سوپلای). اگر تا قبل از ورود روند ۱۵دقیقه خلاف شود، سفارش/انتظار لغو می‌شود.
ZONE_TF_TREND_REQUIRED = True   # True = روند تایم بیس (۱۵دقیقه) هم باید هم‌جهت باشد؛ False = فقط روند ۴ساعته
RANGE_FILTER = False        # فیلتر رنج قدیمی ربات (بر اساس ATR) — جزو روش دستی نیست

# ---- اعتبار بیس (تایم بیس = ۱۵دقیقه) ----
# کنسالیدیشن اوی: تا چند کندل بعد از بیس، باید یک کندل «کامل» بیرون از بیس تشکیل شود —
# حتی سایه‌اش به پراکسیمال‌لاین نخورد. ۰ = خاموش
LEGOUT_CLEAR_BARS = 3
# لگ‌اوت قوی: بدنه‌ی کندل خروج از بیس ≥ این ضریب × ATR(14) همان تایم. ۰ = خاموش
MIN_LEGOUT_BODY_ATR = 1.0
# فقط چاک ۱دقیقه: بیس‌های مخالفِ چسبیده به هم یک بیس حساب می‌شوند و چاک باید پشت دورترینشان با
# بادی بسته شود. چسبیده = فاصله‌ی قیمتی‌شان (یا دور شدن قیمت بینشان) حداکثر این ضریب × ATR و فاصله‌ی
# زمانی‌شان حداکثر این تعداد کندل (یک کندل، دو کندل متوسط یا چند کندل ریز). روی ۱۵دقیقه اعمال نمی‌شود.
CHOCH_CLUSTER_GAP_ATR = 1.5
CHOCH_CLUSTER_MAX_BARS = 5
# بی‌اعتبار شدن بیس: کندل ۱۵دقیقه پشت دیستال بسته شود (سایه حساب نیست)
ZONE_INVALIDATE_ON_CLOSE = True
# تأیید چاک: لگ‌اوت بیس باید «بیس مخالف خودش» را با بادی چاک بدهد — یعنی کلوز کندل آن طرف
# سقف/کفی که بیس مخالف ساخته (آخرین سقف پایین‌تر برای دیمند، آخرین کف بالاتر برای سوپلای)،
# پیش از آنکه قیمت به بیس برگردد. بیس مخالف = آخرین بیس مخالفِ شکسته‌نشده پیش از این بیس که
# خودش کنسالیدیشن اوی داده. بیس از بسته شدن کندل چاک قابل معامله است.
CHOCH_CONFIRM = True

# ---- تایم روند (۴ساعته) و تایم بالا (روزانه) ----
# داخل زون مخالف ۴ساعته/روزانه معامله ممنوع (داخل دیمند → سل نه | داخل سوپلای → بای نه)
HTF_ZONE_FILTER = True
# نزدیک زون مخالف نباشیم: فاصله‌ی ورود تا نزدیک‌ترین زون مخالف ۴ساعته/روزانه ≥ این ضریب × ریسک
# (۳ = جلوی تارگت 3R آزاد باشد). ۰ = خاموش
OPP_ZONE_ROOM_R = 3.0

# فیبوی آخرین سوئینگ روزانه (۰ = کف، ۱ = سقف): بای فقط زیر ۰.۸ | سل فقط بالای ۰.۱۵
# فقط وقتی تایم بزرگ (روزانه) در TF_SETS باشد؛ الان روزانه حذف شده، پس عملاً خاموش است.
FIB_FILTER = True
FIB_BUY_MAX = 0.80
FIB_SELL_MIN = 0.15
FIB_SWING_N = 3             # سقف/کف روزانه: کندلی که از ۳ روز قبل و بعدش بالاتر/پایین‌تر است

# بعد از ۳ سی‌پی (بیس هم‌جهت) پشت‌سرهم روی تایم روند (۴ساعته)، در آن جهت معامله نمی‌شود (۰ = خاموش)
MAX_CONSECUTIVE_CP = 3
CP_ON_TREND_TF = True       # True = سی‌پی‌ها روی ۴ساعته شمرده می‌شوند | False = روی تایم بیس

# ============================================================================
# واقع‌بینی بک‌تست (اصلاح خوش‌بینی‌ها — بعد از مقایسه با ۶ هفته لایو)
# ============================================================================
# بک‌تستر فقط کندل ۴ساعته را می‌بیند و ترتیب اتفاقات داخل کندل را نمی‌داند.
# نسخه‌ی قبلی دو فرض خوش‌بینانه داشت که تقریباً کل سود بک‌تست از آن‌ها می‌آمد:
#   ۱) در کندلی که سفارش پر می‌شد، فرض می‌کرد سقف/کفِ همان کندل «بعد از» پر شدن بوده
#      → سیو سود 2R یا تارگتی که در واقعیت قبل از ورود اتفاق افتاده بود، ثبت می‌شد.
#   ۲) زونی که در همین کندل لمس می‌شد، در همین کندل سفارش می‌گرفت و پر می‌شد؛
#      در حالی که ربات لایو لمس را فقط بعد از بسته شدن کندل می‌فهمد.
# مقایسه با لایو (۱۴ آگوست تا ۲۵ سپتامبر ۲۰۲۶): روش قدیم نتیجه‌ی ۲۶ از ۳۳ معامله را
# درست پیش‌بینی کرد و روش واقع‌بینانه ۳۱ از ۳۳.

# نحوه‌ی حساب کردن «کندل ورود» وقتی دیتای تایم‌فریم پایین‌تر نیست:
#   "path"        → مسیر کندل از رنگش: صعودی O→L→H→C ، نزولی O→H→L→C (فرض رایج تسترها برای کندل OHLC)
#   "pessimistic" → در کندل ورود فقط «کلوز» برای سیو سود/تارگت قابل اتکاست
#   "optimistic"  → رفتار قدیمی (فقط برای مقایسه — نتیجه‌اش قابل اعتماد نیست)
ENTRY_BAR_MODE = "path"

# زمان‌بندی ثبت سفارش مثل ربات لایو:
#   - زونی که در همین کندل لمس شده، از کندل بعد سفارش می‌گیرد (زون‌های لمس‌نشده‌ای که از قبل
#     «مسلح» شده‌اند سفارششان از قبل روی حساب است و عوض نمی‌شوند).
#   - اگر لحظه‌ی ثبت (باز شدن کندل) قیمت از نقطه‌ی ورود رد شده باشد، سفارش لیمیت گذاشته نمی‌شود
#     (ربات هم در این حالت سفارش نمی‌گذارد) و زون برای کندل‌های بعد می‌ماند.
NO_SAME_BAR_TOUCH_FILL = True

# شناسه‌ی زون (ZoneID) — ربات لایو سفارش‌ها را با همین شناسه (کامنت سفارش) پیدا می‌کند.
#   True  → شناسه‌ی پایدار: نماد + تایم + زمان تولد زون + جهت (مثل XAUUSD_H4_2608191200B).
#           با جلو رفتن پنجره‌ی ۲۰۰۰ کندلی ربات عوض نمی‌شود.
#   False → شیوه‌ی قدیمی (شماره‌ی ترتیب زون در پنجره) — با جلو رفتن پنجره جابه‌جا می‌شد و
#           باعث سفارش تکراری در لایو شد. فقط برای بازسازی گزارش‌های قدیمی.
STABLE_ZONE_IDS = True

# دیتا فقط قیمت Bid است. خرید لیمیت وقتی پر می‌شود که Ask برسد و حد ضرر/سود فروش با Ask
# اجرا می‌شود. True = اسپرد هر نماد (جدول spreads در main) در پر شدن و خروج اعمال شود.
# اسپرد هر نماد: اگر فایل spreads.csv (خروجی export_data) کنار دیتا در پوشه‌ی 0 باشد، اسپرد واقعی
# متاتریدر خودت از آن خوانده می‌شود؛ وگرنه جدول تقریبی SPREAD_TABLE.
MODEL_BID_ASK = True

# دیتای تایم‌فریم پایین‌تر برای دیدن ترتیب واقعی اتفاقات داخل کندل ۴ساعته.
# اگر داخل ZIP هر نماد فایل «-1.csv» یا «-5.csv» یا «-15.csv» (یا M1/M5/M15) باشد، ریزترینش
# (فقط اگر از تایم زون ریزتر باشد؛ برای STRATEGY_TF="M15" یعنی فقط «-1» یا «-5»)
# خوانده می‌شود و پر شدن، سیو سود، استاپ و تارگت کندل‌به‌کندل روی آن شبیه‌سازی می‌شود.
# اگر نباشد، ENTRY_BAR_MODE استفاده می‌شود. (نام متغیر به‌خاطر سازگاری همان USE_M15 مانده)
USE_M15 = True

# بازه‌ی بک‌تست: در صورت نیاز این دو خط را تغییر بده.
# اگر این تاریخ از شروع دیتا قدیمی‌تر باشد، خودکار روی شروع واقعی دیتا تنظیم می‌شود،
# پس گذاشتن یک تاریخ قدیمی یعنی «هرچه دیتا داری استفاده کن».
BACKTEST_START = pd.Timestamp("2025-01-01")  # معامله‌ها فقط سال ۲۰۲۵
BACKTEST_END = pd.Timestamp("2025-12-31 23:59:59")  # None یعنی تا انتهای دیتا
# گرم‌کردن: روند، زون‌ها و ATR از این چند روز قبل از BACKTEST_START ساخته می‌شوند تا روز اول
# بک‌تست آماده باشند؛ در این مدت معامله‌ای نیست. (export_data همین مقدار دیتای اضافه می‌گیرد)
WARMUP_DAYS = 120

# هزینه‌های معاملاتی (نسبت به اسپرد هر نماد؛ در صورت نیاز این دو عدد را ویرایش کن)
COMMISSION_SPREAD_MULT = 0.0       # کمیسیون: حساب دموی MetaQuotes کمیسیون ندارد (هیستوری = ۰). حساب واقعی ECN ≈ 0.5
SWAP_SPREAD_MULT_PER_NIGHT = 0.2   # سواپ ≈ ۲۰٪ اسپرد به ازای هر شب نگهداری پوزیشن

# مقایسه‌ی حالت‌های نقطه‌ی ورود در یک اجرا (شیت «مقایسه_نقطه_ورود» در خلاصه_نتایج.xlsx)
# اگر نمی‌خواهی و اجرا سریع‌تر شود، این را False کن.
COMPARE_ENTRY_MODES = False
ENTRY_MODES = {
    "+10% بیرون از پراکسیمال": 0.10,
}
# نقطه‌ی ورود = پراکسیمال + ۱۰٪ ارتفاع بیس به سمت قیمت (قانون اصلی استراتژی).
# مثبت = بیرون از زون به سمت قیمت | منفی = داخل زون (قبلاً -0.50 یعنی وسط زون بود)
DEFAULT_ENTRY_OFF = 0.10

# مقایسه‌ی نسبت سود به ضرر (RR) — تمام شد؛ RR نهایی: 3
COMPARE_RR_MODES = False
RR_MODES = {
    "RR=3": 3.0,
}
DEFAULT_RR = 3.0  # حالت اصلی گزارش‌های کامل

# مقایسه‌ی فیلترهای کیفیت زون (به سبک Odds Enhancers الفونسو) — شیت «مقایسه_کیفیت_زون»
COMPARE_QUALITY_MODES = False  # نتیجه: بدون فیلتر کیفیت بهترین بود
QUALITY_MODES = {
    "مبنا (بدون فیلتر کیفیت)": {},
    "باطل شدن زون شکسته": {"invalidate_on_breach": True},
    "حاشیه سود ≥3R": {"min_profit_margin_r": 3.0},
    "قدرت خروج ≥1×ATR": {"min_departure_atr": 1.0},
    "فرصت دوباره به زون ردشده": {"retry_rejected_zones": True},
    "فرصت دوباره + باطل‌شدن شکسته": {"retry_rejected_zones": True, "invalidate_on_breach": True},
}

# مقایسه‌ی فاصله‌ی حد ضرر از دیستال‌لاین (به نسبت کل ارتفاع زون) — شیت «مقایسه_استاپ»
COMPARE_SL_MODES = False  # نتیجه: ۲۵٪ برنده شد و پیش‌فرض است
SL_MODES = {
    "استاپ 25٪ پشت دیستال": 0.25,
    "استاپ 50٪ پشت دیستال": 0.50,
}
DEFAULT_SL_OFF = 0.25  # حالت اصلی گزارش‌های کامل

# قانون «لغو سفارش در صورت دور شدن قیمت»: اگر قیمت بدون فعال کردن سفارش،
# به اندازه‌ی چند برابرِ ریسک از نقطه‌ی ورود دور شد، سفارش لغو و زون بی‌اعتبار می‌شود.
# چند آستانه در یک اجرا مقایسه می‌شود — شیت «مقایسه_لغو_دور»
COMPARE_DISTCANCEL_MODES = False  # نتیجه: قانون لغو دور شدن برایند را بدتر کرد؛ بدون قانون می‌مانیم
DISTCANCEL_MODES = {
    "بدون قانون": 0.0,
    "دور شدن 3R": 3.0,
    "دور شدن 4R": 4.0,
    "دور شدن 5R": 5.0,
}
DEFAULT_DIST_CANCEL_R = 0.0  # حالت اصلی گزارش‌های کامل (فعلاً بدون قانون تا مقایسه را ببینیم)

# فیلتر «حداقل اندازه‌ی زون»: اگر فاصله‌ی ورود تا استاپ کمتر از این ضریب از ATR باشد، معامله نمی‌شود.
# چند آستانه در یک اجرا مقایسه می‌شود — شیت «مقایسه_حداقل_زون»
COMPARE_MINRISK_MODES = False  # نتیجه: فیلتر کمکی نکرد؛ بدون فیلتر می‌مانیم
MINRISK_MODES = {
    "بدون فیلتر": 0.0,
    "ملایم 0.5xATR": 0.5,
    "متوسط 0.75xATR": 0.75,
    "سختگیر 1.0xATR": 1.0,
}
DEFAULT_MIN_RISK_ATR = 0.0  # حالت اصلی گزارش‌های کامل (فعلاً بدون فیلتر تا مقایسه را ببینیم)

# --- بک‌تست پرتفویی: شبیه‌سازی یک حساب مشترک برای همه‌ی نمادها (شیت‌های «پرتفوی») ---
PORTFOLIO_MAX_OPEN = 5              # حداکثر پوزیشن باز هم‌زمان در کل حساب
PORTFOLIO_RISK_PER_TRADE = 0.01     # ریسک هر معامله از اکویتی حساب (0.005 = نیم درصد، 0.01 = یک درصد)
PORTFOLIO_SYMBOLS = []              # خالی = همه‌ی نمادها؛ نمونه: ["AUDCAD","EURUSD","CHFJPY","XAUUSD","GBPCAD"]

# ============================================================================
# حالت «عین لایو» — همه‌ی نمادها هم‌زمان روی یک حساب، دقیقاً مثل sync_all ربات
# ============================================================================
# در حالت قدیمی هر نماد جدا بک‌تست می‌شد (سقف ۳ سفارش فقط داخل همان نماد) و سقف
# کل حساب بعداً در portfolio_replay روی فهرست آماده اعمال می‌شد. نتیجه‌اش این بود
# که بک‌تست عملاً اجازه‌ی ۱۲×۳ = ۳۶ سفارش هم‌زمان می‌داد ولی ربات فقط ۸ تا.
# در این حالت، موتور همه‌ی نمادها را کندل‌به‌کندل با هم جلو می‌برد و سهمیه‌بندی
# دوریِ (round-robin) ربات را عیناً اجرا می‌کند.
LIVE_MODE = True                    # True = شبیه‌سازی عین لایو (توصیه‌شده)
# ۰ = بدون سقف (فعلاً بی‌سقف تا خود استراتژی سنجیده شود؛ ربات لایو قدیمی: ۸ / ۸ / ۳)
LIVE_MAX_PENDING_TOTAL = 0          # سقف سفارش پندینگ کل حساب
LIVE_MAX_OPEN_TOTAL = 0             # سقف پوزیشن باز کل حساب
LIVE_MAX_PENDING_PER_SYMBOL = 0     # سقف سفارش هر نماد
LIVE_ARM_UNTOUCHED = True           # چیدن سفارش روی زون‌های لمس‌نشده — عین فهرست armed ربات
LIVE_RISK_PER_TRADE = 0.01          # ریسک هر معامله: ۱٪ (ربات لایو فعلی هنوز ۰.۵٪ است)
LIVE_RESERVE = 0.15                 # سرمایه‌ی رزرو — برابر RESERVE ربات
LIVE_START_EQUITY = 100000.0
# ترتیب نمادها در سهمیه‌بندی دوری — باید عیناً همان ترتیب BASKET در live_trader.py باشد
# (نماد اول در هر دور اولویت دارد، پس ترتیب روی نتیجه اثر دارد)
LIVE_BASKET_ORDER = ["XAUUSD", "AUDJPY", "AUDUSD", "CHFJPY", "EURCAD", "EURNZD",
                     "GBPJPY", "GBPNZD", "NZDCAD", "USDCHF"]

# نمادهایی که کلاً از سبد بیرون گذاشته می‌شوند (حتی اگر فایل دیتایشان موجود باشد).
# ⚠️ اگر اینجا نمادی را حذف کردی، در live_trader.py هم از BASKET حذفش کن،
#    وگرنه ربات چیزی معامله می‌کند که بک‌تست نکرده‌ای.
LIVE_EXCLUDE_SYMBOLS = ["USDCAD", "NZDUSD"]

# ============================================================================
# تست پایداری نمادها — «آیا لبه‌ی این نماد واقعی است یا شانسی؟»
# ============================================================================
# تست ۱ (رایگان): بازه به دو نیمه تقسیم می‌شود و کارنامه‌ی هر نماد در هر نیمه
# جدا گزارش می‌شود. نمادی که فقط در یک نیمه خوب بوده، لبه‌ی واقعی ندارد.
# خروجی: شیت «پایداری_نماد»
STABILITY_TEST = True
STABILITY_MIN_TRADES = 20   # کمتر از این تعداد در یک نیمه = نمونه‌ی کم، قضاوت نکن

# تست ۲ (گران): هر بار یک نماد از سبد برداشته می‌شود و کل بک‌تست دوباره اجرا
# می‌گردد تا ببینیم حساب بدون آن نماد بهتر می‌شود یا بدتر. چون نمادها سر ۸ جای
# سفارش با هم رقابت می‌کنند، حذف یک نماد جا را به بقیه می‌دهد — این تنها راهِ
# درستِ جواب دادن به «حذفش کنم یا نه؟» است.
# ⚠️ زمان‌بر: (تعداد نمادها + ۱) برابر یک اجرای کامل. برای ۱۲ نماد و دیتای ۶ ساله
#    حدود ۷۵ دقیقه. فقط وقتی روشنش کن که وقت داری.
# خروجی: شیت «حذف_تک‌نماد»
LEAVE_ONE_OUT_TEST = False

# ============================================================================
# آزمایش تغییر طراحی — هر تغییر «جداگانه» روی همان دیتا اجرا می‌شود
# ============================================================================
# هر ردیف یک اجرای کامل بک‌تست است (همه‌ی نمادها روی یک حساب، عین لایو) و نتیجه‌اش در
# یک سربرگ جدا در «خلاصه_نتایج.xlsx» نوشته می‌شود؛ سربرگ «مقایسه_طراحی‌ها» همه را کنار
# مبنا (بدون تغییر = سربرگ «خلاصه») نشان می‌دهد.
# ⚠️ زمان‌بر: هر ردیف یک اجرای کامل. ردیفی را که نمی‌خواهی با # غیرفعال کن.
DESIGN_TESTS = True
# اجرای اصلی: «zone» = قیمت به بیس ۱۵دقیقه می‌رسد → منتظر چاک ۱دقیقه در جهت بیس → بعد اوردر روی همان
# بیس ۱۵دقیقه (ورود +۱۰٪، استاپ ۲۵٪، تارگت 3R) | «base» = اوردر روی بیس ۱دقیقه | None = بدون تأیید (روش قدیمی)
LTF_MODE = "zone"
LTF_RUN_NAMES = {"zone": "تأیید ۱دقیقه + ورود روی بیس ۱۵دقیقه",
                 "base": "تأیید ۱دقیقه + ورود روی بیس ۱دقیقه",
                 None: "ورود لیمیت ۱۵دقیقه (بدون تأیید)"}
DESIGN_VARIANTS = {
    # نام اجرا: (تنظیمات، توضیح) — اجرای اصلی بالا (LTF_MODE)
    "تأیید_۱دقیقه_ورود_بیس_۱دقیقه": ({"ltf_mode": "base"},
        "قیمت به بیس ۱۵دقیقه می‌رسد → منتظر چاک ۱دقیقه در جهت بیس → بعد اوردر روی بیس ۱دقیقه‌ای که چاک "
        "را ساخت (ورود +۱۰٪، استاپ ۲۵٪، تارگت 3R)"),
}
# تأیید ۱دقیقه: سفارشِ بعد از تأیید اگر قیمت این‌قدر R از بیس دور شد و پر نشد، لغو می‌شود
# (تارگت خود معامله همان 3R است. وقتی ربات سودده شد، چند مقدار دیگرِ این عدد هم بکتست شود.)
LTF_CANCEL_R = 7.0
# ورود روی بیس ۱دقیقه: اگر استاپ از این ضریب × اسپرد کوچک‌تر باشد ورود نمی‌شود (استاپ داخل اسپرد)
LTF_MIN_RISK_SPREAD = 2.0

# سربرگ‌های اضافه‌ی خروجی (پایداری نماد، پرتفوی، تنظیمات و ...). False = فقط «خلاصه»
# و سربرگ‌های آزمایش طراحی نوشته می‌شوند.
WRITE_EXTRA_SHEETS = False
# خروجی ساده: فقط دو سربرگ — «کلی» (همه‌ی اجراها) و «دلیل_استاپ‌ها» (روند ۴ساعته یا بیس ۱۵دقیقه)
SIMPLE_EXCEL = True
# نمودار هر معامله (عکس PNG در «خروجی/نمودار_معاملات») برای مقایسه با روش دستی — به matplotlib نیاز دارد
TRADE_CHARTS = True
TRADE_CHARTS_MAX = 400      # حداکثر تعداد نمودار هر اجرا
STOP_CAUSE_DAYS = 30   # بعد از ورود تا چند روز نگاه شود که اول روند ۴ساعته برگشت یا قیمت به تارگت رسید

# فایل «جزئیات_حرفه‌ای.xlsx» ساخته بشود یا نه (False = فقط خلاصه؛ سریع‌تر)
WRITE_DETAILS = False
# شیت‌های ریز پرتفوی (سالانه/ماهانه) هم نوشته شوند؟ False = خروجی تمیزتر
WRITE_PORTFOLIO_DETAIL = False

# --- تحلیل سشن‌های معاملاتی (شیت‌های «تحلیل_سشن» و «سشن_هر_نماد») ---
ANALYZE_SESSIONS = False   # تحلیل سشن انجام شد؛ نتیجه‌اش در وزن‌دهی زیر اعمال شده
SESSION_STABILITY = False

# --- وزن‌دهی ریسک بر اساس سشن (نهایی: حالت تهاجمی، برنده‌ی مقایسه) ---
USE_DEFAULT_SESSION_WEIGHTS = False  # خاموش: ریسک همه‌ی سشن‌ها یکسان
DEFAULT_SESSION_WEIGHTS = {
    "لندن": 1.5,
    "همپوشانی لندن-نیویورک": 1.25,
    "سیدنی/پایان روز": 1.0,
    "آسیا (توکیو)": 0.75,
    "آسیا (پایان)": 0.5,
    "نیویورک": 0.5,
}

# مقایسه‌ی «وزن‌دهی ریسک بر اساس سشن» — شیت «مقایسه_وزن_سشن»
COMPARE_SESSION_WEIGHTS = False
SESSION_WEIGHT_MODES = {
    "بدون وزن‌دهی (مبنا)": {},
    "محافظه‌کارانه": {"آسیا (پایان)": 0.5, "نیویورک": 0.5, "آسیا (توکیو)": 0.75},
    "تمرکز روی لندن": {"آسیا (پایان)": 0.5, "نیویورک": 0.5, "آسیا (توکیو)": 0.5,
                        "سیدنی/پایان روز": 0.75},
    "تهاجمی (لندن ۱.۵ برابر)": {"لندن": 1.5, "همپوشانی لندن-نیویورک": 1.25,
                                  "آسیا (پایان)": 0.5, "نیویورک": 0.5, "آسیا (توکیو)": 0.75},
}
# ساعت دیتای بروکر معمولاً UTC+2 یا UTC+3 است. برای تبدیل به UTC این عدد به ساعت‌ها اضافه می‌شود.
# اگر مطمئن نیستی صفر بگذار و جدول «ساعت خام» را ببین، بعد کالیبره کن.
SESSION_HOUR_SHIFT = -3   # نمونه: دیتای UTC+3 → -3 برای رسیدن به UTC
# بازه‌های سشن بر حسب ساعت UTC — [شروع، پایان)
SESSION_RANGES = [
    (0, 4,  "آسیا (توکیو)"),
    (4, 8,  "آسیا (پایان)"),
    (8, 12, "لندن"),
    (12, 16, "همپوشانی لندن-نیویورک"),
    (16, 20, "نیویورک"),
    (20, 24, "سیدنی/پایان روز"),
]

def hour_to_session(h):
    for a, b, name in SESSION_RANGES:
        if a <= h < b:
            return name
    return "نامشخص"

# مقایسه‌ی «سقف اجرا» (شبیه ربات لایو): هر چارت حداکثر ۱ ترید باز + سقف کل.
# نتایج در شیت «مقایسه_سقف_اجرا»
COMPARE_EXECCAP_MODES = False  # نتیجه: «هر چارت ۳ + سقف ۸» انتخاب شد
EXECCAP_MODES = {
    "بدون محدودیت": (0, 0),          # (سقف کل تریدهای باز, سقف هر چارت)
    "هر چارت 1 + سقف 3": (3, 1),
    "هر چارت 1 + سقف 5": (5, 1),
}

# مقایسه‌ی «مدیریت معامله» (سیو سود / ریسک‌فری وقتی سود به ۲ برابر ریسک رسید)
# نتایج در شیت «مقایسه_مدیریت»
COMPARE_MANAGE_MODES = False  # نتیجه: «سیو سود در 2R» برنده شد و پیش‌فرض است؛ ریسک‌فری حذف قطعی
MANAGE_MODES = {
    "عادی (بدون مدیریت)": "none",
    "سیو سود در 2R": "partial2",
    "سیو سود + ریسک‌فری در 2R": "partial2_be",
    "ریسک‌فری در 2R": "be2",
}
DEFAULT_MANAGE = "partial2"  # حالت اصلی: سیو سودِ نصف حجم در 2R (برنده‌ی مقایسه)
MANAGE_TRIGGER_R = 2.0      # آستانه‌ی فعال شدن مدیریت: سود ۲ برابر ریسک
PARTIAL_CLOSE_FRAC = 0.5    # سهم سیو سود: نصف حجم

# مقایسه‌ی «محدودیت ضرر» — نتیجه: کمکی نکرد (فقط سود کمتر)؛ بدون محدودیت می‌مانیم
COMPARE_LOSSLIMIT_MODES = False
LOSSLIMIT_MODES = {
    "بدون محدودیت": (0, 0),
    "3 ضرر روز / 7 هفته": (3, 7),
    "2 ضرر روز / 5 هفته": (2, 5),
    "3 ضرر روز / 5 هفته": (3, 5),
}

# اسپرد تقریبی هر نماد (برحسب قیمت) — برای هزینه، مدل Bid/Ask و فیلتر «حداقل اندازه‌ی زون».
# ربات لایو اسپرد را به مغز نمی‌دهد (صفر)؛ فیلترها از همین جدول استفاده می‌کنند تا لایو و
# بک‌تست یکی بمانند.
SPREAD_TABLE = {
    "EURUSD":0.00012, "GBPUSD":0.00018, "AUDUSD":0.00014, "NZDUSD":0.00016,
    "USDCAD":0.00015, "USDCHF":0.00014,
    "EURAUD":0.00025, "EURCAD":0.00022, "EURGBP":0.00018, "EURNZD":0.00025,
    "GBPAUD":0.00030, "GBPCAD":0.00028, "GBPNZD":0.00032,
    "AUDCAD":0.00022, "AUDNZD":0.00024, "CADJPY":0.020, "CHFJPY":0.020,
    "EURJPY":0.020, "GBPJPY":0.025, "USDJPY":0.020, "AUDJPY":0.020,
    "NZDCAD":0.00025,
    "XAUUSD":0.30, "XAGUSD":0.03
}

# ------------- CSV reader (MetaTrader no header) -------------
def _smart_dt(d, t=None):
    """تبدیل تاریخ به datetime با تشخیص خودکار ترتیب روز/ماه (برای فرمت‌های مختلف بروکرها)."""
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
    """خواندن CSV قیمت با تشخیص خودکار فرمت:
    - متاتریدر بدون سطر عنوان (date,time,o,h,l,c[,v])
    - فایل‌های دارای سطر عنوان (مثل FXCM): ستون‌های Open/High/Low/Close یا BidOpen/BidHigh/...
      و تاریخ به‌صورت دو ستون Date/Time یا یک ستون DateTime"""
    if b is None or len(b) == 0:
        raise ValueError("فایل CSV خالی است.")

    head = b[:2048].decode("utf-8", "ignore")
    first_line = head.splitlines()[0].lower() if head else ""
    has_header = any(k in first_line for k in ("open", "high", "low", "close"))

    if has_header:
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
        elif dcol is not None:
            tser = _smart_dt(dcol)
        elif tcol is not None:
            tser = _smart_dt(tcol)
        else:
            tser = _smart_dt(df.iloc[:, 0])
    else:
        df = pd.read_csv(io.BytesIO(b), header=None)
        if df.shape[1] < 5:
            raise ValueError("فرمت CSV غیرمنتظره است (ستون کم).")
        c1 = pd.to_numeric(df.iloc[:, 1], errors="coerce")
        if c1.notna().mean() > 0.9:
            # ستون اول تاریخ+ساعت یکجا است
            tser = _smart_dt(df.iloc[:, 0])
            o, h, l, c = (df.iloc[:, k] for k in (1, 2, 3, 4))
        else:
            # فرمت کلاسیک متاتریدر: date,time,o,h,l,c
            if df.shape[1] < 6:
                raise ValueError("فرمت CSV غیرمنتظره است (ستون کم).")
            tser = _smart_dt(df.iloc[:, 0], df.iloc[:, 1])
            o, h, l, c = (df.iloc[:, k] for k in (2, 3, 4, 5))

    out = pd.DataFrame({
        "time": tser,
        "open": pd.to_numeric(o, errors="coerce"),
        "high": pd.to_numeric(h, errors="coerce"),
        "low":  pd.to_numeric(l, errors="coerce"),
        "close": pd.to_numeric(c, errors="coerce"),
    })
    out = out.dropna().sort_values("time").drop_duplicates("time").reset_index(drop=True)
    if out.empty:
        raise ValueError("هیچ سطر معتبری در CSV پیدا نشد (فرمت ناشناخته).")
    return out

_LTF_MINUTES = {"1": 1, "5": 5, "15": 15, "30": 30, "60": 60}


def _suffix_minutes(label):
    if label in _LTF_MINUTES:
        return _LTF_MINUTES[label]
    return {"240": 240, "1D": 1440, "1W": 10080}.get(label, 10 ** 9)


def _csvs_in_folder(folder):
    """همه‌ی CSVهای یک پوشه (و زیرپوشه‌هایش) → {اسم فایل: مسیر کامل}"""
    out = {}
    for root, _dirs, files in os.walk(folder):
        for fn in files:
            if fn.lower().endswith(".csv"):
                out.setdefault(fn, os.path.join(root, fn))
    return out


class _FolderSource:
    """پوشه‌ی بازشده‌ی یک نماد (مثلاً 0\\AUDJPY\\AUDJPY-240.csv) را مثل یک ZIP می‌خواند."""
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
    """دیتای هر نماد در پوشه‌ی دیتا: فایل ZIP (مثل XAUUSD.zip) یا پوشه‌ی بازشده‌اش
    (مثل پوشه‌ی XAUUSD که CSVها داخلش است). اگر هر دو باشد، ZIP خوانده می‌شود."""
    sources = {}
    for zp in sorted(glob.glob(os.path.join(datadir, "*.zip"))):
        sources[os.path.basename(zp).split(".")[0]] = zp
    for d in sorted(glob.glob(os.path.join(datadir, "*"))):
        if not os.path.isdir(d):
            continue
        sym = os.path.basename(d).split(".")[0]
        if sym in sources:
            continue
        if _csvs_in_folder(d) or glob.glob(os.path.join(d, "**", "*.zip"), recursive=True):
            sources[sym] = d
    return [sources[k] for k in sorted(sources)]


def pip_size(symbol):
    if symbol.endswith("JPY"):
        return 0.01
    if symbol.startswith("XAU"):
        return 0.1
    if symbol.startswith("XAG"):
        return 0.01
    return 0.0001


def load_mt5_spreads(datadir):
    """اسپرد واقعی هر نماد از spreads.csv (خروجی export_data / export_spreads.bat) → {نماد: اسپرد}
    میانه‌ی تیک‌ها استفاده می‌شود، نه میانگین: پرش‌های لحظه‌ای اسپرد (رول‌اوور نیمه‌شب، باز شدن
    بازار) میانگینِ نمادهای کم‌معامله مثل CHFJPY را چند برابر اسپرد معمول نشان می‌دهد."""
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


def load_timeframes_from_zip(zip_path: str, tf_set=None):
    """خواندن سه تایم‌فریم استراتژی (+ تایم ریزتر اختیاری) از ZIP یک نماد (یا پوشه‌ی بازشده‌اش).

    خروجی: (زون، روند، زون بزرگ، تایم ریزتر یا None) — برای سازگاری با بقیه‌ی کد، اسم
    متغیرها همان h4, d1, w1, m15 مانده ولی بسته به STRATEGY_TF می‌تواند M15/H1/H4 باشد."""
    if not os.path.exists(zip_path):
        raise FileNotFoundError(f"فایل ZIP پیدا نشد: {zip_path}")
    key = tf_set or STRATEGY_TF
    if key not in TF_SETS:
        raise ValueError(f"STRATEGY_TF نامعتبر است: {key} — مجاز: {', '.join(TF_SETS)}")
    lab_zone, lab_trend, lab_big = TF_SETS[key]

    with _open_data_source(zip_path) as z:
        names = z.namelist()
        if not names:
            raise ValueError(f"فایل ZIP خالی است: {zip_path}")

        def find(label):
            return [n for n in names if n.endswith(f"-{label}.csv")]

        fz, ft = find(lab_zone), find(lab_trend)
        fb = find(lab_big) if lab_big else ["-"]
        if not fz or not ft or not fb:
            raise ValueError(
                f"داخل ZIP فایل‌های لازم برای STRATEGY_TF=\"{key}\" پیدا نشد: {zip_path} | "
                f"{lab_zone}={len(fz)} {lab_trend}={len(ft)}"
                + (f" {lab_big}={len(fb)}" if lab_big else "") + " — "
                f"یا دیتای همین تایم‌فریم‌ها را بگیر یا STRATEGY_TF را عوض کن."
            )

        # تایم‌فریم ریزتر (اختیاری) — ریزترینِ موجود که از تایم زون ریزتر باشد
        f15_list = []
        zone_min = _suffix_minutes(lab_zone)
        for suf in ("1", "5", "15", "30", "60"):
            if _LTF_MINUTES[suf] >= zone_min:
                break
            f15_list = [n for n in names if n.endswith(f"-{suf}.csv") or n.endswith(f"-M{suf}.csv")]
            if f15_list:
                break

        h4 = read_mt_csv_from_bytes(z.read(fz[0]))
        d1 = read_mt_csv_from_bytes(z.read(ft[0]))
        w1 = read_mt_csv_from_bytes(z.read(fb[0])) if lab_big else None   # None = تایم بزرگ ندارد
        m15 = read_mt_csv_from_bytes(z.read(f15_list[0])) if f15_list else None

    if h4.empty or d1.empty or (w1 is not None and w1.empty):
        raise ValueError(
            f"داده‌ی یکی از تایم‌فریم‌ها داخل ZIP خالی است: {zip_path} | "
            f"زون={len(h4)} روند={len(d1)} بزرگ={0 if w1 is None else len(w1)}"
        )

    return h4, d1, w1, m15

# ---------------- Indicators ----------------
def atr(df: pd.DataFrame, period=14):
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        (df["high"] - df["low"]),
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(period, min_periods=period).mean()

def range_filter(df: pd.DataFrame, atr_s: pd.Series, lookback=20, k=3.0):
    hh = df["high"].rolling(lookback, min_periods=lookback).max()
    ll = df["low"].rolling(lookback, min_periods=lookback).min()
    return (hh - ll) < (k * atr_s)



def swing_points(df: pd.DataFrame, n=1):
    highs = df["high"].values
    lows  = df["low"].values
    sh = np.zeros(len(df), dtype=bool)
    sl = np.zeros(len(df), dtype=bool)
    for i in range(n, len(df)-n):
        if np.all(highs[i] > highs[i-n:i]) and np.all(highs[i] > highs[i+1:i+n+1]):
            sh[i] = True
        if np.all(lows[i] < lows[i-n:i]) and np.all(lows[i] < lows[i+1:i+n+1]):
            sl[i] = True
    return sh, sl

def trend_from_swings(df: pd.DataFrame, n=1):
    """
    نسخه بدون lookahead:
    swing_points همچنان با همان منطقِ قبلی سوئینگ‌ها را تعیین می‌کند،
    اما سیگنال سوئینگ فقط بعد از n کندل (یعنی وقتی قابل تایید است) وارد trend می‌شود.
    """
    sh, sl = swing_points(df, n=n)

    last_hi = np.nan
    last_lo = np.nan
    cur = 0
    out = np.zeros(len(df), dtype=int)

    for i in range(len(df)):
        # تأیید سوئینگ با تأخیر n کندل
        j = i - n
        if j >= 0:
            if sh[j]:
                last_hi = df["high"].iloc[j]
            if sl[j]:
                last_lo = df["low"].iloc[j]

        c = df["close"].iloc[i]
        if (not np.isnan(last_hi)) and c > last_hi:
            cur = 1
        elif (not np.isnan(last_lo)) and c < last_lo:
            cur = -1

        out[i] = cur

    return pd.Series(out, index=df.index)
# ---------------- روند از روی ساختار بازار (چاک / ترندلاین) ----------------
_ALLOWED_DIRS = {1: ("BUY",), -1: ("SELL",), 2: ("BUY", "SELL"), -2: ("BUY", "SELL")}
TREND_TXT = {1: "صعودی", -1: "نزولی", 0: "بدون روند",
             2: "صعودی ولی ترندلاینش شکسته (فاز فشردگی)",
             -2: "نزولی ولی ترندلاینش شکسته (فاز فشردگی)"}


def dirs_allowed(dtr, htr):
    """جهت‌های مجاز معامله از روی روند تایم روند (dtr) و تایم زون (htr)."""
    if not TRADE_WITH_TREND_ONLY:
        # رفتار قدیمی: فقط هم‌جهتی دو روند لازم بود و جهت خود زون چک نمی‌شد
        return ("BUY", "SELL") if (dtr != 0 and dtr == htr) else ()
    a = _ALLOWED_DIRS.get(int(dtr), ())
    if not ZONE_TF_TREND_REQUIRED:
        return a                      # فقط روند تایم روند (۴ساعته) تعیین‌کننده است
    b = _ALLOWED_DIRS.get(int(htr), ())
    return tuple(x for x in a if x in b)


def structure_trend(df, n=3, use_trendline=False, tl_n=2):
    """روند از روی ساختار بازار، بدون نگاه به آینده (سقف/کف بعد از n کندل تأیید می‌شود).

    - BOS صعودی: کلوز بالای آخرین سقف شکسته‌نشده → روند صعودی می‌ماند/می‌شود و
      «کف محافظ‌شده» = پایین‌ترین کف از آن سقف تا الان (همان کفی که این BOS را ساخت).
    - چاک نزولی: کلوز زیر کف محافظ‌شده → روند نزولی. (برعکسش برای روند نزولی)
      کف/سقف‌های ریزِ داخل اصلاح، روند را عوض نمی‌کنند؛ فقط کف/سقف محافظ‌شده.
    - use_trendline: ترندلاین از کفِ شروع روند و کف‌های بالارونده‌ی بعدی کشیده می‌شود (در روند
      نزولی از سقف‌ها)؛ همیشه از «آخرین کف» و کفِ پایین‌ترِ قبلی، تا خط بالارونده بماند.
      کلوز کندل آن طرف خط = شکست ترندلاین → «فاز فشردگی» (خروجی 2 یا -2: هر دو جهت مجاز).
      روند فقط وقتی عوض می‌شود که هم چاک بخورد هم ترندلاین شکسته باشد (اگر ترندلاین معتبری
      نباشد، چاک به‌تنهایی کافی است).

    خروجی برای هر کندل: 1 صعودی، -1 نزولی، 0 نامشخص، 2/-2 فاز فشردگی."""
    hi = df["high"].to_numpy(dtype=float)
    lo = df["low"].to_numpy(dtype=float)
    cl = df["close"].to_numpy(dtype=float)
    N = len(df)
    out = np.zeros(N, dtype=int)
    if N == 0:
        return pd.Series(out, index=df.index)
    sh, sl = swing_points(df, n=n)
    if use_trendline:
        tsh, tsl = (sh, sl) if tl_n == n else swing_points(df, n=tl_n)

    st = {"trend": 0, "prot": np.nan, "prot_i": -1, "last_sh": -1, "sh_live": False,
          "last_sl": -1, "sl_live": False, "anchors": [], "line": None, "tl_broken": False,
          "pending": False}

    def make_line():
        """آخرین نقطه + نزدیک‌ترین نقطه‌ی قبلی که خط را در جهت روند نگه دارد."""
        a = st["anchors"]
        if len(a) < 2:
            return None
        i2, p2 = a[-1]
        for i1, p1 in reversed(a[:-1]):
            if (st["trend"] > 0 and p1 < p2) or (st["trend"] < 0 and p1 > p2):
                return (i1, p1, i2, p2)
        return None

    def line_val(j):
        i1, p1, i2, p2 = st["line"]
        return p1 + (p2 - p1) * (j - i1) / (i2 - i1)

    def beyond(j):
        return (cl[j] < line_val(j)) if st["trend"] > 0 else (cl[j] > line_val(j))

    def start_trend(new_trend, i):
        old = st["trend"]
        if new_trend > 0:
            s0 = st["prot_i"] if (old < 0 and st["prot_i"] >= 0) else max(st["last_sh"], 0)
            k = s0 + int(np.argmin(lo[s0:i + 1]))
            st["prot"], st["prot_i"] = lo[k], k
            if st["last_sh"] >= 0 and cl[i] > hi[st["last_sh"]]:
                st["sh_live"] = False
        else:
            s0 = st["prot_i"] if (old > 0 and st["prot_i"] >= 0) else max(st["last_sl"], 0)
            k = s0 + int(np.argmax(hi[s0:i + 1]))
            st["prot"], st["prot_i"] = hi[k], k
            if st["last_sl"] >= 0 and cl[i] < lo[st["last_sl"]]:
                st["sl_live"] = False
        st["trend"] = new_trend
        st["anchors"] = [(st["prot_i"], st["prot"])]      # ترندلاین از نقطه‌ی شروع روند
        st["line"] = None
        st["tl_broken"] = False
        st["pending"] = False

    for i in range(N):
        k = i - n
        if k >= 0:
            if sh[k]:
                st["last_sh"], st["sh_live"] = k, True
            if sl[k]:
                st["last_sl"], st["sl_live"] = k, True
        trend = st["trend"]
        if use_trendline and trend != 0:
            kt = i - tl_n
            if kt > st["prot_i"]:
                pt = None
                if trend > 0 and tsl[kt]:
                    pt = (kt, lo[kt])
                elif trend < 0 and tsh[kt]:
                    pt = (kt, hi[kt])
                if pt is not None:
                    st["anchors"] = (st["anchors"] + [pt])[-12:]
                    ln = make_line()
                    if ln is not None:
                        st["line"] = ln
                        st["tl_broken"] = any(beyond(j) for j in range(ln[2] + 1, i + 1))
            if st["line"] is not None and not st["tl_broken"] and beyond(i):
                st["tl_broken"] = True
        c = cl[i]
        if trend == 0:
            if st["sh_live"] and c > hi[st["last_sh"]]:
                st["sh_live"] = False
                start_trend(1, i)
            elif st["sl_live"] and c < lo[st["last_sl"]]:
                st["sl_live"] = False
                start_trend(-1, i)
        elif trend > 0:
            if st["sh_live"] and c > hi[st["last_sh"]]:            # BOS صعودی
                st["sh_live"] = False
                k2 = st["last_sh"] + int(np.argmin(lo[st["last_sh"]:i + 1]))
                st["prot"], st["prot_i"] = lo[k2], k2
                st["pending"] = False
                if st["tl_broken"]:          # روند دوباره تأیید شد → ترندلاین از نو کشیده می‌شود
                    st["line"], st["tl_broken"] = None, False
            elif c < st["prot"] or st["pending"]:                   # چاک نزولی
                if (not use_trendline) or st["line"] is None or st["tl_broken"]:
                    start_trend(-1, i)
                else:
                    st["pending"] = True
        else:
            if st["sl_live"] and c < lo[st["last_sl"]]:            # BOS نزولی
                st["sl_live"] = False
                k2 = st["last_sl"] + int(np.argmax(hi[st["last_sl"]:i + 1]))
                st["prot"], st["prot_i"] = hi[k2], k2
                st["pending"] = False
                if st["tl_broken"]:
                    st["line"], st["tl_broken"] = None, False
            elif c > st["prot"] or st["pending"]:                   # چاک صعودی
                if (not use_trendline) or st["line"] is None or st["tl_broken"]:
                    start_trend(1, i)
                else:
                    st["pending"] = True
        t_now = st["trend"]
        if t_now != 0 and use_trendline and st["line"] is not None and st["tl_broken"]:
            out[i] = 2 * t_now
        else:
            out[i] = t_now
    return pd.Series(out, index=df.index)


def weekly_fib_range(w1, n=2):
    """برای هر کندل هفتگی (بسته‌شده): محدوده‌ی آخرین سوئینگ — از قدیمی‌ترینِ «آخرین سقف» و
    «آخرین کف» تأییدشده تا همین هفته، بالاترین سقف و پایین‌ترین کف. (بدون نگاه به آینده)"""
    hi = w1["high"].to_numpy(dtype=float)
    lo = w1["low"].to_numpy(dtype=float)
    N = len(w1)
    sh, sl = swing_points(w1, n=n)
    r_lo = np.full(N, np.nan)
    r_hi = np.full(N, np.nan)
    last_h = last_l = -1
    for i in range(N):
        k = i - n
        if k >= 0:
            if sh[k]:
                last_h = k
            if sl[k]:
                last_l = k
        if last_h >= 0 and last_l >= 0:
            st = min(last_h, last_l)
            r_hi[i] = hi[st:i + 1].max()
            r_lo[i] = lo[st:i + 1].min()
    return r_lo, r_hi


# ---------------- Base/Doji rules ----------------
def is_base_candle(row):
    rng = row["high"] - row["low"]
    if rng <= 0: return False
    body = abs(row["close"] - row["open"])
    return body <= 0.5 * rng

def is_doji_small(row, atr_v, body_ratio_max=0.20, range_atr_max=0.80):
    rng = row["high"] - row["low"]
    if rng <= 0 or atr_v is None or np.isnan(atr_v) or atr_v <= 0:
        return False
    body = abs(row["close"] - row["open"])
    return (body / rng) <= body_ratio_max and (rng <= (range_atr_max * atr_v))

def strong_close(row):
    rng = row["high"] - row["low"]
    if rng <= 0: return False
    body = abs(row["close"] - row["open"])
    return body > 0.5 * rng

# ---------------- Zone structure ----------------
class Zone:
    def __init__(self, symbol, tf, direction, proximal, distal, created_time, base_start, base_end, doji_shadow):
        self.symbol=symbol
        self.tf=tf
        self.direction=direction
        self.proximal=float(proximal)
        self.distal=float(distal)
        self.created_time=created_time
        self.base_start=base_start
        self.base_end=base_end
        self.doji_shadow=bool(doji_shadow)
        self.touch_count=0
        self.last_touch_i=None
        self.clean_after_touch=999
        self.expired=False
        self.zone_id=None
        self.superseded_time=None  # زمانی که زون جدیدِ هم‌پوشان جای این زون را می‌گیرد
        self.conf_body_atr=0.0     # قدرت خروج: بدنه‌ی کندل تأیید نسبت به ATR
        self.departure_h=0.0       # حاشیه‌ی سود: بیشترین حرکت از زون (برحسب ارتفاع زون) پیش از بازگشت

    def low(self): return min(self.proximal, self.distal)
    def high(self): return max(self.proximal, self.distal)

def build_zones(df, symbol, tf, max_base_len, atr_s, legout_clear=None, weak_out=None,
                measure_departure=True):
    """بیس‌ها (زون‌ها) با کنسالیدیشن اوی.
    weak_out: اگر فهرست باشد، بیس‌هایی که کنسالیدیشن اوی ندادند هم (با oe=False) به آن اضافه می‌شوند —
              فقط برای «بیس‌های چسبیده» در تأیید چاک؛ روی پیدا شدن بیس‌های اصلی اثری ندارد.
    measure_departure: False = «حاشیه‌ی سود» حساب نشود (برای تایم ۱دقیقه؛ سریع‌تر)."""
    # ستون‌ها یک بار به آرایه‌ی numpy تبدیل می‌شوند. قوانین عوض نشده‌اند؛ فقط
    # به‌جای خواندن سطربه‌سطر از pandas (که در حلقه‌ی تودرتو بسیار کند است)
    # همان شرط‌ها روی آرایه محاسبه می‌شوند.
    o = df["open"].to_numpy(dtype=float)
    h = df["high"].to_numpy(dtype=float)
    l = df["low"].to_numpy(dtype=float)
    c = df["close"].to_numpy(dtype=float)
    times = df["time"].to_numpy()
    atr_a = np.asarray(atr_s, dtype=float)
    n = len(df)

    rng = h - l
    body = np.abs(c - o)
    with np.errstate(invalid="ignore", divide="ignore"):
        ratio = np.where(rng > 0, body / rng, np.inf)
    is_base_a = (rng > 0) & (body <= 0.5 * rng)                       # is_base_candle
    is_strong_a = (rng > 0) & (body > 0.5 * rng)                      # strong_close
    atr_ok = np.isfinite(atr_a) & (atr_a > 0)
    is_doji_a = (rng > 0) & atr_ok & (ratio <= 0.20) & (rng <= 0.80 * atr_a)   # is_doji_small
    body_max = np.maximum(o, c)
    body_min = np.minimum(o, c)

    zones=[]
    i=0
    while i < n-3:
        made=None
        for L in range(1, max_base_len+1):
            if i+L >= n: break
            if not is_base_a[i:i+L].all():
                break

            base_high=float(h[i:i+L].max())
            base_low =float(l[i:i+L].min())

            j = i+L
            if not is_strong_a[j]:
                continue

            bull = c[j] > base_high
            bear = c[j] < base_low
            if not (bull or bear):
                continue

            doji_shadow = bool(is_doji_a[i:i+L].all())

            if bull:
                direction="BUY"
                if doji_shadow:
                    proximal=base_high
                    distal=base_low
                else:
                    proximal=float(body_max[i:i+L].max())
                    distal=float(base_low)
            else:
                direction="SELL"
                if doji_shadow:
                    proximal=base_low
                    distal=base_high
                else:
                    proximal=float(body_min[i:i+L].min())
                    distal=float(base_high)

            # کنسالیدیشن اوی: تا legout_clear کندل (از کندل خروج)، یک کندل باید کامل بیرون از بیس
            # تشکیل شود — حتی سایه‌اش به پراکسیمال نخورد. زون از بسته شدن همان کندل معتبر است.
            lc = LEGOUT_CLEAR_BARS if legout_clear is None else legout_clear
            born = j
            if lc:
                born = None
                for k2 in range(j, min(j + lc, n)):
                    if (direction == "BUY" and l[k2] > proximal) or (direction == "SELL" and h[k2] < proximal):
                        born = k2
                        break
                if born is None:
                    if weak_out is not None:
                        wz = Zone(symbol, tf, direction, proximal, distal, times[j], times[i], times[j-1],
                                  doji_shadow)
                        wz.oe = False
                        weak_out.append(wz)
                    break                 # این بیس معتبر نیست

            z=Zone(symbol, tf, direction, proximal, distal,
                   times[born], times[i], times[j-1], doji_shadow)

            # --- معیارهای کیفیت زون (به سبک Odds Enhancers) ---
            height = z.high() - z.low()
            # ۱) قدرت خروج: بدنه‌ی کندل تأیید نسبت به ATR همان کندل
            atr_conf = atr_a[j] if j < len(atr_a) else np.nan
            z.conf_body_atr = float(body[j] / atr_conf) if (np.isfinite(atr_conf) and atr_conf > 0) else 0.0

            # ۲) حاشیه‌ی سود: قیمت پیش از بازگشت به زون، چند برابر ارتفاع زون حرکت کرده؟
            #    (کاملاً گذشته‌نگر است: تا وقتی قیمت برنگردد، معامله‌ای هم رخ نمی‌دهد)
            if height > 0 and measure_departure:
                best = 0.0
                z_hi = z.high(); z_lo = z.low()
                for k in range(j, min(j+200, n)):
                    hi_k = h[k]; lo_k = l[k]
                    if direction == "BUY":
                        best = max(best, (hi_k - z_hi) / height)
                        if lo_k <= z_hi:      # قیمت به زون برگشت → پایان اندازه‌گیری
                            if k > j:
                                break
                    else:
                        best = max(best, (z_lo - lo_k) / height)
                        if hi_k >= z_lo:
                            if k > j:
                                break
                z.departure_h = float(max(0.0, best))

            made=(L, z)
            break

        if made:
            zones.append(made[1])
            i += made[0] + 1
        else:
            i += 1
    return zones

def choch_confirm_zones(zones, df, min_body_atr=0.0, weak=None, cluster_gap_atr=None,
                        cluster_max_bars=None):
    """اعتبار بیس با «تأیید چاک» و «لگ‌اوت قوی».

    چاک = لگ‌اوتِ بیس، سقف/کفی را که «بیس مخالف خودش» ساخته با بادی (کلوز کندل) رد کند:
      دیمند: بیس مخالف = آخرین سوپلایِ شکسته‌نشده‌ی بالای بیس که پیش از شروع بیس متولد شده و
             کنسالیدیشن اوی داده. سطح چاک = بالاترین high از شروع آن سوپلای تا شروع دیمند.
      سوپلای: برعکس — آخرین دیمند زیر بیس؛ سطح چاک = پایین‌ترین low.
    بیس‌های مخالفِ چسبیده به آن (با یا بدون کنسالیدیشن اوی؛ weak = بیس‌های بدون اوی) یک بیس حساب
    می‌شوند و چاک باید پشت دورترینشان بسته شود. چسبیده = حداکثر cluster_max_bars کندل و
    cluster_gap_atr × ATR فاصله (فاصله‌ی قیمتی دو بیس یا دور شدن قیمت بینشان).
    چاک باید پیش از برگشت قیمت به بیس اتفاق بیفتد. بیس از بسته شدن دیرترینِ کندل کنسالیدیشن
    اوی و کندل چاک قابل معامله است (بدون نگاه به آینده).
    min_body_atr > 0: بدنه‌ی کندل خروج باید دست‌کم این ضریب × ATR باشد (لگ‌اوت قوی).
    زون‌های ضعیف هم می‌توانند «بیس مخالف» باشند؛ فقط خودشان قابل معامله نیستند."""
    import bisect
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
    # کندلی که هر زون در آن شکست: دیمند با کلوز زیر کفش، سوپلای با کلوز بالای سقفش
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


def overlap_ratio(a_low,a_high,b_low,b_high):
    inter=max(0.0, min(a_high,b_high)-max(a_low,b_low))
    uni=max(a_high,b_high)-min(a_low,b_low)
    return inter/uni if uni>0 else 0.0

def dedup_zones_pit(zones, thr=0.55):
    """حذف زون‌های هم‌پوشان بدون نگاه به آینده:
    هر زون جدید، زون‌های هم‌پوشانِ قبلی را فقط از «زمان ایجاد خودش» به بعد جایگزین می‌کند
    و محدوده‌اش با زون‌های قبلی (که در آن لحظه معلوم‌اند) تنگ‌تر می‌شود."""
    zones = sorted(zones, key=lambda z: z.created_time)
    active = []
    for z in zones:
        for old in active:
            if overlap_ratio(z.low(), z.high(), old.low(), old.high()) >= thr:
                old.superseded_time = z.created_time
                low = max(z.low(), old.low()); high = min(z.high(), old.high())
                if low < high:
                    if z.direction == "BUY":
                        z.proximal = high; z.distal = low
                    else:
                        z.proximal = low; z.distal = high
        active = [a for a in active if a.superseded_time is None]
        active.append(z)
    return zones

def body_overlaps_zone(o,c,z:Zone):
    bl=min(o,c); bh=max(o,c)
    return (bh >= z.low()) and (bl <= z.high())

# ---------------- Reporting helpers ----------------
def init_zone_table(h_z):
    rows=[]
    for z in h_z:
        rows.append({
            "ZoneID": z.zone_id,
            "نماد": z.symbol,
            "تایم‌فریم": z.tf,
            "جهت": "خرید" if z.direction=="BUY" else "فروش",
            "تاریخ_ایجاد": z.created_time,
            "پراکسیمال": z.proximal,
            "دیستال": z.distal,
            "بیس_شروع": z.base_start,
            "بیس_پایان": z.base_end,
            "دوجی_شدو": z.doji_shadow,
            "Touch1": None,
            "Touch2": None,
            "تعداد_تست": 0,
            "FinalStatus": "",
            "FinalReason": "",
            "FinalTime": None,
            "زمان_ثبت_سفارش": None,
            "زمان_پرشدن": None,
            "زمان_خروج": None,
            "نتیجه_R": None
        })
    # اگر هیچ زونی ساخته نشده باشد، جدول باید باز هم ستون‌هایش را داشته باشد (وگرنه کرش می‌کند)
    cols = ["ZoneID", "نماد", "تایم‌فریم", "جهت", "تاریخ_ایجاد", "پراکسیمال", "دیستال",
            "بیس_شروع", "بیس_پایان", "دوجی_شدو", "Touch1", "Touch2", "تعداد_تست",
            "FinalStatus", "FinalReason", "FinalTime", "زمان_ثبت_سفارش", "زمان_پرشدن",
            "زمان_خروج", "نتیجه_R"]
    return pd.DataFrame(rows, columns=cols)

def zone_row_index(zone_df):
    """نگاشت ZoneID به شماره‌ی سطر — تا جست‌وجوی زون O(1) شود.

    قبلاً هر بار کل ستون ZoneID با zid مقایسه می‌شد؛ با هزاران زون و ده‌ها هزار
    رویداد، همین یک کار بخش بزرگی از زمان اجرا را می‌خورد.
    """
    return {z: k for k, z in enumerate(zone_df["ZoneID"].tolist())}


def set_final(zone_df, zid, status, reason, t, idx=None):
    row = idx.get(zid) if idx is not None else None
    if row is None:
        mask = zone_df["ZoneID"]==zid
        if not mask.any(): return
        if str(zone_df.loc[mask, "FinalStatus"].iloc[0]).strip() != "":
            return
        zone_df.loc[mask, "FinalStatus"] = status
        zone_df.loc[mask, "FinalReason"] = reason
        zone_df.loc[mask, "FinalTime"] = t
        return
    cols = zone_df.columns
    cs = cols.get_loc("FinalStatus")
    if str(zone_df.iat[row, cs]).strip() != "":
        return
    zone_df.iat[row, cs] = status
    zone_df.iat[row, cols.get_loc("FinalReason")] = reason
    zone_df.iat[row, cols.get_loc("FinalTime")] = t

def log_event(events, t, symbol, zid, etype, detail=""):
    events.append({
        "زمان": t,
        "نماد": symbol,
        "ZoneID": zid,
        "نوع_رویداد": etype,
        "جزئیات": detail
    })

# ---------------- Backtest (logic unchanged; reporting upgraded) ----------------
class AccountBook:
    """حساب مشترک همه‌ی نمادها در حالت «عین لایو».

    اکویتی، تعداد پوزیشن باز کل حساب و افت سرمایه اینجا نگه داشته می‌شود تا همه‌ی
    نمادها روی یک حساب واقعی معامله کنند — نه هرکدام روی حساب فرضی خودش.
    """

    def __init__(self, start_equity=100000.0, reserve=0.15, risk_per_trade=0.005,
                 session_weights=None, max_open_total=8):
        self.equity = float(start_equity)
        self.start_equity = float(start_equity)
        self.peak = float(start_equity)
        self.max_dd = 0.0
        self.reserve = float(reserve)
        self.risk_per_trade = float(risk_per_trade)
        self.session_weights = session_weights or {}
        self.max_open_total = int(max_open_total) if max_open_total and max_open_total > 0 else 10 ** 9
        self.open_total = 0
        self.equity_curve = []   # (زمان، اکویتی) بعد از هر معامله‌ی بسته‌شده

    def session_weight(self, t):
        if not self.session_weights:
            return 1.0
        try:
            hr = (pd.Timestamp(t).hour + SESSION_HOUR_SHIFT) % 24
        except Exception:
            return 1.0
        return float(self.session_weights.get(hour_to_session(hr), 1.0))

    def risk_amount(self, t):
        return self.equity * (1.0 - self.reserve) * self.risk_per_trade * self.session_weight(t)

    def apply_result(self, t, risk_amt, result_r):
        self.equity += float(risk_amt) * float(result_r)
        self.peak = max(self.peak, self.equity)
        if self.peak > 0:
            self.max_dd = max(self.max_dd, (self.peak - self.equity) / self.peak)
        self.equity_curve.append((t, self.equity))


def _backtest_core(symbol, h4, d1, w1, years, spread,
                   entry_off=0.10, sl_off=0.25, rr=3.0,
                   reserve=0.15, risk_per_trade=0.01, max_orders=3,
                   m15=None, min_risk_atr=0.0, dist_cancel_r=0.0, manage_mode="none",
                   max_open_per_symbol=0,
                   invalidate_on_breach=False, min_profit_margin_r=0.0, min_departure_atr=0.0,
                   retry_rejected_zones=False, return_state=False,
                   book=None, alloc_mode=False, arm_untouched_zones=False,
                   min_risk_spread=0.0, min_room_r=0.0, htf_location=False, trend_mode=None,
                   ltf_mode=None):
    """موتور استراتژی برای یک نماد — به‌صورت generator.

    ltf_mode (تأیید ۱دقیقه): None = سفارش لیمیت روی بیس ۱۵دقیقه (روش فعلی) |
      "zone" = قیمت به بیس برسد، چاک ۱دقیقه در جهت بیس بیاید، بعد اوردر روی همان بیس ۱۵دقیقه |
      "base" = همان، ولی اوردر روی بیس ۱دقیقه‌ای که چاک را ساخت (ورود/استاپ/تارگت با همان درصدها).

    در هر کندل، درست سر جایی که ربات لایو تصمیم می‌گیرد کدام سفارش‌ها روی حساب
    بمانند، این تابع «فهرست خواسته‌هایش» را yield می‌کند و منتظر می‌ماند تا راننده
    (portfolio_live_replay) بگوید چند سهمیه گرفته است. اگر alloc_mode خاموش باشد
    هیچ‌وقت yield نمی‌کند و رفتارش دقیقاً مثل قبل است.
    """

    bt_start = BACKTEST_START
    # گرم‌کردن: زون‌ها/روند/ATR از WARMUP_DAYS قبل ساخته می‌شوند؛ معامله فقط از bt_start
    warm_start = bt_start - pd.Timedelta(days=WARMUP_DAYS)

    # تایم بزرگ (روزانه/هفتگی) اختیاری است؛ اگر نباشد زون بزرگ و فیبو ندارد
    big_enabled = w1 is not None
    if w1 is None:
        w1 = d1
    h4 = h4.copy(); d1 = d1.copy(); w1 = w1.copy()
    for df in (h4, d1, w1):
        df["open"]=df["open"].astype(float)
        df["high"]=df["high"].astype(float)
        df["low"]=df["low"].astype(float)
        df["close"]=df["close"].astype(float)

    # ATR warmup روی کل دیتا
    h4["atr"] = atr(h4)
    d1["atr"] = atr(d1)
    w1["atr"] = atr(w1)

    # برش انتهای بازه‌ی بک‌تست (اگر BACKTEST_END تنظیم شده باشد)
    if BACKTEST_END is not None:
        h4 = h4[h4["time"] <= BACKTEST_END].copy()
        d1 = d1[d1["time"] <= BACKTEST_END].copy()
        w1 = w1[w1["time"] <= BACKTEST_END].copy()
        if m15 is not None:
            m15 = m15[m15["time"] <= BACKTEST_END].copy()

    # کات اولیه (برای منطق، نه ATR) — از شروع گرم‌کردن
    h4_ = h4[h4["time"] >= warm_start].copy()
    d1_ = d1[d1["time"] >= warm_start].copy()
    w1_ = w1[w1["time"] >= warm_start].copy()

    if h4_.empty or d1_.empty or w1_.empty:
        metrics_df = pd.DataFrame([{
            "نماد":symbol,"تعداد":0,"درصد_برد":0.0,"فاکتور_سود":0.0,
            "بازده_خالص٪":0.0,"حداکثر_افت٪":0.0,"میانگین_R":0.0
        }])
        reasons_df = pd.DataFrame([{"نماد":symbol,"دلیل":"دیتا ناکافی بعد از 2023", "تعداد":1}])
        return metrics_df, reasons_df, pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    # شروع واقعی بک‌تست = جایی که هر سه تایم‌فریم بعد از 2023 دیتا دارند
    global_start = max(warm_start, h4_["time"].min(), d1_["time"].min(), w1_["time"].min())

    h4 = h4[h4["time"] >= global_start].reset_index(drop=True)
    d1 = d1[d1["time"] >= global_start].reset_index(drop=True)
    w1 = w1[w1["time"] >= global_start].reset_index(drop=True)

    if h4.empty or d1.empty or w1.empty:
        metrics_df = pd.DataFrame([{
            "نماد":symbol,"تعداد":0,"درصد_برد":0.0,"فاکتور_سود":0.0,
            "بازده_خالص٪":0.0,"حداکثر_افت٪":0.0,"میانگین_R":0.0
        }])
        reasons_df = pd.DataFrame([{"نماد":symbol,"دلیل":"دیتا ناکافی بعد از sync", "تعداد":1}])
        return metrics_df, reasons_df, pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    # range/trend روی دیتای کات‌شده
    h4["range"] = range_filter(h4, h4["atr"])
    d1["range"] = range_filter(d1, d1["atr"])
    # روند: «legacy» = روش قدیمی ربات (سقف/کف‌های ۳ کندلی ریز) | «choch» = ساختار بازار با چاک |
    # «choch_tl» = چاک + ترندلاین (فاز فشردگی وقتی فقط ترندلاین شکسته)
    tmode = trend_mode or TREND_MODE
    if tmode == "legacy":
        h4["trend"] = trend_from_swings(h4, n=1)
        d1["trend"] = trend_from_swings(d1, n=1)
    else:
        use_tl = (tmode == "choch_tl")
        h4["trend"] = structure_trend(h4, n=STRUCT_SWING_N, use_trendline=use_tl, tl_n=TL_SWING_N)
        d1["trend"] = structure_trend(d1, n=STRUCT_SWING_N, use_trendline=use_tl, tl_n=TL_SWING_N)

    # طول کندل هر تایم‌فریم از خود دیتا (میانه‌ی فاصله‌ی کندل‌ها) — برای دسته‌ی H4 همان
    # ۴ ساعت، ۱ روز و ۷ روز است؛ برای دسته‌ی M15 می‌شود ۱۵ دقیقه، ۱ ساعت و ۴ ساعت.
    def _span(df, default):
        dd = df["time"].diff().dropna()
        return pd.Timedelta(dd.median()) if len(dd) else default
    zone_span = _span(h4, pd.Timedelta(hours=4))
    trend_span = _span(d1, pd.Timedelta(days=1))
    big_span = _span(w1, pd.Timedelta(days=7))
    _mins = int(zone_span / pd.Timedelta(minutes=1))
    zone_tf = {1: "M1", 5: "M5", 15: "M15", 30: "M30", 60: "H1", 240: "H4", 1440: "D1"}.get(_mins, f"{_mins}m")

    w_z = dedup_zones_pit(build_zones(w1, symbol, "BIG", 12, w1["atr"])) if big_enabled else []
    # بیس‌های تایم زون: کنسالیدیشن اوی (داخل build_zones) → لگ‌اوت قوی + تأیید چاک → حذف هم‌پوشان‌ها
    h_raw = build_zones(h4, symbol, zone_tf, 6,  h4["atr"])
    if CHOCH_CONFIRM:   # «بیس‌های چسبیده» فقط برای ۱دقیقه است؛ اینجا خاموش
        h_raw = choch_confirm_zones(h_raw, h4, min_body_atr=MIN_LEGOUT_BODY_ATR, cluster_gap_atr=0.0)
    elif MIN_LEGOUT_BODY_ATR > 0:
        h_raw = [z for z in h_raw if z.conf_body_atr >= MIN_LEGOUT_BODY_ATR]
    h_z = dedup_zones_pit(h_raw)

    # ZoneID
    h_z = sorted(h_z, key=lambda z: z.created_time)
    _ids_seen = {}
    for idx, z in enumerate(h_z, start=1):
        if STABLE_ZONE_IDS:
            zid = (f"{symbol}_{zone_tf}_{pd.Timestamp(z.created_time):%y%m%d%H%M}"
                   f"{'B' if z.direction == 'BUY' else 'S'}")
            k = _ids_seen.get(zid, 0) + 1          # دو زون هم‌جهت با یک زمان تولد → پسوند ۲، ۳، ...
            _ids_seen[zid] = k
            z.zone_id = zid if k == 1 else f"{zid}{k}"
        else:
            z.zone_id = f"{symbol}_{zone_tf}_{idx:05d}"

    # ---------- زون‌های بزرگ به‌صورت آرایه (سرعت) ----------
    # «معتبر در لحظه‌ی t» = کندل تأییدش بسته شده (created + big_span <= t) و هنوز جایگزین نشده.
    # قبلاً در هر کندل کل فهرست با محاسبه‌ی کُند تاریخ گشته می‌شد؛ نتیجه دقیقاً همان است.
    _NEVER = np.datetime64("2262-01-01", "ns")
    _wz_from = np.array([np.datetime64(pd.Timestamp(wz.created_time) + big_span, "ns") for wz in w_z],
                        dtype="datetime64[ns]")
    _wz_sup = np.array([np.datetime64(pd.Timestamp(wz.superseded_time), "ns") if wz.superseded_time is not None
                        else _NEVER for wz in w_z], dtype="datetime64[ns]")
    _wz_low = np.array([wz.low() for wz in w_z], dtype=float)
    _wz_high = np.array([wz.high() for wz in w_z], dtype=float)
    _wz_buy = np.array([wz.direction == "BUY" for wz in w_z], dtype=bool)

    def big_valid_mask(t_now):
        tt = np.datetime64(pd.Timestamp(t_now), "ns")
        return (_wz_from <= tt) & (tt < _wz_sup)

    def big_body_hits(t_now, o_, c_):
        """بدنه‌ی کندل (o_, c_) با یک زون بزرگِ معتبر تقاضا/عرضه برخورد دارد؟ → {"BUY": .., "SELL": ..}"""
        if not len(w_z):
            return {"BUY": False, "SELL": False}
        m = big_valid_mask(t_now) & (max(o_, c_) >= _wz_low) & (min(o_, c_) <= _wz_high)
        return {"BUY": bool((m & _wz_buy).any()), "SELL": bool((m & ~_wz_buy).any())}

    # ---------- فیلترهای آزمایش طراحی (پیش‌فرض همه خاموش؛ ربات لایو را عوض نمی‌کنند) ----------
    # اسپرد مرجع برای «حداقل اندازه‌ی زون»: ربات لایو اسپرد را صفر می‌دهد، پس از جدول خوانده می‌شود
    spread_ref = float(spread) if float(spread) > 0 else float(SPREAD_TABLE.get(symbol, 0.0))
    risk_h = 1.0 + entry_off + sl_off            # فاصله‌ی ورود تا استاپ برحسب ارتفاع زون

    # محل زون روی تایم بالاتر: برای هر زون H4، زون‌های روزانه/هفتگیِ هم‌جهتی که با آن هم‌پوشانی دارند
    htf_overlaps = {}
    d_z = dedup_zones_pit(build_zones(d1, symbol, "TREND", 6, d1["atr"])) \
        if (htf_location or HTF_ZONE_FILTER or OPP_ZONE_ROOM_R > 0
            or (MAX_CONSECUTIVE_CP and CP_ON_TREND_TF)) else []
    if htf_location:
        htf_all = [(hz, trend_span) for hz in d_z] + [(hz, big_span) for hz in w_z]
        for z in h_z:
            htf_overlaps[id(z)] = [(hz, lag) for hz, lag in htf_all
                                   if hz.direction == z.direction
                                   and z.low() <= hz.high() and z.high() >= hz.low()]

    def htf_ok(z, t_now):
        """زون H4 روی یک زون روزانه/هفتگیِ هم‌جهت و معتبر (کندل تأییدش بسته شده) قرار دارد؟"""
        for hz, lag in htf_overlaps.get(id(z), ()):
            if hz.created_time + lag <= t_now and (hz.superseded_time is None or t_now < hz.superseded_time):
                return True
        return False

    def room_levels(t_now, ref_price, zones_k):
        """نزدیک‌ترین زون عرضه‌ی بالای قیمت و نزدیک‌ترین زون تقاضای زیر قیمت (H4 و هفتگی).
        زون مخالفی که قیمت از آن عبور کرده (آن طرف قیمت است) حساب نمی‌شود.
        zones_k: شماره‌ی زون‌های زنده (باطل‌نشده) در h_z."""
        sup_low = dem_high = None
        zk = np.asarray(zones_k, dtype=np.int64)
        if len(zk):
            m = _Z_SUP[zk] > pd.Timestamp(t_now).value
            s_ = m & ~_Z_BUY[zk] & (_Z_LO[zk] >= ref_price)
            if s_.any():
                sup_low = float(_Z_LO[zk][s_].min())
            b_ = m & _Z_BUY[zk] & (_Z_HI[zk] <= ref_price)
            if b_.any():
                dem_high = float(_Z_HI[zk][b_].max())
        if len(w_z):
            m = big_valid_mask(t_now)
            s_ = m & ~_wz_buy & (_wz_low >= ref_price)
            if s_.any():
                v = float(_wz_low[s_].min())
                sup_low = v if sup_low is None else min(sup_low, v)
            b_ = m & _wz_buy & (_wz_high <= ref_price)
            if b_.any():
                v = float(_wz_high[b_].max())
                dem_high = v if dem_high is None else max(dem_high, v)
        return sup_low, dem_high

    # ---------- قوانین استراتژی (روش دستی) ----------
    # ۱) فیلتر تایم بالا: زون‌های روزانه و هفتگیِ معتبر (کندل تأییدشان بسته شده، جایگزین نشده و
    #    هنوز با کلوز کندلِ همان تایم از دیستال‌لاینشان رد نشده‌اند)
    def _htf_arrays(zs, lag, tf_df):
        n_ = len(zs)
        f_ = np.empty(n_, dtype="datetime64[ns]")
        u_ = np.empty(n_, dtype="datetime64[ns]")
        tt = tf_df["time"].to_numpy(dtype="datetime64[ns]")
        cc = tf_df["close"].to_numpy(dtype=float)
        lag64 = np.timedelta64(pd.Timedelta(lag).value, "ns")
        for q, hz in enumerate(zs):
            f_[q] = np.datetime64(pd.Timestamp(hz.created_time) + lag, "ns")
            end = (np.datetime64(pd.Timestamp(hz.superseded_time), "ns") if hz.superseded_time is not None
                   else np.datetime64("2262-01-01", "ns"))
            # اولین کندلِ بسته‌شده‌ی بعد از تولد که آن طرف دیستال بسته شده → زون از آن به بعد باطل
            k0 = int(np.searchsorted(tt, f_[q], side="left"))
            if k0 < len(tt):
                bad = (cc[k0:] < hz.low()) if hz.direction == "BUY" else (cc[k0:] > hz.high())
                if bad.any():
                    end = min(end, tt[k0 + int(np.argmax(bad))] + lag64)
            u_[q] = end
        return (f_, u_, np.array([hz.low() for hz in zs], dtype=float),
                np.array([hz.high() for hz in zs], dtype=float),
                np.array([hz.direction == "BUY" for hz in zs], dtype=bool))

    if (HTF_ZONE_FILTER or OPP_ZONE_ROOM_R > 0) and (len(d_z) or len(w_z)):
        _a = _htf_arrays(d_z, trend_span, d1)
        _b = _htf_arrays(w_z, big_span, w1)
        _hz_from, _hz_until, _hz_lo, _hz_hi, _hz_buy = (np.concatenate([x, y]) for x, y in zip(_a, _b))
    else:
        _hz_from = None

    def opp_room_block(direction, entry_price, risk_price, t_now):
        """نزدیک زون مخالف ۴ساعته/روزانه نباشیم: فاصله‌ی ورود تا نزدیک‌ترین زون مخالفِ معتبر
        (در مسیر تارگت) باید دست‌کم OPP_ZONE_ROOM_R برابر ریسک باشد."""
        if _hz_from is None or OPP_ZONE_ROOM_R <= 0 or risk_price <= 0:
            return False
        tt = np.datetime64(pd.Timestamp(t_now), "ns")
        m = (_hz_from <= tt) & (tt < _hz_until)
        if direction == "BUY":
            s_ = m & ~_hz_buy & (_hz_lo > entry_price)
            return bool(s_.any()) and (float(_hz_lo[s_].min()) - entry_price) < OPP_ZONE_ROOM_R * risk_price
        s_ = m & _hz_buy & (_hz_hi < entry_price)
        return bool(s_.any()) and (entry_price - float(_hz_hi[s_].max())) < OPP_ZONE_ROOM_R * risk_price

    def htf_zone_block(direction, price, t_now):
        """قیمت داخل دیمند تایم بالا → سل ممنوع | داخل سوپلای تایم بالا → بای ممنوع"""
        if _hz_from is None or price is None:
            return False
        tt = np.datetime64(pd.Timestamp(t_now), "ns")
        m = (_hz_from <= tt) & (tt < _hz_until) & (_hz_lo <= price) & (price <= _hz_hi)
        return bool((m & _hz_buy).any()) if direction == "SELL" else bool((m & ~_hz_buy).any())

    # ۲) فیبوی آخرین سوئینگ هفتگی (فقط هفته‌های بسته‌شده)
    if FIB_FILTER and big_enabled and len(w1):
        _fib_lo, _fib_hi = weekly_fib_range(w1, n=FIB_SWING_N)
        _fib_t = (w1["time"] + big_span).to_numpy(dtype="datetime64[ns]")   # زمان بسته شدن هر هفته
    else:
        _fib_lo = None

    def fib_block(direction, entry_price, t_now):
        if _fib_lo is None:
            return False
        k = int(np.searchsorted(_fib_t, np.datetime64(pd.Timestamp(t_now), "ns"), side="right")) - 1
        if k < 0 or not np.isfinite(_fib_lo[k]) or _fib_hi[k] <= _fib_lo[k]:
            return False
        frac = (entry_price - _fib_lo[k]) / (_fib_hi[k] - _fib_lo[k])
        return frac > FIB_BUY_MAX if direction == "BUY" else frac < FIB_SELL_MIN

    # ۳) سی‌پی‌های پشت‌سرهم (روی تایم روند یا تایم بیس): هنگام تولد هر زون، چند زونِ هم‌جهت پشت‌سرهم
    #    (بدون زون مخالف بینشان) تا آن لحظه ساخته شده؛ زونی که جای زون قبلی را گرفته دوبار شمرده نمی‌شود
    _cp_zs = d_z if (CP_ON_TREND_TF and len(d_z)) else h_z
    _cp_lag = trend_span if _cp_zs is d_z and _cp_zs is not h_z else pd.Timedelta(0)
    _cp_zs = sorted(_cp_zs, key=lambda z: z.created_time)
    _cp_t = np.array([np.datetime64(pd.Timestamp(z.created_time) + _cp_lag, "ns") for z in _cp_zs],
                     dtype="datetime64[ns]")
    _cp_run = np.zeros(len(_cp_zs), dtype=int)
    _seq = []
    for q, z in enumerate(_cp_zs):
        ct = z.created_time
        _seq = [r for r in _seq if not (_cp_zs[r].superseded_time is not None and _cp_zs[r].superseded_time <= ct)]
        _seq = (_seq + [q])[-60:]
        run = 0
        for r in reversed(_seq):
            if _cp_zs[r].direction != z.direction:
                break
            run += 1
        _cp_run[q] = run

    def cp_block(direction, t_now):
        if not MAX_CONSECUTIVE_CP or not len(_cp_zs):
            return False
        k = int(np.searchsorted(_cp_t, np.datetime64(pd.Timestamp(t_now), "ns"), side="left")) - 1
        return k >= 0 and _cp_zs[k].direction == direction and _cp_run[k] >= MAX_CONSECUTIVE_CP

    def design_block(z, levels, t_now, price=None):
        """قوانین استراتژی + فیلترهای آزمایش طراحی؛ خروجی None = قبول، وگرنه کلید دلیل رد.
        price = قیمت لحظه‌ی تصمیم (برای فیلتر تایم بالا)."""
        height = z.high() - z.low()
        risk = height * risk_h
        ent_ = z.proximal + entry_off * height if z.direction == "BUY" else z.proximal - entry_off * height
        if cp_block(z.direction, t_now):
            return "رد_به_خاطر_سه_سی‌پی_پشت‌سرهم"
        if FIB_FILTER and fib_block(z.direction, ent_, t_now):
            return "رد_به_خاطر_فیبوی_هفتگی"
        if HTF_ZONE_FILTER and htf_zone_block(z.direction, price, t_now):
            return "رد_به_خاطر_زون_مخالف_تایم_بالا"
        if OPP_ZONE_ROOM_R > 0 and opp_room_block(z.direction, ent_, risk, t_now):
            return "رد_به_خاطر_نزدیکی_زون_مخالف"
        if min_risk_spread > 0 and spread_ref > 0 and risk < min_risk_spread * spread_ref:
            return "رد_به_خاطر_استاپ_کوچک_نسبت_به_اسپرد"
        if htf_location and not htf_ok(z, t_now):
            return "رد_به_خاطر_محل_زون_تایم_بالا"
        if min_room_r > 0 and levels is not None:
            sup_low, dem_high = levels
            if z.direction == "BUY":
                ent = z.proximal + entry_off * height
                if sup_low is not None and sup_low - ent < min_room_r * risk:
                    return "رد_به_خاطر_جای_کم_تا_زون_مخالف"
            else:
                ent = z.proximal - entry_off * height
                if dem_high is not None and ent - dem_high < min_room_r * risk:
                    return "رد_به_خاطر_جای_کم_تا_زون_مخالف"
        return None

    def armed_quality_ok(z, levels, t_now, atr_ref, price=None):
        """فیلترهای کیفیت برای زون‌های لمس‌نشده‌ای که از قبل سفارش می‌گیرند
        (قبلاً فیلترهای کیفیت فقط روی زون‌های لمس‌شده اعمال می‌شد و سفارش‌های از پیش
        چیده بدون فیلتر پر می‌شدند). حاشیه‌ی سود (min_profit_margin_r) اینجا حساب نمی‌شود
        چون قبل از لمس، بخشی از آن از آینده می‌آید."""
        if min_departure_atr > 0 and z.conf_body_atr < min_departure_atr:
            return False
        if min_risk_atr > 0 and (pd.isna(atr_ref) or (z.high() - z.low()) * risk_h < min_risk_atr * float(atr_ref)):
            return False
        return design_block(z, levels, t_now, price) is None

    zone_df = init_zone_table(h_z)
    z_idx = zone_row_index(zone_df)          # ZoneID → شماره‌ی سطر (جست‌وجوی O(1))
    _zcols = {cname: k for k, cname in enumerate(zone_df.columns)}

    def _zset(zid, col, val):
        r = z_idx.get(zid)
        if r is not None:
            zone_df.iat[r, _zcols[col]] = val

    events = []

    d_times = d1["time"].values
    def last_idx_leq(times, t):
        return np.searchsorted(times, t, side="right") - 1

    equity=100000.0; peak=equity; max_dd=0.0
    pending=[]    # سفارش در انتظار
    open_pos=[]   # پوزیشن باز
    trades=[]

    reasons={
        "زون_چهارساعته_کل": len(h_z),
        "رد_به_خاطر_رنج": 0,
        "رد_به_خاطر_روند": 0,
        "رد_به_خاطر_زون_کوچک": 0,
        "رد_به_خاطر_سقف_سفارش": 0,
        "رد_به_خاطر_سقف_پوزیشن_نماد": 0,
        "لغو_به_خاطر_سهمیه_کل_حساب": 0,
        "رد_به_خاطر_سقف_پوزیشن_کل_حساب": 0,
        "لغو_به_خاطر_هفتگی": 0,
        "لغو_به_خاطر_دور_شدن": 0,
        "لغو_به_خاطر_تست_سوم": 0,
        "لغو_سفارشِ_زون_باطل": 0,
        "باطل_شدن_زون_شکسته": 0,
        "رد_به_خاطر_حاشیه_سود_کم": 0,
        "رد_به_خاطر_خروج_ضعیف": 0,
        "لغو_به_خاطر_رنج_یا_روند_لحظه_ورود": 0,
        "انقضا_زون": 0,
        "جایگزینی_زون": 0,
        "ورود_انجام_شد": 0,
        "خروج_همزمان_بدون_M15_استاپ_فرض": 0,
        "کندل_ورود_با_تایم_پایین": 0,
        "کندل_ورود_با_حدس_مسیر": 0,
        "کندل_های_حل_شده_با_تایم_پایین": 0,
        "TP_کندل_ورود_بدون_M15": 0,
        "تعویق_سفارش_لمس_همین_کندل": 0,
        "رد_به_خاطر_عبور_قیمت_از_ورود": 0,
        "رد_به_خاطر_استاپ_کوچک_نسبت_به_اسپرد": 0,
        "رد_به_خاطر_محل_زون_تایم_بالا": 0,
        "رد_به_خاطر_جای_کم_تا_زون_مخالف": 0,
        "رد_به_خاطر_سه_سی‌پی_پشت‌سرهم": 0,
        "رد_به_خاطر_فیبوی_هفتگی": 0,
        "رد_به_خاطر_زون_مخالف_تایم_بالا": 0,
        "رد_به_خاطر_نزدیکی_زون_مخالف": 0,
        "لغو_شکست_بیس_با_کلوز_۱۵دقیقه": 0,
        "رسیدن_به_بیس_۱۵دقیقه": 0,
        "تأیید_چاک_۱دقیقه": 0,
        "ورود_بازار_بعد_از_تأیید": 0,
        "لغو_دور_شدن_بدون_ورود": 0,
        "لغو_استاپ_۱دقیقه_کوچک": 0,
    }

    # اسپرد (برحسب قیمت) برای مدل Bid/Ask: خرید لیمیت با Ask پر می‌شود و فروش با Ask بسته می‌شود
    spr = float(spread) if MODEL_BID_ASK else 0.0

    # --- آماده‌سازی تایم‌فریم پایین‌تر (M1/M5/M15) برای دیدن ترتیب اتفاقات داخل کندل H4 ---
    m15_t = m15_o = m15_h = m15_l = m15_c = None
    if USE_M15 and m15 is not None and not m15.empty:
        m15_t = m15["time"].values
        m15_o = m15["open"].astype(float).values
        m15_h = m15["high"].astype(float).values
        m15_l = m15["low"].astype(float).values
        m15_c = m15["close"].astype(float).values

    H4_SPAN = np.timedelta64(zone_span.value, "ns")     # طول کندل تایم زون

    # ---------- تأیید ۱دقیقه: بیس‌های ۱دقیقه‌ای که چاک داده‌اند (همان قوانین بیس ۱۵دقیقه) ----------
    ltf_on = bool(ltf_mode) and m15_t is not None
    conf_at = {}
    if ltf_on:
        _m1 = pd.DataFrame({"time": m15["time"].values, "open": m15_o, "high": m15_h,
                            "low": m15_l, "close": m15_c})
        _m1["atr"] = atr(_m1)
        _wk1 = []
        _z1 = build_zones(_m1, symbol, "LTF", 6, _m1["atr"], weak_out=_wk1, measure_departure=False)
        _z1 = choch_confirm_zones(_z1, _m1, min_body_atr=MIN_LEGOUT_BODY_ATR, weak=_wk1)
        _L_buy = np.array([z1.direction == "BUY" for z1 in _z1], dtype=bool)
        _L_lo = np.array([z1.low() for z1 in _z1], dtype=float)
        _L_hi = np.array([z1.high() for z1 in _z1], dtype=float)
        _L_prox = np.array([z1.proximal for z1 in _z1], dtype=float)
        _L_dist = np.array([z1.distal for z1 in _z1], dtype=float)
        _L_be = np.array([np.searchsorted(m15_t, np.datetime64(pd.Timestamp(z1.base_end), "ns")) for z1 in _z1],
                         dtype=np.int64)
        _L_z = _z1
        for q1, z1 in enumerate(_z1):        # کندل ۱دقیقه‌ای که چاک در آن بسته شد → بیس‌ها
            j_ = int(np.searchsorted(m15_t, np.datetime64(pd.Timestamp(z1.created_time), "ns")))
            conf_at.setdefault(j_, []).append(q1)

    def _m15_range(t_bar):
        if m15_t is None:
            return None
        t0 = t_bar.to_datetime64()
        i0 = int(np.searchsorted(m15_t, t0, side="left"))
        i1 = int(np.searchsorted(m15_t, t0 + H4_SPAN, side="left"))
        if i1 <= i0:
            return None
        return i0, i1

    def entry_bar_fav(direction, entry, o_, h_, l_, c_):
        """بهترین قیمتی که «بعد از پر شدن» در کندل ورود می‌شود رویش حساب کرد.

        سفارش لیمیت وقتی پر می‌شود که قیمت خلاف جهت معامله به ورود برسد؛ پس سقف
        (برای خرید) یا کف (برای فروش) کندل ممکن است قبل از پر شدن بوده باشد.
          path: صعودی O→L→H→C ، نزولی O→H→L→C  |  pessimistic: فقط کلوز  |  optimistic: کل کندل
        """
        if ENTRY_BAR_MODE == "optimistic":
            return None
        if direction == "BUY":
            if ENTRY_BAR_MODE == "path" and c_ >= o_:
                return h_                      # اول کف (پر شدن) بعد سقف
            return max(c_, entry)              # سقف قبل از پر شدن بوده؛ بعدش فقط تا کلوز
        if ENTRY_BAR_MODE == "path" and c_ <= o_:
            return l_                          # اول سقف (پر شدن) بعد کف
        return min(c_, entry)

    def walk_lower_tf(pos, t_bar, entry_bar):
        """یک کندل H4 را روی کندل‌های تایم‌فریم پایین‌تر جلو می‌برد.
        خروجی مثل process_pos_candle؛ None یعنی دیتای پایین‌تر برای این کندل نیست
        (یا در کندل ورود، لحظه‌ی پر شدن در آن پیدا نشد) و باید از خود H4 استفاده شود."""
        rng = _m15_range(t_bar)
        if rng is None:
            return None
        j0 = rng[0]
        if entry_bar:
            ent = pos["eff_entry"]
            jf = None
            for j in range(rng[0], rng[1]):
                if (pos["direction"] == "BUY" and m15_l[j] + spr <= ent) or \
                   (pos["direction"] == "SELL" and m15_h[j] >= ent):
                    jf = j
                    break
            if jf is None:
                return None
            fav = entry_bar_fav(pos["direction"], ent, m15_o[jf], m15_h[jf], m15_l[jf], m15_c[jf])
            ex = process_pos_candle(pos, m15_h[jf], m15_l[jf], t_bar, fav=fav)
            if ex[0]:
                return ex
            j0 = jf + 1
        for j in range(j0, rng[1]):
            ex = process_pos_candle(pos, m15_h[j], m15_l[j], t_bar)
            if ex[0]:
                return ex
        return False, None, None

    def step_position(pos, o_, h_, l_, c_, t_bar, entry_bar=False):
        """خروج/مدیریت یک پوزیشن در یک کندل H4 — با تایم پایین اگر باشد، وگرنه H4."""
        if m15_t is not None:
            ex = walk_lower_tf(pos, t_bar, entry_bar)
            if ex is not None:
                reasons["کندل_های_حل_شده_با_تایم_پایین"] += 1
                if entry_bar:
                    reasons["کندل_ورود_با_تایم_پایین"] += 1
                return ex
        if entry_bar:
            reasons["کندل_ورود_با_حدس_مسیر"] += 1
            fav = entry_bar_fav(pos["direction"], pos["eff_entry"], o_, h_, l_, c_)
            return process_pos_candle(pos, h_, l_, t_bar, fav=fav)
        return process_pos_candle(pos, h_, l_, t_bar)

    # هزینه‌های تقریبی این نماد (برحسب قیمت)
    commission_cost = COMMISSION_SPREAD_MULT * float(spread)
    swap_per_night = SWAP_SPREAD_MULT_PER_NIGHT * float(spread)

    def make_order(z:Zone, t_now, test_no):
        height = z.high()-z.low()
        if height<=0: height=1e-9
        # ورود = پراکسیمال + entry_off × ارتفاع بیس، به سمت قیمت.
        # entry_off مثبت = بیرون زون نزدیک قیمت (جبران اسپرد)، منفی = داخل زون دورتر از قیمت.
        # اسپرد جداگانه دوباره حساب نمی‌شود.
        if z.direction=="BUY":
            entry = z.proximal + entry_off*height
            sl    = z.distal  - sl_off*height
            eff_entry = entry
            risk = eff_entry - sl
            tp = eff_entry + rr*risk
        else:
            entry = z.proximal - entry_off*height
            sl    = z.distal  + sl_off*height
            eff_entry = entry
            risk = sl - eff_entry
            tp = eff_entry - rr*risk

        _zset(z.zone_id, "زمان_ثبت_سفارش", t_now)

        return {"z":z,"entry":float(entry),"sl":float(sl),"tp":float(tp),
                "eff_entry":float(eff_entry),"t":t_now,"test":test_no,
                "active":True,"filled":False,"fill_time":None,"cancel":None,
                "risk": float(risk)}

    _l_bar, _h_bar = [0.0], [0.0]        # کف/سقف کندل ۱۵دقیقه‌ی جاری (برای میان‌بر ltf_step)

    def ltf_cancel(p, t_now, key, why):
        p["active"] = False
        p["cancel"] = why
        reasons[key] += 1
        set_final(zone_df, p["z"].zone_id, "لغو شد", why, t_now, idx=z_idx)
        log_event(events, t_now, symbol, p["z"].zone_id, "Canceled", key)

    def ltf_open(p, t_bar, j, j1, eff_entry, in_bar_fill):
        """پوزیشن از کندل ۱دقیقه‌ی j؛ in_bar_fill = لیمیت داخل همان کندل پر شد (وگرنه ورود با کلوز j).
        بقیه‌ی همین کندل ۱۵دقیقه روی ۱دقیقه جلو می‌رود. خروجی: پوزیشن باز یا None (بسته شد)."""
        direction = p["z"].direction
        risk = (eff_entry - p["sl"]) if direction == "BUY" else (p["sl"] - eff_entry)
        if book is not None and book.open_total >= book.max_open_total:
            ltf_cancel(p, t_bar, "رد_به_خاطر_سقف_پوزیشن_کل_حساب", "لغو: سقف پوزیشن باز کل حساب پر بود")
            return None
        if risk <= 0:
            ltf_cancel(p, t_bar, "لغو_استاپ_۱دقیقه_کوچک", "لغو: استاپ نامعتبر بعد از تأیید")
            return None
        fill_t = pd.Timestamp(m15_t[j])
        p["filled"] = True; p["active"] = False; p["fill_time"] = fill_t
        reasons["ورود_انجام_شد"] += 1
        _zset(p["z"].zone_id, "زمان_پرشدن", fill_t)
        log_event(events, fill_t, symbol, p["z"].zone_id, "Filled", "")
        if book is not None:
            risk_amt = book.risk_amount(t_bar)
            book.open_total += 1
        else:
            risk_amt = equity * (1.0 - reserve) * risk_per_trade
        trigger = (eff_entry + MANAGE_TRIGGER_R * risk) if direction == "BUY" else (eff_entry - MANAGE_TRIGGER_R * risk)
        pos = {"ZoneID": p["z"].zone_id, "direction": direction, "eff_entry": float(eff_entry),
               "sl": float(p["sl"]), "tp": float(p["tp"]), "risk": float(risk), "risk_amt": float(risk_amt),
               "fill_time": fill_t, "test": p["test"], "z": p["z"], "trigger": float(trigger), "managed": False,
               "ltf": p.get("ltf")}
        if in_bar_fill:
            fav = entry_bar_fav(direction, eff_entry, m15_o[j], m15_h[j], m15_l[j], m15_c[j])
            ex = process_pos_candle(pos, m15_h[j], m15_l[j], t_bar, fav=fav)
            if ex[0]:
                finalize_trade(pos, t_bar, float(ex[1]), ex[2])
                return None
        for jj in range(j + 1, j1):
            ex = process_pos_candle(pos, m15_h[jj], m15_l[jj], t_bar)
            if ex[0]:
                finalize_trade(pos, t_bar, float(ex[1]), ex[2])
                return None
        return pos

    def ltf_step(p, t_bar):
        """یک کندل ۱۵دقیقه برای سفارشِ «تأیید ۱دقیقه» روی کندل‌های ۱دقیقه:
        armed (منتظر رسیدن قیمت به بیس) → watch (منتظر چاک ۱دقیقه) → order (اوردر لیمیت) → پوزیشن.
        خروجی: پوزیشن باز یا None."""
        buy_ = p["z"].direction == "BUY"
        if p["stage"] == "armed":
            # میان‌بر: اگر کل همین کندل ۱۵دقیقه به نقطه‌ی ورود نرسیده، کندل‌های ۱دقیقه بررسی نمی‌شوند
            if (buy_ and _l_bar[0] + spr > p["entry"]) or (not buy_ and _h_bar[0] < p["entry"]):
                return None
        rng = _m15_range(t_bar)
        if rng is None:
            return None
        j, j1 = rng
        while j < j1:
            st = p["stage"]
            if st == "armed":
                # قیمت به بیس ۱۵دقیقه رسید (همان نقطه‌ی ورود فعلی)
                if (buy_ and m15_l[j] + spr <= p["entry"]) or (not buy_ and m15_h[j] >= p["entry"]):
                    p["stage"] = "watch"
                    p["j_reach"] = j
                    reasons["رسیدن_به_بیس_۱۵دقیقه"] += 1
            elif st == "watch":
                for q1 in conf_at.get(j, ()):
                    # بیس ۱دقیقه هم‌جهت، بعد از رسیدن قیمت، و روی همان بیس ۱۵دقیقه
                    if _L_buy[q1] != buy_ or _L_be[q1] < p["j_reach"]:
                        continue
                    if (buy_ and _L_lo[q1] > p["entry"]) or (not buy_ and _L_hi[q1] < p["entry"]):
                        continue
                    reasons["تأیید_چاک_۱دقیقه"] += 1
                    log_event(events, pd.Timestamp(m15_t[j]), symbol, p["z"].zone_id, "LTF_CHoCH", "")
                    _z1c = _L_z[q1]
                    p["ltf"] = {"reach": pd.Timestamp(m15_t[p["j_reach"]]), "conf": pd.Timestamp(m15_t[j]),
                                "b0": pd.Timestamp(_z1c.base_start), "b1": pd.Timestamp(_z1c.base_end),
                                "prox": float(_z1c.proximal), "dist": float(_z1c.distal),
                                "lvl": float(getattr(_z1c, "choch_level", np.nan)),
                                "lvl_from": pd.Timestamp(getattr(_z1c, "choch_from", _z1c.base_start))}
                    if ltf_mode == "base":
                        h1 = _L_hi[q1] - _L_lo[q1]
                        if buy_:
                            ent1 = _L_prox[q1] + entry_off * h1
                            sl1 = _L_dist[q1] - sl_off * h1
                            r1 = ent1 - sl1
                            tp1 = ent1 + rr * r1
                        else:
                            ent1 = _L_prox[q1] - entry_off * h1
                            sl1 = _L_dist[q1] + sl_off * h1
                            r1 = sl1 - ent1
                            tp1 = ent1 - rr * r1
                        if r1 <= 0 or r1 < LTF_MIN_RISK_SPREAD * spread_ref:
                            ltf_cancel(p, t_bar, "لغو_استاپ_۱دقیقه_کوچک",
                                       f"لغو: استاپ بیس ۱دقیقه کمتر از {LTF_MIN_RISK_SPREAD:g} برابر اسپرد")
                            return None
                        p.update(entry=float(ent1), sl=float(sl1), tp=float(tp1), eff_entry=float(ent1),
                                 risk=float(r1))
                    p["stage"] = "order"
                    # قیمتِ لحظه‌ی تأیید از نقطه‌ی ورود گذشته؟ → لیمیت معنا ندارد، ورود با قیمت بازار
                    if (buy_ and m15_c[j] + spr <= p["entry"]) or (not buy_ and m15_c[j] >= p["entry"]):
                        reasons["ورود_بازار_بعد_از_تأیید"] += 1
                        return ltf_open(p, t_bar, j, j1, m15_c[j] + spr if buy_ else m15_c[j], False)
                    break
            else:  # order
                if (buy_ and m15_l[j] + spr <= p["entry"]) or (not buy_ and m15_h[j] >= p["entry"]):
                    return ltf_open(p, t_bar, j, j1, p["entry"], True)
                far = (m15_h[j] >= p["entry"] + LTF_CANCEL_R * p["risk"]) if buy_ \
                    else (m15_l[j] + spr <= p["entry"] - LTF_CANCEL_R * p["risk"])
                if far:
                    ltf_cancel(p, t_bar, "لغو_دور_شدن_بدون_ورود",
                               f"لغو: قیمت {LTF_CANCEL_R:g}R دور شد و اوردر پر نشد")
                    return None
            j += 1
        return None

    def finalize_trade(pos, exit_time, exit_price, reason):
        nonlocal equity, peak, max_dd
        direction = pos["direction"]
        eff_entry = pos["eff_entry"]
        risk = pos["risk"]
        if risk <= 0:
            return

        raw_r = (exit_price - eff_entry)/risk if direction=="BUY" else (eff_entry - exit_price)/risk
        # سهم سیوسودشده (banked) + سهم باقی‌مانده (frac) — در حالت عادی: 0 و 1
        result_r = pos.get("banked", 0.0) + pos.get("frac", 1.0) * float(raw_r)

        # کسر هزینه‌های تقریبی: کمیسیون + سواپ به ازای هر شب نگهداری
        try:
            nights = max(0, int((pd.Timestamp(exit_time).normalize() - pd.Timestamp(pos["fill_time"]).normalize()).days))
        except Exception:
            nights = 0
        result_r = float(result_r) - (commission_cost + swap_per_night * nights) / risk
        # هزینه‌ی کل این معامله نسبت به ریسک: اسپرد (رفت‌وبرگشت) + کمیسیون + سواپ
        cost_r = (spread_ref + commission_cost + swap_per_night * nights) / risk

        if book is not None:
            # حساب مشترک: اکویتی و افت سرمایه در سطح کل حساب به‌روز می‌شود
            book.apply_result(exit_time, pos["risk_amt"], result_r)
            book.open_total = max(0, book.open_total - 1)
        equity += pos["risk_amt"] * float(result_r)
        peak=max(peak,equity)
        dd=(peak-equity)/peak if peak>0 else 0.0
        max_dd=max(max_dd,dd)

        z = pos["z"]
        trades.append({
            "نماد":symbol,"جهت":("خرید" if direction=="BUY" else "فروش"),
            "زمان_ورود":pos["fill_time"],"ورود":eff_entry,"حدضرر":pos["sl"],"حدسود":pos["tp"],
            "زمان_خروج":exit_time,"قیمت_خروج":float(exit_price),"نتیجه_R":float(result_r),
            "برد": (result_r>0), "علت_خروج":reason, "تست":pos["test"],
            "ZoneID": pos["ZoneID"],
            "پراکسیمال":z.proximal,"دیستال":z.distal,
            "بیس_شروع":z.base_start,"بیس_پایان":z.base_end,
            "دوجی_شدو":z.doji_shadow, "هزینه_R": float(cost_r),
            "زمان_تأیید_بیس": z.created_time,
            "سطح_چاک_بیس": float(getattr(z, "choch_level", np.nan)),
            "چاک_بیس_از": getattr(z, "choch_from", None),
            "زمان_رسیدن_به_بیس": (pos.get("ltf") or {}).get("reach"),
            "زمان_چاک_۱دقیقه": (pos.get("ltf") or {}).get("conf"),
            "_ltf": pos.get("ltf"),
        })

        _zset(pos["ZoneID"], "زمان_خروج", exit_time)
        _zset(pos["ZoneID"], "نتیجه_R", float(result_r))
        final = "پر شد: برد" if result_r>0 else "پر شد: باخت"
        set_final(zone_df, pos["ZoneID"], final, reason, exit_time, idx=z_idx)
        log_event(events, exit_time, symbol, pos["ZoneID"], "Exit", final)

    def process_pos_candle(pos, h, l, t, fav=None):
        """خروج/مدیریت یک پوزیشن در یک کندل — همیشه بدبینانه (اول استاپ).
        مدیریت (سیو سود/ریسک‌فری) وقتی سود به MANAGE_TRIGGER_R برابر ریسک برسد فعال می‌شود.

        fav: در کندل ورود، بهترین قیمتی که «بعد از پر شدن» دیده شده (entry_bar_fav)؛
             None یعنی کل کندل بعد از ورود است (کندل‌های بعدی).
        قیمت‌ها Bid هستند: خرید با Bid بسته می‌شود، فروش با Ask (= Bid + spr)."""
        direction = pos["direction"]
        sl = pos["sl"]; tp = pos["tp"]
        if direction == "BUY":
            f = h if fav is None else fav
            hit_sl = l <= sl; hit_tp = f >= tp
        else:
            f = l if fav is None else fav
            hit_sl = h + spr >= sl; hit_tp = f + spr <= tp

        # فعال‌سازی مدیریت — فقط اگر در همین کندل استاپ لمس نشده باشد (بدبینانه)
        if manage_mode != "none" and not pos.get("managed") and not hit_sl:
            trg = pos["trigger"]
            hit_trg = (f >= trg) if direction == "BUY" else (f + spr <= trg)
            if hit_trg:
                pos["managed"] = True
                if manage_mode in ("partial2", "partial2_be"):
                    # نصف حجم در 2R نقد می‌شود
                    pos["banked"] = MANAGE_TRIGGER_R * PARTIAL_CLOSE_FRAC
                    pos["frac"] = 1.0 - PARTIAL_CLOSE_FRAC
                if manage_mode in ("partial2_be", "be2"):
                    # استاپ به نقطه‌ی ورود (ریسک‌فری)
                    pos["sl"] = pos["eff_entry"]
                    sl = pos["sl"]
                    hit_sl = (l <= sl) if direction == "BUY" else (h + spr >= sl)

        if hit_sl and hit_tp:
            # ترتیب داخل همین کندل معلوم نیست → بدبینانه: اول استاپ
            reasons["خروج_همزمان_بدون_M15_استاپ_فرض"] += 1
            return True, sl, "هر دو در یک کندل: حدضرر"
        if hit_sl:
            if pos.get("managed") and manage_mode in ("partial2_be", "be2"):
                return True, sl, "سربه‌سر (ریسک‌فری)"
            return True, sl, "حدضرر"
        if hit_tp:
            return True, tp, "حدسود"
        return False, None, None

    def cancel_orders_of_zone(z, t_now, why_short, why_long):
        """سفارش‌های پرنشده‌ی یک زون را وقتی زون بی‌اعتبار می‌شود لغو می‌کند."""
        n = 0
        for p in pending:
            if p["active"] and not p["filled"] and p["z"] is z:
                p["active"] = False
                p["cancel"] = why_long
                n += 1
                log_event(events, t_now, symbol, z.zone_id, "Canceled", why_short)
        return n

    # ---------- آرایه‌های کمکیِ زون‌ها (فقط برای سرعت؛ منطق همان قبلی است) ----------
    # در تایم‌فریم ۱۵ دقیقه، زون‌های زنده به هزاران عدد می‌رسند و پیمایش پایتونیِ همه‌شان
    # در هر کندل بکتست را خیلی کند می‌کرد. حالا با numpy فقط زون‌هایی پیمایش می‌شوند که
    # در همان کندل واقعاً اتفاقی برایشان می‌افتد. خود اشیای زون همچنان مرجع اصلی‌اند.
    _nz = len(h_z)
    _NEVER = np.iinfo(np.int64).max
    _Z_LO = np.array([z.low() for z in h_z], dtype=float)
    _Z_HI = np.array([z.high() for z in h_z], dtype=float)
    _Z_DIST = np.array([z.distal for z in h_z], dtype=float)
    _Z_BUY = np.array([z.direction == "BUY" for z in h_z], dtype=bool)
    _Z_SUP = np.array([pd.Timestamp(z.superseded_time).value if z.superseded_time is not None else _NEVER
                       for z in h_z], dtype=np.int64)
    _Z_TC = np.zeros(_nz, dtype=np.int64)            # = touch_count
    _Z_LTI = np.full(_nz, -10**9, dtype=np.int64)    # = last_touch_i (None → خیلی قدیم)
    _Z_CAT = np.full(_nz, 999, dtype=np.int64)       # = clean_after_touch
    _Z_USED = np.zeros(_nz, dtype=bool)              # = id(z) in used
    _kmap = {id(z): k for k, z in enumerate(h_z)}

    class _UsedSet(set):
        """همان مجموعه‌ی used؛ فقط آرایه‌ی _Z_USED را هم هم‌زمان به‌روز نگه می‌دارد."""
        def add(self, x):
            set.add(self, x)
            k = _kmap.get(x)
            if k is not None:
                _Z_USED[k] = True

        def discard(self, x):
            set.discard(self, x)
            k = _kmap.get(x)
            if k is not None:
                _Z_USED[k] = False

    used = _UsedSet()

    def _touch_step(z, i, t, h, l, c_prev):
        """لمس/انقضا/جایگزینی/شکست یک زون در یک کندل (بدنه‌ی قبلی حلقه، بدون تغییر)."""
        # اگر زون جدیدِ هم‌پوشان آمده باشد، این زون از همان لحظه کنار می‌رود
        if z.superseded_time is not None and t >= z.superseded_time:
            z.expired=True
            reasons["جایگزینی_زون"] += 1
            # سفارش پرنشده‌ی این زون هم باید لغو شود (زون دیگر معتبر نیست)
            reasons["لغو_سفارشِ_زون_باطل"] += cancel_orders_of_zone(
                z, t, "SupersededZone", "لغو: زون جدید هم‌پوشان جایگزین شد")
            set_final(zone_df, z.zone_id, "منقضی شد", "زون جدید هم‌پوشان جایگزین شد", t, idx=z_idx)
            log_event(events, t, symbol, z.zone_id, "Superseded", "")
            return

        # زون شکسته باطل می‌شود: کندلِ بسته‌شده‌ی قبلی آن‌سوی دیستال‌لاین بسته شده باشد
        # (زون‌هایی که قبلاً معامله یا رد شده‌اند شمرده نمی‌شوند تا آمار گمراه‌کننده نشود)
        if invalidate_on_breach and id(z) not in used:
            breached = (c_prev < z.distal) if z.direction == "BUY" else (c_prev > z.distal)
            if breached:
                z.expired = True
                reasons["باطل_شدن_زون_شکسته"] += 1
                reasons["لغو_سفارشِ_زون_باطل"] += cancel_orders_of_zone(
                    z, t, "ZoneBreached", "لغو: قیمت زون را شکست")
                set_final(zone_df, z.zone_id, "باطل شد", "قیمت از زون عبور کرد", t, idx=z_idx)
                log_event(events, t, symbol, z.zone_id, "Breached", "")
                return

        touched = (h >= z.low() and l <= z.high())
        if touched:
            if z.touch_count==0:
                z.touch_count=1; z.last_touch_i=i; z.clean_after_touch=0
                _zset(z.zone_id, "Touch1", t); _zset(z.zone_id, "تعداد_تست", 1)
                log_event(events, t, symbol, z.zone_id, "Touch1", "")
            else:
                if z.clean_after_touch>=3 and z.last_touch_i is not None and (i - z.last_touch_i) <= 50:
                    z.touch_count += 1
                    z.last_touch_i=i; z.clean_after_touch=0
                    _zset(z.zone_id, "Touch2", t); _zset(z.zone_id, "تعداد_تست", z.touch_count)
                    log_event(events, t, symbol, z.zone_id, "Touch2", f"تست={z.touch_count}")
                else:
                    z.clean_after_touch=0
        else:
            if z.touch_count>0:
                z.clean_after_touch += 1

        if z.touch_count==1 and z.last_touch_i is not None and (i - z.last_touch_i) > 50:
            z.expired=True
            reasons["انقضا_زون"] += 1
            # سفارش پرنشده‌ی زون منقضی هم لغو می‌شود
            reasons["لغو_سفارشِ_زون_باطل"] += cancel_orders_of_zone(
                z, t, "ExpiredZone", "لغو: زون منقضی شد")
            set_final(zone_df, z.zone_id, "منقضی شد", "Touch2 تا ۵۰ کندل نیامد", t, idx=z_idx)
            log_event(events, t, symbol, z.zone_id, "Expired", "")

    # ستون‌های داغِ حلقه یک بار به numpy تبدیل می‌شوند. خواندن سطربه‌سطر از pandas
    # (h4["open"].iloc[i]) هر بار یک Series می‌سازد و در ده‌ها هزار کندل، بخش
    # بزرگی از زمان اجرا را می‌خورد. مقادیر و منطق دقیقاً همان قبلی است.
    _t_a = h4["time"].to_numpy()
    _o_a = h4["open"].to_numpy(dtype=float);  _h_a = h4["high"].to_numpy(dtype=float)
    _l_a = h4["low"].to_numpy(dtype=float);   _c_a = h4["close"].to_numpy(dtype=float)
    _hrg_a = h4["range"].to_numpy();          _htr_a = h4["trend"].to_numpy()
    _drg_a = d1["range"].to_numpy();          _dtr_a = d1["trend"].to_numpy()
    _h4_atr_a = h4["atr"].to_numpy(dtype=float)

    # فقط زون‌های «به‌دنیا‌آمده و باطل‌نشده» نگه داشته می‌شوند. قبلاً در هر کندل کل
    # تاریخچه‌ی زون‌ها پیمایش می‌شد؛ با دیتای چندساله این هزینه مربعی می‌شد.
    # h_z از قبل بر اساس زمان تولد مرتب است، پس ترتیب پیمایش عوض نمی‌شود.
    _zptr = 0
    live_k = np.zeros(0, dtype=np.int64)     # شماره‌ی زون‌های زنده در h_z (به همان ترتیب تولد)

    for i in range(len(h4)):
        t=_t_a[i]

        o=float(_o_a[i]); h=float(_h_a[i])
        l=float(_l_a[i]); c=float(_c_a[i])

        di=last_idx_leq(d_times, t)
        if di<1 or i<1:
            continue

        # فیلترها فقط از کندل‌های «بسته‌شده» خوانده می‌شوند (بدون نگاه به آینده):
        # کندل H4 قبلی و آخرین کندل روزانه‌ی کامل‌شده (di-1)
        # تا وقتی فیلتر رنج «گرم» نشده (۲۰ کندل اول)، معامله ممنوع است
        if pd.isna(_drg_a[di-1]) or pd.isna(_hrg_a[i-1]):
            continue

        t = pd.Timestamp(t)
        dtr=int(_dtr_a[di-1])
        htr=int(_htr_a[i-1])

        drg=bool(_drg_a[di-1]) if RANGE_FILTER else False
        hrg=bool(_hrg_a[i-1]) if RANGE_FILTER else False
        # جهت‌های مجاز معامله در این کندل (روند روزانه و روند تایم زون باید هم‌جهت باشند و
        # جهت زون هم با روند یکی باشد؛ در فاز فشردگی هر دو جهت)
        allowed_now = dirs_allowed(dtr, htr)

        # کندل بسته‌شده‌ی قبلی برای چک‌های لغو (هفتگی و دور شدن قیمت)
        o_prev=float(_o_a[i-1]); c_prev=float(_c_a[i-1])
        h_prev=float(_h_a[i-1]); l_prev=float(_l_a[i-1])

        # ---------- exits for already-open positions ----------
        still_open=[]
        for pos in open_pos:
            exited, exit_price, reason = step_position(pos, o, h, l, c, t)
            if exited:
                finalize_trade(pos, t, float(exit_price), reason)
            else:
                still_open.append(pos)
        open_pos = still_open

        # زون‌هایی که کندل تأییدشان بسته شده، از همین‌جا وارد فهرست زنده‌ها می‌شوند
        _z0 = _zptr
        while _zptr < len(h_z) and h_z[_zptr].created_time < t:
            _zptr += 1
        if _zptr > _z0:
            live_k = np.concatenate([live_k, np.arange(_z0, _zptr, dtype=np.int64)])

        # ---------- touches + expiry (همان) ----------
        # فقط زون‌هایی که در این کندل لمس، جایگزین، شکسته یا منقضی می‌شوند پیمایش می‌شوند؛
        # برای بقیه‌ی زون‌های لمس‌شده فقط یک «کندل تمیز» به شمارشان اضافه می‌شود — دقیقاً
        # همان کاری که بدنه‌ی حلقه برایشان می‌کرد.
        _exp_k = []
        if len(live_k):
            lk = live_k
            tc = _Z_TC[lk]
            att = (h >= _Z_LO[lk]) & (l <= _Z_HI[lk])
            att |= _Z_SUP[lk] <= t.value
            if invalidate_on_breach:
                att |= np.where(_Z_BUY[lk], c_prev < _Z_DIST[lk], c_prev > _Z_DIST[lk]) & ~_Z_USED[lk]
            att |= (tc == 1) & ((i - _Z_LTI[lk]) > 50)
            _Z_CAT[lk[(~att) & (tc > 0)]] += 1
            for k in lk[att]:
                z = h_z[k]
                z.clean_after_touch = int(_Z_CAT[k])
                _touch_step(z, i, t, h, l, c_prev)
                _Z_TC[k] = z.touch_count
                if z.last_touch_i is not None:
                    _Z_LTI[k] = z.last_touch_i
                _Z_CAT[k] = z.clean_after_touch
                if z.expired:
                    _exp_k.append(k)

        # ---------- انتخاب زون‌های واجد شرایط (کاندیدای سفارش) ----------
        # زون‌هایی که از همه‌ی فیلترها رد شده‌اند اینجا فقط «کاندید» می‌شوند؛
        # اینکه واقعاً سفارششان روی حساب برود یا نه، به سهمیه بستگی دارد.
        # زون‌های باطل‌شده دیگر هرگز برنمی‌گردند، پس از فهرست زنده‌ها حذف می‌شوند
        if _exp_k:
            live_k = live_k[~np.isin(live_k, _exp_k)]

        if t < bt_start:
            # گرم‌کردن: فقط لمس زون‌ها دنبال می‌شود؛ زونی که پیش از شروع بک‌تست لمس شده مصرف‌شده است
            if len(live_k):
                for k in live_k[_Z_TC[live_k] > 0]:
                    used.add(id(h_z[k]))
            continue

        # سطح نزدیک‌ترین زون‌های مخالف برای «جای تا زون مخالف» — یک بار در هر کندل
        levels = room_levels(t, o, live_k) if min_room_r > 0 else None

        candidates = []
        # زون لمس‌نشده یا «مصرف‌شده» در این حلقه هیچ اثری ندارد؛ از قبل کنار گذاشته می‌شود
        for k in live_k[(_Z_TC[live_k] > 0) & ~_Z_USED[live_k]]:
            z = h_z[k]
            if id(z) in used:
                continue
            # لمسِ همین کندل را ربات لایو فقط بعد از بسته شدن کندل می‌فهمد؛ پس تصمیم درباره‌ی
            # این زون (سفارش/رد) از کندل بعد گرفته می‌شود — نه با نگاه به داخل همین کندل.
            if NO_SAME_BAR_TOUCH_FILL and z.last_touch_i == i:
                reasons["تعویق_سفارش_لمس_همین_کندل"] += 1
                continue
            if z.touch_count>=3:
                reasons["لغو_به_خاطر_تست_سوم"] += 1
                set_final(zone_df, z.zone_id, "رد شد", "تست سوم ممنوع", t, idx=z_idx)
                log_event(events, t, symbol, z.zone_id, "Rejected", "تست سوم")
                used.add(id(z)); continue
            if z.touch_count==0:
                continue

            # رد به‌خاطر رنج/روند: به‌طور پیش‌فرض دائمی است؛ با retry_rejected_zones
            # زون زنده می‌ماند و اگر بعداً شرایط سبز شد، دوباره فرصت می‌گیرد
            if drg or hrg:
                reasons["رد_به_خاطر_رنج"] += 1
                if retry_rejected_zones:
                    continue
                set_final(zone_df, z.zone_id, "رد شد", "رنج", t, idx=z_idx)
                log_event(events, t, symbol, z.zone_id, "Rejected", "رنج")
                used.add(id(z)); continue

            if z.direction not in allowed_now:
                reasons["رد_به_خاطر_روند"] += 1
                if retry_rejected_zones:
                    continue
                set_final(zone_df, z.zone_id, "رد شد",
                          "خلاف روند یا ناهم‌جهتی روند روزانه و تایم زون" if TRADE_WITH_TREND_ONLY
                          else "عدم هم‌جهتی روند D1 و H4", t, idx=z_idx)
                log_event(events, t, symbol, z.zone_id, "Rejected", "روند")
                used.add(id(z)); continue

            # نکته: سقف سفارش هم‌زمان اینجا اعمال نمی‌شود. در ربات لایو هم زونی که
            # فقط به‌خاطر پر بودن سهمیه جا نماند، «باطل» نمی‌شود بلکه در فهرست
            # خواسته‌ها می‌ماند و به‌محض آزاد شدن سهمیه دوباره چیده می‌شود.
            # اعمال سقف در بخش سهمیه‌بندی پایین‌تر انجام می‌گیرد.

            # حاشیه‌ی سود (Odds Enhancer): حرکت اولیه‌ی زون باید حداقل N برابر ریسک جا داده باشد
            if min_profit_margin_r > 0:
                risk_h = 1.0 + entry_off + sl_off          # ریسک برحسب ارتفاع زون
                if z.departure_h < min_profit_margin_r * risk_h:
                    reasons["رد_به_خاطر_حاشیه_سود_کم"] += 1
                    set_final(zone_df, z.zone_id, "رد شد", "حاشیه‌ی سود حرکت اولیه کم بود", t, idx=z_idx)
                    log_event(events, t, symbol, z.zone_id, "Rejected", "ProfitMargin")
                    used.add(id(z)); continue

            # قدرت خروج (Odds Enhancer): بدنه‌ی کندل تأیید نسبت به ATR
            if min_departure_atr > 0 and z.conf_body_atr < min_departure_atr:
                reasons["رد_به_خاطر_خروج_ضعیف"] += 1
                set_final(zone_df, z.zone_id, "رد شد", "خروج از زون به‌قدر کافی قوی نبود", t, idx=z_idx)
                log_event(events, t, symbol, z.zone_id, "Rejected", "WeakDeparture")
                used.add(id(z)); continue

            # سقف اختیاری پوزیشن باز هر نماد (۰ = بدون محدودیت، مثل رفتار فعلی)
            if max_open_per_symbol and len(open_pos) >= max_open_per_symbol:
                reasons["رد_به_خاطر_سقف_پوزیشن_نماد"] += 1
                set_final(zone_df, z.zone_id, "رد شد", "سقف پوزیشن باز این نماد", t, idx=z_idx)
                log_event(events, t, symbol, z.zone_id, "Rejected", "سقف پوزیشن نماد")
                used.add(id(z)); continue

            # فیلتر حداقل اندازه‌ی زون: فاصله‌ی ورود تا استاپ باید حداقل min_risk_atr برابر ATR باشد
            # (ATR از کندل قبلیِ بسته‌شده — بدون نگاه به آینده)
            if min_risk_atr > 0:
                atr_ref = _h4_atr_a[i-1]
                height = z.high() - z.low()
                risk_est = height * (1.0 + entry_off + sl_off)
                if pd.isna(atr_ref) or risk_est < min_risk_atr * float(atr_ref):
                    reasons["رد_به_خاطر_زون_کوچک"] += 1
                    set_final(zone_df, z.zone_id, "رد شد", "زون خیلی کوچک (استاپ نزدیک)", t, idx=z_idx)
                    log_event(events, t, symbol, z.zone_id, "Rejected", "SmallZone")
                    used.add(id(z)); continue

            # فیلترهای آزمایش طراحی (اندازه‌ی زون نسبت به اسپرد، محل روی تایم بالا، جای تا زون مخالف)
            _why = design_block(z, levels, t, o)
            if _why:
                reasons[_why] += 1
                set_final(zone_df, z.zone_id, "رد شد", _why.replace("_", " "), t, idx=z_idx)
                log_event(events, t, symbol, z.zone_id, "Rejected", _why)
                used.add(id(z)); continue

            # عین ربات: اگر قیمتِ لحظه‌ی ثبت (باز شدن کندل) از نقطه‌ی ورود رد شده باشد، سفارش
            # لیمیت معنا ندارد؛ زون سهمیه نمی‌گیرد و برای کندل‌های بعد (اگر قیمت برگشت) می‌ماند.
            if NO_SAME_BAR_TOUCH_FILL and not ltf_on:
                _h = z.high() - z.low()
                _ent = z.proximal + entry_off * _h if z.direction == "BUY" else z.proximal - entry_off * _h
                if (z.direction == "BUY" and _ent >= o + spr) or (z.direction == "SELL" and _ent <= o):
                    reasons["رد_به_خاطر_عبور_قیمت_از_ورود"] += 1
                    continue

            candidates.append((z, 1 if z.touch_count==1 else 2))

        # ---------- سفارش‌های «از پیش چیده» روی زون‌های لمس‌نشده ----------
        # ربات لایو فقط کندل‌های بسته‌شده را می‌بیند، پس اگر منتظر لمس زون بماند
        # ورودهای داخل کندل را از دست می‌دهد. برای همین روی نزدیک‌ترین زون‌های
        # لمس‌نشده هم از قبل لیمیت می‌گذارد (فهرست armed در replay_state).
        # این سفارش‌ها جای واقعی از سقف حساب اشغال می‌کنند — بدون مدل کردنشان
        # بک‌تست خیلی خوش‌بینانه می‌شود.
        armed_cands = []
        if arm_untouched_zones and not (drg or hrg) and allowed_now:
            _hits_arm = big_body_hits(t, o_prev, c_prev)
            for k in live_k[(_Z_TC[live_k] == 0) & ~_Z_USED[live_k]]:
                z = h_z[k]
                if id(z) in used:
                    continue
                if z.superseded_time is not None and t >= z.superseded_time:
                    continue
                if z.touch_count != 0:
                    continue
                if z.direction not in allowed_now:
                    continue
                opp_dir = "SELL" if z.direction == "BUY" else "BUY"
                if _hits_arm[opp_dir]:
                    continue
                if z.high() - z.low() <= 0:
                    continue
                if not armed_quality_ok(z, levels, t, _h4_atr_a[i-1], o):
                    continue
                armed_cands.append((z, 1))
            armed_cands.sort(key=lambda zc: abs(c - zc[0].proximal))

        # ---------- سهمیه‌بندی سفارش‌ها — عین sync_all ربات ----------
        # فهرست خواسته‌های این نماد به همان ترتیب اولویت ربات:
        # اول سفارش‌های روی حساب (جایشان را نگه می‌دارند)، بعد زون‌های لمس‌شده،
        # و در آخر زون‌های لمس‌نشده به ترتیب نزدیکی به قیمت.
        candidates.sort(key=lambda zc: abs(c - zc[0].proximal))
        candidates = candidates + armed_cands
        live_pending = [p for p in pending if p["active"] and not p["filled"]]
        n_wanted = len(live_pending) + len(candidates)

        if alloc_mode:
            # منتظر راننده می‌مانیم تا بگوید چند سهمیه از سقف کل حساب گرفته‌ایم
            n_slots = yield {"نماد": symbol, "t": t, "خواسته": n_wanted,
                            "روی_حساب": len(live_pending)}
            n_slots = int(n_slots or 0)
        else:
            n_slots = max_orders
        n_slots = max(0, min(n_slots, max_orders)) if max_orders and max_orders > 0 else n_wanted
        if ltf_on:
            # تأیید ۱دقیقه: منتظر ماندن برای رسیدن قیمت/چاک اوردری روی بروکر نیست، پس سقف سفارش
            # را اشغال نمی‌کند؛ فقط سقف پوزیشن باز کل حساب موقع ورود رعایت می‌شود.
            n_slots = n_wanted

        # سفارش‌هایی که سهمیه‌شان را از دست داده‌اند برداشته می‌شوند (زون سالم می‌ماند)
        for p in live_pending[n_slots:]:
            p["active"] = False
            p["cancel"] = "لغو: سهمیه‌ی سفارش کل حساب پر شد"
            reasons["لغو_به_خاطر_سهمیه_کل_حساب"] += 1
            used.discard(id(p["z"]))
            set_final(zone_df, p["z"].zone_id, "لغو شد",
                      f"سهمیه‌ی سفارش پر بود (سقف {LIVE_MAX_PENDING_TOTAL} کل حساب)", t, idx=z_idx)
            log_event(events, t, symbol, p["z"].zone_id, "Canceled", "QuotaFull")

        free = max(0, n_slots - min(len(live_pending), n_slots))
        for z, test_no in candidates[:free]:
            # در ربات، وقتی سقف پوزیشن باز کل حساب پر باشد سفارش تازه گذاشته نمی‌شود
            if book is not None and book.open_total >= book.max_open_total and not ltf_on:
                reasons["رد_به_خاطر_سقف_پوزیشن_کل_حساب"] += 1
                continue
            _po = make_order(z, t, test_no)
            if ltf_on:
                # تأیید ۱دقیقه: اگر قیمت همین حالا روی بیس است مستقیم منتظر چاک می‌مانیم
                _rg = _m15_range(t)
                _at = (_po["entry"] >= o + spr) if z.direction == "BUY" else (_po["entry"] <= o)
                _po["stage"] = "watch" if (_at and _rg is not None) else "armed"
                _po["j_reach"] = _rg[0] if _rg is not None else 0
                if _po["stage"] == "watch":
                    reasons["رسیدن_به_بیس_۱۵دقیقه"] += 1
            pending.append(_po)
            set_final(zone_df, z.zone_id, "سفارش ثبت شد", "در انتظار پر شدن", t, idx=z_idx)
            log_event(events, t, symbol, z.zone_id, "OrderPlaced", f"تست={test_no}")
            used.add(id(z))
        for z, _tn in candidates[free:]:
            reasons["رد_به_خاطر_سقف_سفارش"] += 1

        # ---------- weekly cancel BEFORE fill (همان) ----------
        # زون هفتگی فقط بعد از بسته‌شدن کندل هفتگیِ تأیید (حدود ۷ روز بعد) معتبر است
        _hits_now = big_body_hits(t, o_prev, c_prev) if any(p["active"] and not p["filled"] for p in pending) else None
        for p in pending:
            if not p["active"] or p["filled"]:
                continue
            opp_dir = "SELL" if p["z"].direction=="BUY" else "BUY"
            if _hits_now[opp_dir]:
                p["active"]=False
                p["cancel"]="لغو: برخورد بدنه با زون مخالف هفتگی"
                reasons["لغو_به_خاطر_هفتگی"] += 1
                set_final(zone_df, p["z"].zone_id, "لغو شد", "زون مخالف هفتگی (بدنه)", t, idx=z_idx)
                log_event(events, t, symbol, p["z"].zone_id, "Canceled", "WeeklyOpp")

        # ---------- لغو به‌خاطر دور شدن قیمت بدون فعال شدن سفارش (اختیاری) ----------
        if dist_cancel_r > 0:
            for p in pending:
                if not p["active"] or p["filled"]:
                    continue
                if p["z"].direction == "BUY":
                    far = h_prev >= p["entry"] + dist_cancel_r * p["risk"]
                else:
                    far = l_prev <= p["entry"] - dist_cancel_r * p["risk"]
                if far:
                    p["active"] = False
                    p["cancel"] = "لغو: دور شدن قیمت"
                    reasons["لغو_به_خاطر_دور_شدن"] += 1
                    set_final(zone_df, p["z"].zone_id, "لغو شد",
                              f"قیمت {dist_cancel_r:g}R دور شد بدون ورود", t, idx=z_idx)
                    log_event(events, t, symbol, p["z"].zone_id, "Canceled", "FarAway")

        # ---------- بی‌اعتبار شدن بیس: کندل ۱۵دقیقه‌ی قبلی پشت دیستال بسته شد ----------
        if invalidate_on_breach:
            for p in pending:
                if not p["active"] or p["filled"]:
                    continue
                _zz = p["z"]
                if (_zz.direction == "BUY" and c_prev < _zz.distal) or (_zz.direction == "SELL" and c_prev > _zz.distal):
                    p["active"] = False
                    p["cancel"] = "لغو: کندل ۱۵دقیقه پشت بیس بسته شد"
                    reasons["لغو_شکست_بیس_با_کلوز_۱۵دقیقه"] += 1
                    set_final(zone_df, _zz.zone_id, "لغو شد", "کندل پشت بیس بسته شد", t, idx=z_idx)
                    log_event(events, t, symbol, _zz.zone_id, "Canceled", "ZoneBreached")

        # ---------- fills + (NEW) exit-same-bar ----------
        new_open_positions = []
        for p in pending:
            if not p["active"] or p["filled"]:
                continue

            if drg or hrg or p["z"].direction not in allowed_now:
                p["active"]=False
                p["cancel"]="لغو: عدم هم‌جهتی/رنج در لحظه ورود"
                reasons["لغو_به_خاطر_رنج_یا_روند_لحظه_ورود"] += 1
                set_final(zone_df, p["z"].zone_id, "لغو شد", "عدم هم‌جهتی/رنج در لحظه ورود", t, idx=z_idx)
                log_event(events, t, symbol, p["z"].zone_id, "Canceled", "Trend/Range at Fill")
                continue

            if ltf_on:
                _l_bar[0], _h_bar[0] = l, h
                _pos = ltf_step(p, t)
                if _pos is not None:
                    new_open_positions.append(_pos)
                continue

            filled_now = False
            direction = p["z"].direction

            # خرید لیمیت با Ask پر می‌شود (Bid + اسپرد)، فروش لیمیت با Bid
            if direction=="BUY" and l + spr <= p["entry"]:
                filled_now = True
            elif direction=="SELL" and h >= p["entry"]:
                filled_now = True

            if not filled_now:
                continue

            p["filled"]=True; p["fill_time"]=t
            reasons["ورود_انجام_شد"] += 1
            _zset(p["z"].zone_id, "زمان_پرشدن", t)
            log_event(events, t, symbol, p["z"].zone_id, "Filled", "")

            if book is not None:
                # حجم از روی اکویتیِ حساب مشترک و وزن سشنِ همان لحظه — عین ربات
                risk_amt = book.risk_amount(t)
                book.open_total += 1
            else:
                usable = equity*(1.0 - reserve)
                risk_amt = usable*risk_per_trade

            trigger = (p["eff_entry"] + MANAGE_TRIGGER_R * p["risk"]) if direction == "BUY" \
                else (p["eff_entry"] - MANAGE_TRIGGER_R * p["risk"])
            pos = {
                "ZoneID": p["z"].zone_id,
                "direction": direction,
                "eff_entry": float(p["eff_entry"]),
                "sl": float(p["sl"]),
                "tp": float(p["tp"]),
                "risk": float(p["risk"]),
                "risk_amt": float(risk_amt),
                "fill_time": t,
                "test": p["test"],
                "z": p["z"],
                "trigger": float(trigger),
                "managed": False,
            }

            # کندل ورود: فقط اتفاقاتِ «بعد از» پر شدن حساب می‌شود — با تایم پایین‌تر اگر باشد،
            # وگرنه با حدس مسیر کندل (ENTRY_BAR_MODE). استاپ همیشه بدبینانه اول بررسی می‌شود.
            exited, exit_price, reason = step_position(pos, o, h, l, c, t, entry_bar=True)
            if exited:
                if "حدسود" in str(reason) and m15_t is None:
                    reasons["TP_کندل_ورود_بدون_M15"] += 1
                finalize_trade(pos, t, float(exit_price), reason)
            else:
                new_open_positions.append(pos)

            p["active"] = False

        open_pos.extend(new_open_positions)
        pending=[x for x in pending if x["active"] and (not x["filled"])]

    # ---------- پایان دیتا ----------
    endt = h4["time"].iloc[-1] if len(h4)>0 else None
    if endt is not None:
        # بستن پوزیشن‌های باز با close آخر
        c_last = float(h4["close"].iloc[-1])
        for pos in open_pos:
            finalize_trade(pos, endt, c_last, "پایان دیتا")

        # finalize zones
        for zid in zone_df["ZoneID"].tolist():
            if str(zone_df.iat[z_idx[zid], zone_df.columns.get_loc("FinalStatus")]).strip()=="":
                set_final(zone_df, zid, "بدون لمس", "تا پایان دیتا لمس نشد", endt, idx=z_idx)

        for p in pending:
            if p["active"] and (not p["filled"]):
                set_final(zone_df, p["z"].zone_id, "سفارش پر نشد", "تا پایان دیتا پر نشد", endt, idx=z_idx)
                log_event(events, endt, symbol, p["z"].zone_id, "Unfilled", "")

    tdf=pd.DataFrame(trades)
    if tdf.empty:
        metrics={
            "نماد":symbol,"تعداد":0,"درصد_برد":0.0,"فاکتور_سود":0.0,
            "بازده_خالص٪":0.0,"حداکثر_افت٪":0.0,"میانگین_R":0.0,
            "مبهم_تعداد":0,"مبهم_درصد":0.0,
            "بازده٪_اگر_مبهم_TP":0.0,"بازده٪_اگر_مبهم_استاپ":0.0,
            "فاصله_استاپ_پیپ":0.0,"فاصله_TP_پیپ":0.0,
            "برد_همان_کندل_تعداد":0,"بازده٪_اگر_برد_همان_کندل_استاپ":0.0,
            "هزینه_هر_معامله_R":0.0,"اسپرد_پیپ":round(spread_ref / pip_size(symbol), 2)
        }
    else:
        wins=tdf.loc[tdf["نتیجه_R"]>0,"نتیجه_R"].sum()
        loss=tdf.loc[tdf["نتیجه_R"]<0,"نتیجه_R"].abs().sum()
        pf=float(wins/loss) if loss>0 else 999.0
        winrate=float((tdf["نتیجه_R"]>0).mean()*100.0)
        net=float((equity-100000.0)/100000.0*100.0)

        # --- تحلیل معاملات مبهم (TP و استاپ هر دو در یک کندل H4 لمس شده) ---
        amb = tdf["علت_خروج"].astype(str).str.contains("هر دو در یک کندل")
        n_amb = int(amb.sum())

        def _net_with(r_series):
            eq = 100000.0
            for r in r_series:
                eq += eq * (1.0 - reserve) * risk_per_trade * float(r)
            return round((eq - 100000.0) / 100000.0 * 100.0, 2)

        risk_d = (tdf["ورود"] - tdf["حدضرر"]).abs().replace(0, np.nan)
        r_if_tp = (tdf["حدسود"] - tdf["ورود"]).abs() / risk_d - commission_cost / risk_d
        rs_if_tp = tdf["نتیجه_R"].where(~amb, r_if_tp).fillna(tdf["نتیجه_R"])
        net_if_tp = _net_with(rs_if_tp)      # اگر همه‌ی مبهم‌ها TP بودند
        net_if_sl = _net_with(tdf["نتیجه_R"])  # مبهم‌ها همین حالا استاپ حساب شده‌اند

        # --- فاصله‌ی استاپ و حدسود به پیپ ---
        pip = pip_size(symbol)
        sl_pips = float(((tdf["ورود"] - tdf["حدضرر"]).abs() / pip).mean())
        tp_pips = float(((tdf["حدسود"] - tdf["ورود"]).abs() / pip).mean())

        # --- بردهای همان‌کندل (خروج در همان کندل ورود) و سناریوی کف: همه استاپ ---
        same_win = (pd.to_datetime(tdf["زمان_ورود"]) == pd.to_datetime(tdf["زمان_خروج"])) & (tdf["نتیجه_R"] > 0)
        n_sw = int(same_win.sum())
        r_if_sl = -1.0 - commission_cost / risk_d
        rs_floor = tdf["نتیجه_R"].where(~same_win, r_if_sl).fillna(tdf["نتیجه_R"])
        net_floor = _net_with(rs_floor)

        metrics={
            "نماد":symbol,"تعداد":int(len(tdf)),"درصد_برد":round(winrate,2),
            "فاکتور_سود":round(pf,3),"بازده_خالص٪":round(net,2),
            "حداکثر_افت٪":round(max_dd*100.0,2),"میانگین_R":round(float(tdf["نتیجه_R"].mean()),3),
            "مبهم_تعداد":n_amb,"مبهم_درصد":round(n_amb/len(tdf)*100.0,2),
            "بازده٪_اگر_مبهم_TP":net_if_tp,"بازده٪_اگر_مبهم_استاپ":net_if_sl,
            "فاصله_استاپ_پیپ":round(sl_pips,1),"فاصله_TP_پیپ":round(tp_pips,1),
            "برد_همان_کندل_تعداد":n_sw,"بازده٪_اگر_برد_همان_کندل_استاپ":net_floor,
            "هزینه_هر_معامله_R":round(float(tdf["هزینه_R"].median()),3),   # میانه: چند استاپ خیلی ریز میانگین را گمراه می‌کنند
            "اسپرد_پیپ":round(spread_ref / pip, 2)
        }

    reasons_df=pd.DataFrame([{"نماد":symbol,"دلیل":k,"تعداد":int(v)} for k,v in reasons.items()])
    metrics_df=pd.DataFrame([metrics])
    events_df=pd.DataFrame(events)

    z_reason = zone_df.groupby(["نماد","FinalStatus","FinalReason"]).size().reset_index(name="تعداد")
    z_reason["درصد"] = z_reason.groupby("نماد")["تعداد"].transform(lambda s: (s/s.sum()*100.0).round(2))

    if return_state:
        # وضعیت «همین الان» برای ربات لایو: سفارش‌های در انتظارِ فعال و پوزیشن‌های باز
        state = {
            "pending": [{
                "zone_id": p["z"].zone_id, "direction": p["z"].direction,
                "entry": float(p["entry"]), "sl": float(p["sl"]), "tp": float(p["tp"]),
                "placed_time": p["t"], "test": p["test"],
            } for p in pending if p["active"] and not p["filled"]],
            "open": [{
                "zone_id": pos["ZoneID"], "direction": pos["direction"],
                "entry": float(pos["eff_entry"]), "sl": float(pos["sl"]), "tp": float(pos["tp"]),
                "fill_time": pos["fill_time"],
            } for pos in open_pos],
            "armed": [],
            "فیلتر_توضیح": "",
            "دلیل_نبود": "",
            # دلیل نهایی هر زون (برای اینکه ربات لایو بداند چرا سفارشی دیگر معتبر نیست)
            "دلایل_زون": {
                str(r["ZoneID"]): f"{str(r['FinalStatus']).strip()} — {str(r['FinalReason']).strip()}"
                for _, r in zone_df.iterrows()
                if str(r.get("FinalStatus", "")).strip()
            },
        }

        # زون‌های «آماده‌باش» برای لایو: هنوز تاچ نشده‌اند ولی اگر قیمت وسط کندل بیاید،
        # سفارش از قبل داخل متاتریدر هست و جا نمی‌مانیم (معادل پر شدن داخل کندل در بک‌تست).
        if len(h4) >= 2 and len(d1) >= 2:
            t_last = h4["time"].iloc[-1]
            o_last = float(h4["open"].iloc[-1]); c_last = float(h4["close"].iloc[-1])
            drg_now = d1["range"].iloc[-1]; hrg_now = h4["range"].iloc[-1]
            if not RANGE_FILTER:
                drg_now = False if not pd.isna(drg_now) else drg_now
                hrg_now = False if not pd.isna(hrg_now) else hrg_now
            dtr_now = int(d1["trend"].iloc[-1]); htr_now = int(h4["trend"].iloc[-1])
            warm = (not pd.isna(drg_now)) and (not pd.isna(hrg_now))
            allowed_last = dirs_allowed(dtr_now, htr_now)
            filters_ok = warm and (not bool(drg_now)) and (not bool(hrg_now)) and bool(allowed_last)

            trend_txt = TREND_TXT
            state["فیلتر_توضیح"] = (
                f"روند روزانه: {trend_txt.get(dtr_now)} | روند H4: {trend_txt.get(htr_now)} | "
                f"رنج روزانه: {'بله' if warm and bool(drg_now) else 'خیر'} | "
                f"رنج H4: {'بله' if warm and bool(hrg_now) else 'خیر'}"
            )

            # دلیل دقیق نبودِ معامله (برای عیب‌یابی زنده)
            blockers = []
            if not warm:
                blockers.append("اندیکاتورها هنوز آماده نیستند")
            else:
                if bool(drg_now):
                    blockers.append("بازار روزانه رنج است")
                if bool(hrg_now):
                    blockers.append("بازار ۴ساعته رنج است")
                if dtr_now == 0:
                    blockers.append("روند روزانه مشخص نیست")
                if htr_now == 0:
                    blockers.append("روند ۴ساعته مشخص نیست")
                if dtr_now != 0 and htr_now != 0 and not allowed_last:
                    blockers.append(f"روند روزانه {trend_txt.get(dtr_now)} ولی ۴ساعته {trend_txt.get(htr_now)} (ناهم‌جهت)")
            state["دلیل_نبود"] = " + ".join(blockers) if blockers else "فیلترها سبزند"

            # فیلترهای آزمایش طراحی برای لحظه‌ی «همین الان» (اگر روشن باشند)
            atr_last = float(h4["atr"].iloc[-1]) if "atr" in h4.columns else float("nan")
            zones_now_last = [k for k, z in enumerate(h_z) if z.created_time < t_last and not z.expired]
            levels_last = room_levels(t_last, c_last, zones_now_last) if min_room_r > 0 else None

            if not NO_SAME_BAR_TOUCH_FILL:
                pass   # رفتار قدیمی: فقط سفارش‌های ثبت‌شده‌ی بازپخش + زون‌های مسلح
            elif not filters_ok:
                # بک‌تستر اول کندل بعد، سفارش‌های پرنشده را با همین فیلترهای تازه لغو می‌کند
                # (لغو_به_خاطر_رنج_یا_روند_لحظه_ورود)؛ ربات هم نباید تا ۴ ساعت نگهشان دارد.
                state["pending"] = []
            else:
                # سفارشی که جهتش دیگر با روند جور نیست، کندل بعد در بک‌تستر لغو می‌شود
                state["pending"] = [p_ for p_ in state["pending"] if p_["direction"] in allowed_last]
                # زون‌های لمس‌شده‌ای که هنوز سفارش نگرفته‌اند — از جمله زونی که در همین آخرین
                # کندل لمس شد و طبق NO_SAME_BAR_TOUCH_FILL تصمیمش به کندل بعد موکول شد.
                # بک‌تستر همین‌ها را کندل بعد (بعد از سفارش‌های موجود و قبل از زون‌های لمس‌نشده)
                # سفارش می‌دهد؛ ربات لایو هم همین الان همین کار را می‌کند.
                wz_c = [wz for wz in w_z
                        if wz.created_time + big_span <= t_last
                        and (wz.superseded_time is None or t_last < wz.superseded_time)]
                cands_next = []
                for z in h_z:
                    if z.created_time >= t_last or z.expired or id(z) in used:
                        continue
                    if z.superseded_time is not None and t_last >= z.superseded_time:
                        continue
                    if z.touch_count not in (1, 2):
                        continue
                    if z.direction not in allowed_last:
                        continue
                    opp_dir = "SELL" if z.direction == "BUY" else "BUY"
                    if any(body_overlaps_zone(o_last, c_last, wz) for wz in wz_c if wz.direction == opp_dir):
                        continue
                    height = z.high() - z.low()
                    if height <= 0:
                        continue
                    if min_profit_margin_r > 0 and z.departure_h < min_profit_margin_r * (1.0 + entry_off + sl_off):
                        continue
                    if min_departure_atr > 0 and z.conf_body_atr < min_departure_atr:
                        continue
                    if min_risk_atr > 0 and (pd.isna(atr_last) or
                                             height * (1.0 + entry_off + sl_off) < min_risk_atr * atr_last):
                        continue
                    if design_block(z, levels_last, t_last, c_last):
                        continue
                    if z.direction == "BUY":
                        entry = z.proximal + entry_off * height
                        sl = z.distal - sl_off * height
                        risk = entry - sl
                        tp = entry + rr * risk
                    else:
                        entry = z.proximal - entry_off * height
                        sl = z.distal + sl_off * height
                        risk = sl - entry
                        tp = entry - rr * risk
                    if risk <= 0:
                        continue
                    # قیمت از ورود رد شده → فعلاً سفارشی نمی‌شود گذاشت؛ سهمیه هم نگیرد
                    if (z.direction == "BUY" and entry >= c_last) or (z.direction == "SELL" and entry <= c_last):
                        continue
                    cands_next.append({"zone_id": z.zone_id, "direction": z.direction,
                                       "entry": float(entry), "sl": float(sl), "tp": float(tp),
                                       "placed_time": t_last, "test": 1 if z.touch_count == 1 else 2,
                                       "dist": float(abs(c_last - z.proximal))})
                cands_next.sort(key=lambda a: a["dist"])
                state["pending"] = state["pending"] + cands_next

            if filters_ok:
                wz_now = [wz for wz in w_z
                          if wz.created_time + big_span <= t_last
                          and (wz.superseded_time is None or t_last < wz.superseded_time)]
                armed = []
                for z in h_z:
                    if z.created_time >= t_last or z.expired or id(z) in used:
                        continue
                    if z.superseded_time is not None and t_last >= z.superseded_time:
                        continue
                    if z.touch_count != 0:
                        continue
                    if z.direction not in allowed_last:
                        continue
                    opp_dir = "SELL" if z.direction == "BUY" else "BUY"
                    if any(body_overlaps_zone(o_last, c_last, wz) for wz in wz_now if wz.direction == opp_dir):
                        continue
                    height = z.high() - z.low()
                    if height <= 0:
                        continue
                    if not armed_quality_ok(z, levels_last, t_last, atr_last, c_last):
                        continue
                    if z.direction == "BUY":
                        entry = z.proximal + entry_off * height
                        sl = z.distal - sl_off * height
                        risk = entry - sl
                        tp = entry + rr * risk
                    else:
                        entry = z.proximal - entry_off * height
                        sl = z.distal + sl_off * height
                        risk = sl - entry
                        tp = entry - rr * risk
                    if risk <= 0:
                        continue
                    armed.append({"zone_id": z.zone_id, "direction": z.direction,
                                  "entry": float(entry), "sl": float(sl), "tp": float(tp),
                                  "placed_time": t_last, "test": 0,
                                  "dist": float(abs(c_last - z.proximal))})
                # نزدیک‌ترین زون‌ها به قیمت، تا سقف سفارش هم‌زمانِ هر نماد
                armed.sort(key=lambda a: a["dist"])
                n_slots = max(0, max_orders - len(state["pending"]))
                state["armed"] = armed[:n_slots]

        return metrics_df, reasons_df, tdf, zone_df, events_df, z_reason, state

    return metrics_df, reasons_df, tdf, zone_df, events_df, z_reason


def backtest_one(*args, **kwargs):
    """اجرای تک‌نمادی (رفتار قبلی، بدون تغییر).

    موتور را تنها اجرا می‌کند و در هر سهمیه‌بندی، سقف خودِ نماد را کامل به آن
    می‌دهد — یعنی همان «هر چارت تا ۳ سفارش، بدون توجه به بقیه‌ی حساب».
    """
    kwargs.pop("alloc_mode", None)
    max_orders = kwargs.get("max_orders", 3)
    gen = _backtest_core(*args, alloc_mode=False, **kwargs)
    reply = None
    while True:
        try:
            gen.send(reply)
        except StopIteration as stop:
            return stop.value
        reply = max_orders


def portfolio_live_replay(symbol_frames, spreads, entry_off=None, sl_off=None, rr=None,
                          manage_mode=None, risk_per_trade=None, reserve=None,
                          start_equity=None, max_pending_total=None, max_open_total=None,
                          max_pending_per_symbol=None, basket_order=None,
                          session_weights=None, **core_kwargs):
    """بک‌تست «عین لایو»: همه‌ی نمادها هم‌زمان روی یک حساب مشترک.

    هر نماد یک موتور مستقل دارد ولی همه کندل‌به‌کندل با هم جلو می‌روند. سر هر کندل،
    درست مثل sync_all ربات، سهمیه‌ی سفارش‌ها به‌صورت دوری تقسیم می‌شود:
    دور اول یک سفارش به هر نماد، بعد دور دوم و سوم — تا وقتی سقف کل حساب پر شود.

    symbol_frames: دیکشنری {نماد: (h4, d1, w1, m15)}
    """
    entry_off = DEFAULT_ENTRY_OFF if entry_off is None else entry_off
    sl_off = DEFAULT_SL_OFF if sl_off is None else sl_off
    rr = DEFAULT_RR if rr is None else rr
    manage_mode = DEFAULT_MANAGE if manage_mode is None else manage_mode
    risk_per_trade = LIVE_RISK_PER_TRADE if risk_per_trade is None else risk_per_trade
    reserve = LIVE_RESERVE if reserve is None else reserve
    start_equity = LIVE_START_EQUITY if start_equity is None else start_equity
    max_pending_total = LIVE_MAX_PENDING_TOTAL if max_pending_total is None else max_pending_total
    max_open_total = LIVE_MAX_OPEN_TOTAL if max_open_total is None else max_open_total
    max_per_sym = LIVE_MAX_PENDING_PER_SYMBOL if max_pending_per_symbol is None else max_pending_per_symbol
    if session_weights is None and USE_DEFAULT_SESSION_WEIGHTS:
        session_weights = DEFAULT_SESSION_WEIGHTS

    # ترتیب نمادها = ترتیب اولویت در سهمیه‌بندی دوری (عین BASKET ربات)
    order = [s for s in (basket_order or LIVE_BASKET_ORDER) if s in symbol_frames]
    order += [s for s in symbol_frames if s not in order]

    book = AccountBook(start_equity=start_equity, reserve=reserve,
                       risk_per_trade=risk_per_trade, session_weights=session_weights,
                       max_open_total=max_open_total)

    gens, reqs, results = {}, {}, {}
    for sym in order:
        h4, d1, w1, m15 = symbol_frames[sym]
        gen = _backtest_core(sym, h4, d1, w1, None, spreads.get(sym, 0.0),
                             entry_off=entry_off, sl_off=sl_off, rr=rr,
                             reserve=reserve, risk_per_trade=risk_per_trade,
                             max_orders=max_per_sym, m15=m15, manage_mode=manage_mode,
                             book=book, alloc_mode=True,
                             arm_untouched_zones=LIVE_ARM_UNTOUCHED, **core_kwargs)
        try:
            reqs[sym] = gen.send(None)
        except StopIteration as stop:
            results[sym] = stop.value
            continue
        gens[sym] = gen

    # حلقه‌ی زمانیِ مشترک: در هر گام، نمادهایی که روی قدیمی‌ترین کندل ایستاده‌اند
    # جواب سهمیه می‌گیرند و یک کندل جلو می‌روند.
    alloc_log = []
    while gens:
        t_min = min(r["t"] for r in reqs.values())
        group = [s for s in order if s in gens and reqs[s]["t"] == t_min]

        # سهمیه‌بندی دوری روی خواسته‌ی همه‌ی نمادهای زنده — عین حلقه‌ی range(3) ربات
        alloc = {s: 0 for s in gens}
        total = 0
        if max_per_sym <= 0 or max_pending_total <= 0:
            # بدون سقف: هر نماد هر چند سفارش که بخواهد (سقف هر نماد اگر باشد رعایت می‌شود)
            for s in gens:
                alloc[s] = reqs[s]["خواسته"] if max_per_sym <= 0 else min(reqs[s]["خواسته"], max_per_sym)
        for _round in range(max_per_sym if max_pending_total > 0 else 0):
            for s in order:
                if s not in gens or total >= max_pending_total:
                    continue
                if reqs[s]["خواسته"] > alloc[s]:
                    alloc[s] += 1
                    total += 1

        alloc_log.append({"زمان": t_min, "سفارش_تخصیص‌یافته": total,
                          "پوزیشن_باز": book.open_total, "اکویتی": round(book.equity, 2)})

        for s in group:
            try:
                reqs[s] = gens[s].send(alloc[s])
            except StopIteration as stop:
                results[s] = stop.value
                gens.pop(s, None)
                reqs.pop(s, None)

    return results, book, pd.DataFrame(alloc_log)

# ---------------- PDFs ----------------
def _parse_version_tuple(name: str):
    """
    تبدیل Z_v1.4 -> (1,4) برای مرتب‌سازی نسخه‌ها
    اگر قابل تشخیص نبود None برمی‌گرداند.
    """
    m = re.search(r'Z_v(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:\.(\d+))?', name)
    if not m:
        return None
    nums = [int(x) for x in m.groups() if x is not None]
    return tuple(nums) if nums else None

def _find_baseline_metrics_path(current_dir: str):
    """
    تلاش می‌کند نتایج نسخه قبلی را پیدا کند:
    - در پوشه والد، فولدرهای Z_v* را پیدا می‌کند
    - نزدیک‌ترین نسخه کوچک‌تر از نسخه فعلی را انتخاب می‌کند
    - سپس مسیر خروجی/نتایج_اعدادی.xlsx را برمی‌گرداند اگر وجود داشته باشد
    """
    parent = os.path.dirname(current_dir)
    cur_name = os.path.basename(current_dir)
    cur_ver = _parse_version_tuple(cur_name)

    candidates = []
    for d in os.listdir(parent):
        p = os.path.join(parent, d)
        if d == cur_name or (not os.path.isdir(p)):
            continue
        if not d.startswith("Z_v"):
            continue
        vt = _parse_version_tuple(d)
        if vt is None:
            continue
        candidates.append((vt, d))

    if not candidates or cur_ver is None:
        return None

    # انتخاب بزرگ‌ترین نسخه‌ای که از نسخه فعلی کوچک‌تر باشد
    smaller = [c for c in candidates if c[0] < cur_ver]
    if not smaller:
        return None
    smaller.sort(key=lambda x: x[0])
    prev_dir = smaller[-1][1]
    baseline_new = os.path.join(parent, prev_dir, "خروجی", "خلاصه_نتایج.xlsx")
    baseline_old = os.path.join(parent, prev_dir, "خروجی", "نتایج_اعدادی.xlsx")
    if os.path.isfile(baseline_new):
        return baseline_new
    return baseline_old if os.path.isfile(baseline_old) else None

def augment_metrics_with_change_review(metrics_df: pd.DataFrame, current_dir: str, years: int,
                                       book=None, trades=None):
    """
    به metrics_df ستون‌های مقایسه با نسخه قبلی اضافه می‌کند (اگر پیدا شود).
    همچنین یک ردیف «کل» اضافه می‌کند که KPIهای وزنی را نشان می‌دهد.

    اگر book داده شود (حالت «عین لایو»)، بازده و افتِ ردیف «کل» از خود حساب
    مشترک خوانده می‌شود — نه میانگین/بیشینه‌ی ستون‌ها که در این حالت گمراه‌کننده است.
    """
    df = metrics_df.copy()

    # KPI کل (وزنی بر اساس تعداد معاملات)
    total_trades = int(df["تعداد"].sum()) if "تعداد" in df.columns else 0
    if total_trades > 0:
        est_wins = (df["تعداد"] * df["درصد_برد"] / 100.0).sum()
        win_all = float(est_wins / total_trades * 100.0)
        pf_w = float((df["فاکتور_سود"] * df["تعداد"]).sum() / total_trades)
        r_w = float((df["میانگین_R"] * df["تعداد"]).sum() / total_trades)
        worst_dd = float(df["حداکثر_افت٪"].max())
        # تقریب بازده پرتفوی وزن مساوی
        wealth = (1.0 + df["بازده_خالص٪"] / 100.0).mean()
        port_return = (wealth - 1.0) * 100.0
        port_monthly = (wealth ** (1.0 / (years * 12.0)) - 1.0) * 100.0
    else:
        win_all = pf_w = r_w = worst_dd = port_return = port_monthly = 0.0

    if book is not None and total_trades > 0:
        # حالت «عین لایو»: بازده و افت واقعیِ همان یک حساب، نه میانگین ستون‌ها.
        # (ستون‌های هر نماد در این حالت «سهم آن نماد از بازده حساب» هستند و
        #  جمعشان بازده کل می‌شود؛ پس میانگین گرفتن از آن‌ها بی‌معنی است.)
        wealth = book.equity / book.start_equity if book.start_equity else 1.0
        port_return = (wealth - 1.0) * 100.0
        worst_dd = book.max_dd * 100.0
        port_monthly = ((wealth ** (1.0 / (years * 12.0)) - 1.0) * 100.0) if years else 0.0

    summary_row = {
        "نماد": "کل",
        "تعداد": total_trades,
        "درصد_برد": round(win_all, 2),
        "فاکتور_سود": round(pf_w, 3),
        "بازده_خالص٪": round(port_return, 2),
        "حداکثر_افت٪": round(worst_dd, 2),
        "میانگین_R": round(r_w, 3),
        "CAGR_ماهانه_% (تقریب وزن‌مساوی)": round(port_monthly, 2),
    }
    if trades is not None and not trades.empty and "هزینه_R" in trades.columns:
        summary_row["هزینه_هر_معامله_R"] = round(float(trades["هزینه_R"].astype(float).median()), 3)

    # Baseline
    baseline_path = _find_baseline_metrics_path(current_dir)
    if baseline_path:
        try:
            base = pd.read_excel(baseline_path)
            # merge on symbol
            m = df.merge(base, on="نماد", how="left", suffixes=("", "_Baseline"))
            # اضافه کردن نمادهای حذف‌شده (در Baseline بوده‌اند ولی در این نسخه نیستند)
            removed_syms = [x for x in base["نماد"].unique().tolist() if x not in df["نماد"].unique().tolist()]
            if removed_syms:
                removed_rows = base[base["نماد"].isin(removed_syms)].copy()
                # ستون‌های فعلی را خالی می‌کنیم و فقط ستون‌های Baseline را نگه می‌داریم
                for col in df.columns:
                    if col != "نماد":
                        removed_rows[col] = np.nan
                # نام ستون‌های Baseline را با پسوند هماهنگ می‌کنیم
                for col in list(base.columns):
                    if col != "نماد":
                        removed_rows.rename(columns={col: f"{col}_Baseline"}, inplace=True)
                removed_rows["نتیجه_تغییر"] = "حذف شد"
                # هم‌ستون‌سازی با m
                for col in m.columns:
                    if col not in removed_rows.columns:
                        removed_rows[col] = np.nan
                removed_rows = removed_rows[m.columns]
                m = pd.concat([m, removed_rows], ignore_index=True)

            # deltas
            for col in ["درصد_برد", "فاکتور_سود", "بازده_خالص٪", "حداکثر_افت٪", "میانگین_R", "تعداد"]:
                bcol = f"{col}_Baseline"
                if bcol in m.columns:
                    m[f"Δ{col}"] = m[col] - m[bcol]
            # status
            def status_row(r):
                if pd.isna(r.get("درصد_برد_Baseline")):
                    return "جدید/بدون مقایسه"
                score = 0
                score += 1 if r.get("Δدرصد_برد", 0) >= 0 else -1
                score += 1 if r.get("Δفاکتور_سود", 0) >= 0 else -1
                # دراودان کمتر بهتر است
                score += 1 if r.get("Δحداکثر_افت٪", 0) <= 0 else -1
                score += 1 if r.get("Δبازده_خالص٪", 0) >= 0 else -1
                if score >= 2:
                    return "بهتر"
                if score <= -2:
                    return "بدتر"
                return "مخلوط/نامشخص"
            m["نتیجه_تغییر"] = m.apply(status_row, axis=1)

            # baseline portfolio KPI
            if "تعداد" in base.columns and base["تعداد"].sum() > 0:
                bt = int(base["تعداد"].sum())
                bw = (base["تعداد"] * base["درصد_برد"] / 100.0).sum()
                bwin = float(bw / bt * 100.0)
                bpf = float((base["فاکتور_سود"] * base["تعداد"]).sum() / bt)
                br = float((base["میانگین_R"] * base["تعداد"]).sum() / bt)
                bdd = float(base["حداکثر_افت٪"].max())
                bwealth = (1.0 + base["بازده_خالص٪"] / 100.0).mean()
                bret = (bwealth - 1.0) * 100.0
                bmon = (bwealth ** (1.0 / (years * 12.0)) - 1.0) * 100.0
            else:
                bt=bwin=bpf=br=bdd=bret=bmon=0.0

            # attach baseline numbers into summary row
            summary_row.update({
                "تعداد_Baseline": bt,
                "درصد_برد_Baseline": round(bwin, 2),
                "فاکتور_سود_Baseline": round(bpf, 3),
                "بازده_خالص٪_Baseline": round(bret, 2),
                "حداکثر_افت٪_Baseline": round(bdd, 2),
                "میانگین_R_Baseline": round(br, 3),
                "CAGR_ماهانه_% (تقریب وزن‌مساوی)_Baseline": round(bmon, 2),
                "Δدرصد_برد": round(win_all - bwin, 2),
                "Δفاکتور_سود": round(pf_w - bpf, 3),
                "Δبازده_خالص٪": round(port_return - bret, 2),
                "Δحداکثر_افت٪": round(worst_dd - bdd, 2),
                "Δمیانگین_R": round(r_w - br, 3),
            })
            # overall status
            overall_score = 0
            overall_score += 1 if (win_all - bwin) >= 0 else -1
            overall_score += 1 if (pf_w - bpf) >= 0 else -1
            overall_score += 1 if (worst_dd - bdd) <= 0 else -1
            overall_score += 1 if (port_return - bret) >= 0 else -1
            summary_row["نتیجه_تغییر"] = "بهتر" if overall_score >= 2 else ("بدتر" if overall_score <= -2 else "مخلوط/نامشخص")
            summary_row["BaselineFile"] = os.path.basename(os.path.dirname(baseline_path))
            df_out = m
        except Exception:
            df_out = df
            summary_row["نتیجه_تغییر"] = "Baseline یافت شد ولی خوانده نشد"
    else:
        df_out = df
        summary_row["نتیجه_تغییر"] = "Baseline یافت نشد"

    # اضافه کردن ردیف کل
    df_out = pd.concat([df_out, pd.DataFrame([summary_row])], ignore_index=True)
    return df_out, baseline_path

# ---------------- Main ----------------
def session_analysis(trades_df):
    """تحلیل عملکرد استراتژی بر اساس سشن معاملاتی (از روی ساعت ورود).
    معیار اصلی «مجموع R» است چون قابل جمع‌زدن و منصفانه است."""
    if trades_df is None or trades_df.empty:
        return None, None, None
    t = trades_df.copy()
    t["زمان_ورود"] = pd.to_datetime(t["زمان_ورود"], errors="coerce")
    t = t.dropna(subset=["زمان_ورود", "نتیجه_R"])
    if t.empty:
        return None, None, None

    t["ساعت_UTC"] = (t["زمان_ورود"].dt.hour + SESSION_HOUR_SHIFT) % 24
    t["سشن"] = t["ساعت_UTC"].apply(hour_to_session)
    total_r = float(t["نتیجه_R"].sum())

    def _agg(g):
        n = len(g)
        wins = int((g["نتیجه_R"] > 0).sum())
        sum_r = float(g["نتیجه_R"].sum())
        return pd.Series({
            "تعداد": n,
            "درصد_برد": round(wins / n * 100.0, 2) if n else 0.0,
            "میانگین_R": round(sum_r / n, 3) if n else 0.0,
            "مجموع_R": round(sum_r, 1),
            "سهم_از_کل_سود٪": round(sum_r / total_r * 100.0, 1) if total_r else 0.0,
        })

    by_session = t.groupby("سشن").apply(_agg).reset_index().sort_values("مجموع_R", ascending=False)
    by_hour = t.groupby(["ساعت_UTC"]).apply(_agg).reset_index().sort_values("ساعت_UTC")

    # جدول متقاطع نماد × سشن (مجموع R و میانگین R)
    piv_sum = t.pivot_table(index="نماد", columns="سشن", values="نتیجه_R", aggfunc="sum").round(1)
    piv_cnt = t.pivot_table(index="نماد", columns="سشن", values="نتیجه_R", aggfunc="count")
    piv = piv_sum.copy()
    piv.columns = [f"{c} (مجموع R)" for c in piv.columns]
    for c in piv_cnt.columns:
        piv[f"{c} (تعداد)"] = piv_cnt[c]
    piv = piv.reset_index()

    return by_session, by_hour, piv


def session_stability(trades_df):
    """تست پایداری سشن‌ها: دیتا را از وسط دو نیم می‌کند و می‌بیند آیا
    رتبه‌بندی سشن‌ها در هر دو نیمه یکسان می‌ماند (ضد بهینه‌سازی روی گذشته)."""
    if trades_df is None or trades_df.empty:
        return None
    t = trades_df.copy()
    t["زمان_ورود"] = pd.to_datetime(t["زمان_ورود"], errors="coerce")
    t = t.dropna(subset=["زمان_ورود", "نتیجه_R"]).sort_values("زمان_ورود")
    if len(t) < 20:
        return None

    t["ساعت_UTC"] = (t["زمان_ورود"].dt.hour + SESSION_HOUR_SHIFT) % 24
    t["سشن"] = t["ساعت_UTC"].apply(hour_to_session)
    mid = t["زمان_ورود"].iloc[len(t) // 2]
    first, second = t[t["زمان_ورود"] < mid], t[t["زمان_ورود"] >= mid]

    rows = []
    for name in [r[2] for r in SESSION_RANGES]:
        g1, g2 = first[first["سشن"] == name], second[second["سشن"] == name]
        if g1.empty and g2.empty:
            continue
        a1 = float(g1["نتیجه_R"].mean()) if len(g1) else 0.0
        a2 = float(g2["نتیجه_R"].mean()) if len(g2) else 0.0
        s1, s2 = float(g1["نتیجه_R"].sum()), float(g2["نتیجه_R"].sum())
        if s1 > 0 and s2 > 0:
            verdict = "✅ پایدار (در هر دو نیمه سودده)"
        elif s1 < 0 and s2 < 0:
            verdict = "❌ پایدار (در هر دو نیمه ضررده)"
        else:
            verdict = "⚠️ ناپایدار (فقط در یک نیمه سودده)"
        rows.append({
            "سشن": name,
            "نیمه۱_تعداد": len(g1), "نیمه۱_میانگین_R": round(a1, 3), "نیمه۱_مجموع_R": round(s1, 1),
            "نیمه۲_تعداد": len(g2), "نیمه۲_میانگین_R": round(a2, 3), "نیمه۲_مجموع_R": round(s2, 1),
            "نتیجه": verdict,
        })
    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values("نیمه۲_مجموع_R", ascending=False)
        out.attrs["mid"] = str(mid)
    return out


def _aggregate_mode_rows(rows, mode_col):
    """جدول مقایسه‌ی حالت‌ها: ردیف هر نماد + ردیف «کل» برای هر حالت."""
    cmp_df = pd.concat(rows, ignore_index=True)
    agg_rows = []
    for mode, g in cmp_df.groupby(mode_col, sort=False):
        n = float(g["تعداد"].sum())
        w = g["تعداد"].astype(float)
        wr = float((g["درصد_برد"] * w).sum() / n) if n > 0 else 0.0
        ar = float((g["میانگین_R"] * w).sum() / n) if n > 0 else 0.0
        agg_rows.append({
            mode_col: mode, "نماد": "کل", "تعداد": int(n),
            "درصد_برد": round(wr, 2), "میانگین_R": round(ar, 3),
            "بازده_خالص٪": round(float(g["بازده_خالص٪"].mean()), 2),
            "حداکثر_افت٪": round(float(g["حداکثر_افت٪"].max()), 2),
            "فاکتور_سود": round(float(g["فاکتور_سود"].mean()), 3),
        })
    out = pd.concat([cmp_df, pd.DataFrame(agg_rows)], ignore_index=True)
    cols = [mode_col, "نماد", "تعداد", "درصد_برد", "میانگین_R", "بازده_خالص٪", "حداکثر_افت٪", "فاکتور_سود"]
    out = out[[c for c in cols if c in out.columns]]
    return out.sort_values([mode_col, "نماد"]).reset_index(drop=True)

def portfolio_replay(trades_df, start_equity=100000.0, reserve=0.15, risk_per_trade=None,
                     max_open=None, symbols=None, max_losses_day=0, max_losses_week=0,
                     per_symbol_max_open=0, session_weights=None):
    """شبیه‌سازی «یک حساب مشترک» روی معاملات همه‌ی نمادها:
    معامله‌ها به ترتیب زمان ورود اجرا می‌شوند، ریسک هر معامله ۱٪ از اکویتی لحظه‌ای حساب است،
    و اگر تعداد پوزیشن‌های باز به سقف برسد، معامله‌ی جدید گرفته نمی‌شود (رد می‌شود).
    منطق استراتژی را تغییر نمی‌دهد؛ فقط حساب را واقعی می‌کند."""
    import heapq

    if trades_df is None or trades_df.empty:
        return None
    t = trades_df.copy()
    if symbols:
        t = t[t["نماد"].isin(list(symbols))]
    if t.empty:
        return None

    t["زمان_ورود"] = pd.to_datetime(t["زمان_ورود"], errors="coerce")
    t["زمان_خروج"] = pd.to_datetime(t["زمان_خروج"], errors="coerce")
    t = t.dropna(subset=["زمان_ورود", "زمان_خروج", "نتیجه_R"]).sort_values("زمان_ورود")
    if t.empty:
        return None
    if max_open is None:
        max_open = PORTFOLIO_MAX_OPEN
    open_cap = max_open if (max_open and max_open > 0) else 10**9  # 0 = بدون سقف
    if risk_per_trade is None:
        risk_per_trade = PORTFOLIO_RISK_PER_TRADE

    from collections import deque

    eq = float(start_equity); peak = eq; max_dd = 0.0
    open_heap = []   # (زمان_خروج, ردیف, مبلغ_ریسک, R)
    curve = []
    taken = skipped = 0
    skipped_losslimit = 0
    skipped_persym = 0
    win_amt = loss_amt = 0.0
    rs = []
    seq = 0
    loss_times = deque()  # زمان بسته شدن ضررها (برای محدودیت روز/هفته)
    open_by_sym = {}      # تعداد ترید باز هر نماد (برای سقف هر چارت)

    def close_until(t_now):
        nonlocal eq, peak, max_dd, win_amt, loss_amt
        while open_heap and open_heap[0][0] <= t_now:
            xt, _, ramt, r, sym_ = heapq.heappop(open_heap)
            open_by_sym[sym_] = max(0, open_by_sym.get(sym_, 0) - 1)
            pnl = ramt * r
            eq += pnl
            if pnl > 0: win_amt += pnl
            else:
                loss_amt += -pnl
                loss_times.append(xt)
            rs.append(r)
            peak = max(peak, eq)
            dd = (peak - eq) / peak if peak > 0 else 0.0
            max_dd = max(max_dd, dd)
            curve.append((xt, eq))

    # وزن ریسک هر معامله بر اساس سشنِ ورود (اگر وزن‌دهی فعال باشد)
    if session_weights is None and USE_DEFAULT_SESSION_WEIGHTS:
        session_weights = DEFAULT_SESSION_WEIGHTS
    if session_weights:
        _sess = ((t["زمان_ورود"].dt.hour + SESSION_HOUR_SHIFT) % 24).apply(hour_to_session)
        t = t.assign(_w=_sess.map(lambda s: float(session_weights.get(s, 1.0))))
    else:
        t = t.assign(_w=1.0)

    for sym, entry_t, exit_t, r, w in zip(t["نماد"], t["زمان_ورود"], t["زمان_خروج"],
                                          t["نتیجه_R"], t["_w"]):
        close_until(entry_t)
        if len(open_heap) >= open_cap:
            skipped += 1
            continue
        # سقف «هر چارت»: مثل ربات لایو، هر نماد هم‌زمان فقط N ترید باز
        if per_symbol_max_open and open_by_sym.get(sym, 0) >= per_symbol_max_open:
            skipped_persym += 1
            continue

        # سپر ایمنی: بعد از N ضرر در روز/هفته، ورود جدید ممنوع تا دوره عوض شود
        if max_losses_day or max_losses_week:
            cutoff = entry_t - pd.Timedelta(days=8)
            while loss_times and loss_times[0] < cutoff:
                loss_times.popleft()
            blocked = False
            if max_losses_day:
                ld = sum(1 for lt in loss_times if lt.date() == entry_t.date())
                if ld >= max_losses_day:
                    blocked = True
            if not blocked and max_losses_week:
                iso = entry_t.isocalendar()
                lw = sum(1 for lt in loss_times
                         if lt.isocalendar()[0] == iso[0] and lt.isocalendar()[1] == iso[1])
                if lw >= max_losses_week:
                    blocked = True
            if blocked:
                skipped_losslimit += 1
                continue

        ramt = eq * (1.0 - reserve) * risk_per_trade * float(w)
        seq += 1
        heapq.heappush(open_heap, (exit_t, seq, ramt, float(r), sym))
        open_by_sym[sym] = open_by_sym.get(sym, 0) + 1
        taken += 1
    close_until(pd.Timestamp.max)

    wins = sum(1 for r in rs if r > 0)
    stats = pd.DataFrame([{
        "تعداد_نماد": int(t["نماد"].nunique()),
        "وزن‌دهی_سشن": "فعال (تهاجمی)" if session_weights else "خاموش",
        "سقف_پوزیشن_همزمان": int(max_open),
        "ریسک_هر_معامله٪": round(risk_per_trade * 100.0, 2),
        "معاملات_انجام‌شده": int(taken),
        "معاملات_ردشده_به_خاطر_سقف": int(skipped),
        "ردشده_سقف_هر_چارت": int(skipped_persym),
        "ردشده_محدودیت_ضرر": int(skipped_losslimit),
        "درصد_برد": round(wins / len(rs) * 100.0, 2) if rs else 0.0,
        "فاکتور_سود": round(win_amt / loss_amt, 3) if loss_amt > 0 else 999.0,
        "بازده_خالص٪": round((eq - start_equity) / start_equity * 100.0, 2),
        "حداکثر_افت٪": round(max_dd * 100.0, 2),
        "اکویتی_نهایی": round(eq, 2),
    }])

    curve_df = pd.DataFrame(curve, columns=["زمان", "اکویتی"])

    def _period_returns(fmt):
        rows = []
        prev = start_equity
        c = curve_df.copy()
        c["دوره"] = c["زمان"].dt.to_period(fmt).astype(str)
        for per, g in c.groupby("دوره"):
            e = float(g["اکویتی"].iloc[-1])
            rows.append({"دوره": per, "بازده٪": round((e - prev) / prev * 100.0, 2),
                         "اکویتی_پایان": round(e, 2)})
            prev = e
        return pd.DataFrame(rows)

    return {"stats": stats,
            "yearly": _period_returns("Y").rename(columns={"دوره": "سال"}),
            "monthly": _period_returns("M").rename(columns={"دوره": "ماه"})}


def live_book_report(book, trades_df, alloc_df=None):
    """گزارش حساب در حالت «عین لایو».

    اینجا دیگر هیچ فیلتری روی معاملات اعمال نمی‌شود — سقف‌ها موقع ساخته شدن معامله
    اعمال شده‌اند، پس این تابع فقط همان حساب واقعی را گزارش می‌کند.
    """
    curve_df = pd.DataFrame(book.equity_curve, columns=["زمان", "اکویتی"])
    rs = trades_df["نتیجه_R"].astype(float) if (trades_df is not None and not trades_df.empty) else pd.Series(dtype=float)
    wins = int((rs > 0).sum())
    win_amt = float(rs[rs > 0].sum())
    loss_amt = float(rs[rs < 0].abs().sum())

    peak_pending = int(alloc_df["سفارش_تخصیص‌یافته"].max()) if (alloc_df is not None and not alloc_df.empty) else 0
    avg_pending = round(float(alloc_df["سفارش_تخصیص‌یافته"].mean()), 2) if (alloc_df is not None and not alloc_df.empty) else 0.0
    peak_open = int(alloc_df["پوزیشن_باز"].max()) if (alloc_df is not None and not alloc_df.empty) else 0

    stats = pd.DataFrame([{
        "حالت": "عین لایو (همه‌ی نمادها هم‌زمان روی یک حساب)",
        "تعداد_نماد": int(trades_df["نماد"].nunique()) if (trades_df is not None and not trades_df.empty) else 0,
        "وزن‌دهی_سشن": "فعال" if book.session_weights else "خاموش",
        "سقف_سفارش_کل_حساب": int(LIVE_MAX_PENDING_TOTAL),
        "سقف_پوزیشن_کل_حساب": int(book.max_open_total),
        "سقف_سفارش_هر_نماد": int(LIVE_MAX_PENDING_PER_SYMBOL),
        "ریسک_هر_معامله٪": round(book.risk_per_trade * 100.0, 2),
        "معاملات_انجام‌شده": int(len(rs)),
        "درصد_برد": round(wins / len(rs) * 100.0, 2) if len(rs) else 0.0,
        "فاکتور_سود": round(win_amt / loss_amt, 3) if loss_amt > 0 else 999.0,
        "بازده_خالص٪": round((book.equity - book.start_equity) / book.start_equity * 100.0, 2),
        "حداکثر_افت٪": round(book.max_dd * 100.0, 2),
        "اکویتی_نهایی": round(book.equity, 2),
        "بیشترین_سفارش_همزمان": peak_pending,
        "میانگین_سفارش_همزمان": avg_pending,
        "بیشترین_پوزیشن_همزمان": peak_open,
    }])

    def _period_returns(fmt):
        rows = []
        prev = book.start_equity
        if curve_df.empty:
            return pd.DataFrame(rows)
        c = curve_df.copy()
        c["زمان"] = pd.to_datetime(c["زمان"], errors="coerce")
        c["دوره"] = c["زمان"].dt.to_period(fmt).astype(str)
        for per, g in c.groupby("دوره"):
            e = float(g["اکویتی"].iloc[-1])
            rows.append({"دوره": per, "بازده٪": round((e - prev) / prev * 100.0, 2),
                         "اکویتی_پایان": round(e, 2)})
            prev = e
        return pd.DataFrame(rows)

    return {"stats": stats,
            "yearly": _period_returns("Y").rename(columns={"دوره": "سال"}),
            "monthly": _period_returns("M").rename(columns={"دوره": "ماه"})}


def _design_trades(results):
    tr = [r[2] for r in results.values() if r[2] is not None and not r[2].empty]
    return pd.concat(tr, ignore_index=True) if tr else pd.DataFrame(columns=["نتیجه_R", "زمان_ورود"])


def _pf(r):
    win = float(r[r > 0].sum())
    los = float(r[r < 0].abs().sum())
    return round(win / los, 3) if los > 0 else 999.0


def design_symbol_table(results, book):
    """جدول نمادها برای سربرگ هر آزمایش — همان ستون‌های سربرگ «خلاصه» + ردیف «کل»."""
    rows = []
    for sym, r in results.items():
        m = r[0].iloc[0]
        rows.append({"نماد": sym, "تعداد": int(m["تعداد"]), "درصد_برد": m["درصد_برد"],
                     "فاکتور_سود": m["فاکتور_سود"], "میانگین_R": m["میانگین_R"],
                     "سهم_از_بازده_حساب٪": m["بازده_خالص٪"], "افت_سهم_این_نماد٪": m["حداکثر_افت٪"],
                     "فاصله_استاپ_پیپ": m.get("فاصله_استاپ_پیپ", 0.0),
                     "هزینه_هر_معامله_R": m.get("هزینه_هر_معامله_R", 0.0),
                     "اسپرد_پیپ": m.get("اسپرد_پیپ", 0.0)})
    tr = _design_trades(results)
    R = tr["نتیجه_R"].astype(float)
    C = tr["هزینه_R"].astype(float) if "هزینه_R" in tr.columns else pd.Series(dtype=float)
    rows.append({"نماد": "کل", "تعداد": int(len(R)),
                 "درصد_برد": round(float((R > 0).mean() * 100.0), 2) if len(R) else 0.0,
                 "فاکتور_سود": _pf(R), "میانگین_R": round(float(R.mean()), 3) if len(R) else 0.0,
                 "سهم_از_بازده_حساب٪": round((book.equity / book.start_equity - 1.0) * 100.0, 2),
                 "افت_سهم_این_نماد٪": round(book.max_dd * 100.0, 2),
                 "هزینه_هر_معامله_R": round(float(C.median()), 3) if len(C) else 0.0})
    return pd.DataFrame(rows)


def stop_causes(trades, frames, trend_mode, max_days=None):
    """دلیل هر استاپ کامل (معامله‌ی ضررده که با حدضرر بسته شد) — فقط برای گزارش، نه معامله:
      «روند ۴ساعته»: بعد از ورود، روند ۴ساعته خلاف جهت معامله شد پیش از آنکه قیمت به تارگت برسد.
      «بیس ۱۵دقیقه»: روند ۴ساعته سر جایش ماند و قیمت بعد از زدن استاپ به تارگت رسید.
      «نامشخص»: تا max_days روز نه روند برگشت نه تارگت خورد.
    خروجی: (برچسب هر معامله — "" برای غیر استاپ، عمق خلاف جهت برحسب R برای «بیس» یا NaN)."""
    max_days = STOP_CAUSE_DAYS if max_days is None else max_days
    labels = pd.Series("", index=trades.index, dtype=object)
    depth = pd.Series(np.nan, index=trades.index, dtype=float)
    if trades is None or trades.empty:
        return labels, depth
    win = np.timedelta64(pd.Timedelta(days=max_days))
    for sym, g in trades.groupby("نماد"):
        if sym not in frames:
            continue
        zdf, tdf_ = frames[sym][0], frames[sym][1]
        if trend_mode == "legacy":
            tr = trend_from_swings(tdf_, n=1).to_numpy()
        else:
            tr = structure_trend(tdf_, n=STRUCT_SWING_N, use_trendline=(trend_mode == "choch_tl"),
                                 tl_n=TL_SWING_N).to_numpy()
        tsp = tdf_["time"].diff().dropna().median()
        known = (pd.to_datetime(tdf_["time"]) + tsp).to_numpy(dtype="datetime64[ns]")
        sgn = np.sign(tr)
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


def stop_cause_table(trades, frames, trend_mode, max_days=None):
    """جدول دلیل استاپ‌ها برای هر نماد + ردیف «کل» (از روی stop_causes)."""
    cols = ["نماد", "تعداد_معامله", "استاپ_کامل", "روند_۴ساعته_برگشت", "٪_روند",
            "بیس_۱۵دقیقه_(جهت_درست_بود)", "٪_بیس", "نامشخص", "٪_نامشخص",
            "بیس_عمق_خلاف_جهت_R_(میانه)"]
    if trades is None or trades.empty:
        return pd.DataFrame(columns=cols)
    labels, depth = stop_causes(trades, frames, trend_mode, max_days)

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


def trades_review_table(name, results, frames, tmode):
    """همه‌ی معاملات یک اجرا با زمان‌های لازم برای پیدا کردنشان روی چارت متاتریدر (ساعت سرور بروکر).
    خروجی: (جدول برای اکسل، جدول خام برای نمودارها)"""
    tr = _design_trades(results)
    if tr.empty:
        return tr, tr
    tr = tr.sort_values("زمان_ورود").reset_index(drop=True)
    labels, depth = stop_causes(tr, frames, tmode)
    tr["دلیل_استاپ"] = labels
    tr["شماره"] = np.arange(1, len(tr) + 1)
    tr["اجرا"] = name
    pips = tr["نماد"].map(pip_size)
    out = pd.DataFrame({
        "اجرا": tr["اجرا"], "شماره": tr["شماره"], "نماد": tr["نماد"], "جهت": tr["جهت"],
        "نتیجه_R": tr["نتیجه_R"].astype(float).round(2), "علت_خروج": tr["علت_خروج"],
        "دلیل_استاپ": tr["دلیل_استاپ"],
        "شروع_بیس_۱۵دقیقه": tr["بیس_شروع"].map(_fmt_t), "پایان_بیس_۱۵دقیقه": tr["بیس_پایان"].map(_fmt_t),
        "تأیید_بیس_(کندل_چاک)": tr["زمان_تأیید_بیس"].map(_fmt_t) if "زمان_تأیید_بیس" in tr else "",
        "پراکسیمال": tr["پراکسیمال"], "دیستال": tr["دیستال"],
        "سطح_چاک_بیس": tr["سطح_چاک_بیس"] if "سطح_چاک_بیس" in tr else np.nan,
        "رسیدن_قیمت_به_بیس": tr["زمان_رسیدن_به_بیس"].map(_fmt_t) if "زمان_رسیدن_به_بیس" in tr else "",
        "چاک_۱دقیقه": tr["زمان_چاک_۱دقیقه"].map(_fmt_t) if "زمان_چاک_۱دقیقه" in tr else "",
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
    reason_en = {"حدسود": "TP", "حدضرر": "SL", "سربه‌سر (ریسک‌فری)": "BE", "پایان دیتا": "end of data",
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
        z15, m1 = frames[sym][0], frames[sym][3]
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
        ax.plot([xin], [r["ورود"]], marker="^" if r["جهت"] == "خرید" else "v", color="#1565c0", markersize=9, zorder=5)
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


def session_results_table(runs):
    """برد، باخت، سود و ضرر هر سشن (بر اساس ساعت ورود، تبدیل‌شده به UTC با SESSION_HOUR_SHIFT)."""
    rows = []
    risk_pct = LIVE_RISK_PER_TRADE * 100.0
    for name, results, _book, _tm in runs:
        tr = _design_trades(results)
        if tr.empty:
            continue
        hrs = (pd.to_datetime(tr["زمان_ورود"]) + pd.Timedelta(hours=SESSION_HOUR_SHIFT)).dt.hour
        ses = hrs.map(hour_to_session)
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


def write_simple_excel(sw, runs, frames):
    """سربرگ‌ها: «کلی» (هر اجرا: ردیف کل + نمادها)، «دلیل_استاپ‌ها» و «معاملات».
    runs: [(اسم اجرا, results, book, trend_mode)] — خروجی: جدول معاملات هر اجرا (برای نمودارها)"""
    parts, causes, reviews = [], [], []
    for name, results, book, tmode in runs:
        tbl = design_symbol_table(results, book)
        tbl = pd.concat([tbl[tbl["نماد"] == "کل"], tbl[tbl["نماد"] != "کل"]], ignore_index=True)
        tbl.insert(0, "اجرا", name)
        parts += [tbl, pd.DataFrame([{}])]
        ct = stop_cause_table(_design_trades(results), frames, tmode)
        ct.insert(0, "اجرا", name)
        causes += [ct, pd.DataFrame([{}])]
        if not ct.empty:
            t0 = ct.iloc[0]
            print(f"   دلیل {int(t0['استاپ_کامل'])} استاپ «{name}»: روند ۴ساعته {t0['٪_روند']}٪ | "
                  f"بیس ۱۵دقیقه {t0['٪_بیس']}٪ | نامشخص {t0['٪_نامشخص']}٪")
    main_tbl = pd.concat(parts, ignore_index=True)
    main_tbl.to_excel(sw, sheet_name="کلی", index=False)
    # قیف هر اجرا: چند بار قیمت به بیس رسید، چند بار چاک ۱دقیقه آمد، چند معامله شد و چرا لغو شد
    keys = [("رسیدن_به_بیس_۱۵دقیقه", "قیمت_به_بیس_رسید"), ("تأیید_چاک_۱دقیقه", "چاک_۱دقیقه_آمد"),
            ("ورود_انجام_شد", "معامله"), ("ورود_بازار_بعد_از_تأیید", "ورود_با_قیمت_بازار"),
            ("لغو_شکست_بیس_با_کلوز_۱۵دقیقه", "لغو_کلوز_پشت_بیس"),
            ("لغو_دور_شدن_بدون_ورود", "لغو_دور_شدن_بدون_ورود"),
            ("لغو_استاپ_۱دقیقه_کوچک", "لغو_استاپ_۱دقیقه_کوچک")]
    funnel = []
    for name, results, _book, _tm in runs:
        tot = {k: 0 for k, _ in keys}
        for r in results.values():
            rdf = r[1]
            if rdf is None or rdf.empty or "دلیل" not in rdf.columns:
                continue
            for k, _ in keys:
                tot[k] += int(rdf.loc[rdf["دلیل"] == k, "تعداد"].sum())
        funnel.append({"اجرا": name, **{lab: tot[k] for k, lab in keys}})
    pd.DataFrame([{"اجرا": "قیف هر اجرا (تعداد کل در همه‌ی نمادها)"}]).to_excel(
        sw, sheet_name="کلی", index=False, header=False, startrow=len(main_tbl) + 2)
    pd.DataFrame(funnel).to_excel(sw, sheet_name="کلی", index=False, startrow=len(main_tbl) + 3)
    cdf = pd.concat(causes, ignore_index=True)
    cdf.to_excel(sw, sheet_name="دلیل_استاپ‌ها", index=False)
    notes = pd.DataFrame({"توضیح": [
        "استاپ_کامل = معامله‌ی ضررده که با حدضرر بسته شد (معامله‌ای که در 2R نصفش سیو شده حساب نمی‌شود).",
        "روند_۴ساعته_برگشت = بعد از ورود، روند ۴ساعته خلاف جهت معامله شد پیش از آنکه قیمت به تارگت برسد → مشکل از روند ۴ساعته.",
        "بیس_۱۵دقیقه = روند ۴ساعته سر جایش ماند و قیمت بعد از زدن استاپ به تارگت رسید → جهت درست بود، بیس ۱۵دقیقه نگه نداشت.",
        f"نامشخص = تا {STOP_CAUSE_DAYS} روز بعد از ورود نه روند برگشت نه تارگت خورد.",
        "بیس_عمق_خلاف_جهت_R = در استاپ‌های «بیس»، قیمت پیش از رسیدن به تارگت چند R خلاف جهت رفت "
        "(نزدیک ۱ تا ۱.۵ = استاپ فقط کمی کوچک بود؛ خیلی بیشتر = خود بیس اشتباه بود).",
    ]})
    notes.to_excel(sw, sheet_name="دلیل_استاپ‌ها", index=False, startrow=len(cdf) + 2)
    # همه‌ی معاملات با زمان‌ها (ساعت سرور بروکر، همان ساعت چارت متاتریدر)
    for name, results, _book, tmode in runs:
        reviews.append((name,) + tuple(trades_review_table(name, results, frames, tmode)))
    sdf = session_results_table(runs)
    if not sdf.empty:
        sdf.to_excel(sw, sheet_name="سشن‌ها", index=False)
        pd.DataFrame({"توضیح": [
            f"سشن از روی ساعت ورود معامله؛ ساعت دیتا {SESSION_HOUR_SHIFT:+d} ساعت = UTC (SESSION_HOUR_SHIFT).",
            f"خالص_تقریبی٪_حساب = خالص R × ریسک هر معامله ({LIVE_RISK_PER_TRADE * 100:g}٪) — بدون اثر مرکب.",
        ]}).to_excel(sw, sheet_name="سشن‌ها", index=False, startrow=len(sdf) + 2)
    tabs = [t for _, t, _raw in reviews if t is not None and not t.empty]
    if tabs:
        pd.concat(tabs, ignore_index=True).to_excel(sw, sheet_name="معاملات", index=False)
    return reviews


def design_compare_row(name, results, book, mid_t, desc):
    """یک ردیف برای سربرگ «مقایسه_طراحی‌ها». نیمه‌ی اول/دوم برای دیدن اینکه بهبود واقعی است
    یا فقط در یک دوره‌ی خوش‌شانس بوده."""
    tr = _design_trades(results)
    R = tr["نتیجه_R"].astype(float)
    t_in = pd.to_datetime(tr["زمان_ورود"])
    ret = (book.equity / book.start_equity - 1.0) * 100.0
    dd = book.max_dd * 100.0
    return {"طراحی": name, "تعداد_معامله": int(len(R)),
            "درصد_برد": round(float((R > 0).mean() * 100.0), 2) if len(R) else 0.0,
            "فاکتور_سود": _pf(R), "میانگین_R": round(float(R.mean()), 3) if len(R) else 0.0,
            "بازده_کل_حساب٪": round(ret, 2), "بیشترین_افت٪": round(dd, 2),
            "بازده_به_افت": round(ret / dd, 2) if dd > 0 else None,
            "جمع_R_نیمه_اول": round(float(R[t_in < mid_t].sum()), 1),
            "جمع_R_نیمه_دوم": round(float(R[t_in >= mid_t].sum()), 1),
            "توضیح": desc}


def design_verdicts(rows):
    """حکم ساده برای هر آزمایش در برابر مبنا (ردیف اول)."""
    if not rows:
        return rows
    base = rows[0]
    base["اختلاف_بازده_با_مبنا٪"] = 0.0
    if base["بازده_کل_حساب٪"] > 0 and base["جمع_R_نیمه_اول"] > 0 and base["جمع_R_نیمه_دوم"] > 0:
        base["حکم"] = "مبنا — ✅ سودده در هر دو نیمه"
    elif base["بازده_کل_حساب٪"] > 0:
        base["حکم"] = "مبنا — ⚠️ سودده ولی فقط در یک نیمه"
    else:
        base["حکم"] = "مبنا — ❌ سودده نیست"
    for r in rows[1:]:
        r["اختلاف_بازده_با_مبنا٪"] = round(r["بازده_کل_حساب٪"] - base["بازده_کل_حساب٪"], 2)
        h1, h2 = r["جمع_R_نیمه_اول"], r["جمع_R_نیمه_دوم"]
        better_both = h1 > base["جمع_R_نیمه_اول"] and h2 > base["جمع_R_نیمه_دوم"]
        if r["بازده_کل_حساب٪"] > 0 and h1 > 0 and h2 > 0:
            r["حکم"] = "✅ سودده در هر دو نیمه"
        elif better_both:
            r["حکم"] = "➕ بهتر از مبنا در هر دو نیمه (ولی هنوز سودده نیست)"
        elif r["بازده_کل_حساب٪"] > base["بازده_کل_حساب٪"]:
            r["حکم"] = "⚠️ بهتر از مبنا ولی فقط در یک نیمه — قابل اعتماد نیست"
        else:
            r["حکم"] = "❌ بدتر از مبنا"
    return rows


def stability_split_test(trades_df, min_trades=None):
    """تست پایداری: کارنامه‌ی هر نماد در نیمه‌ی اول در برابر نیمه‌ی دوم بازه.

    چرا مهم است؟ نمادی که کل سودش از یک دوره‌ی خوش‌شانس آمده، در نیمه‌ی دیگر
    ضررده است. چنین نمادی لبه‌ی واقعی ندارد و اعتماد به آن یعنی برازش به گذشته.

    فقط از «میانگین R» و «فاکتور سود» قضاوت می‌کنیم چون مستقل از اندازه‌ی حساب‌اند
    (سود دلاری با بزرگ شدن حساب رشد می‌کند و نیمه‌ی دوم را الکی برنده نشان می‌دهد).
    """
    if trades_df is None or trades_df.empty:
        return None
    min_trades = STABILITY_MIN_TRADES if min_trades is None else min_trades

    t = trades_df.copy()
    t["زمان_ورود"] = pd.to_datetime(t["زمان_ورود"], errors="coerce")
    t = t.dropna(subset=["زمان_ورود"])
    if t.empty:
        return None

    t0, t1 = t["زمان_ورود"].min(), t["زمان_ورود"].max()
    mid = t0 + (t1 - t0) / 2

    def half_stats(g):
        if g.empty:
            return dict(تعداد=0, درصد_برد=0.0, میانگین_R=0.0, فاکتور_سود=0.0, جمع_R=0.0)
        r = g["نتیجه_R"].astype(float)
        win = float(r[r > 0].sum())
        los = float(r[r < 0].abs().sum())
        return dict(تعداد=int(len(r)),
                    درصد_برد=round(float((r > 0).mean() * 100.0), 2),
                    میانگین_R=round(float(r.mean()), 3),
                    فاکتور_سود=round(win / los, 3) if los > 0 else 999.0,
                    جمع_R=round(float(r.sum()), 2))

    rows = []
    for sym, g in t.groupby("نماد"):
        a = half_stats(g[g["زمان_ورود"] < mid])
        b = half_stats(g[g["زمان_ورود"] >= mid])

        if a["تعداد"] < min_trades or b["تعداد"] < min_trades:
            verdict = "نمونه‌ی کم — قضاوت نکن"
        elif a["میانگین_R"] > 0 and b["میانگین_R"] > 0:
            verdict = "پایدار ✅"
        elif a["میانگین_R"] <= 0 and b["میانگین_R"] <= 0:
            verdict = "در هر دو نیمه ضررده ❌"
        elif b["میانگین_R"] > 0:
            verdict = "فقط نیمه‌ی دوم خوب بود ⚠️"
        else:
            verdict = "فقط نیمه‌ی اول خوب بود ⚠️"

        rows.append({
            "نماد": sym,
            "نیمه۱_تعداد": a["تعداد"], "نیمه۱_برد٪": a["درصد_برد"],
            "نیمه۱_میانگین_R": a["میانگین_R"], "نیمه۱_فاکتور_سود": a["فاکتور_سود"],
            "نیمه۲_تعداد": b["تعداد"], "نیمه۲_برد٪": b["درصد_برد"],
            "نیمه۲_میانگین_R": b["میانگین_R"], "نیمه۲_فاکتور_سود": b["فاکتور_سود"],
            "اختلاف_میانگین_R": round(b["میانگین_R"] - a["میانگین_R"], 3),
            "حکم": verdict,
        })

    out = pd.DataFrame(rows).sort_values("نیمه۲_میانگین_R", ascending=False)
    out.insert(0, "مرز_دو_نیمه", mid.strftime("%Y-%m-%d"))
    return out.reset_index(drop=True)


def leave_one_out_test(frames, spreads, **kw):
    """تست حذف تک‌نماد: حساب بدون هر نماد چقدر بهتر/بدتر می‌شود؟

    چون نمادها سر ۸ جای سفارش با هم رقابت می‌کنند، حذف یک نماد فقط معاملاتش را
    کم نمی‌کند — جای خالی‌اش به بقیه می‌رسد. پس تنها راه درست این است که کل
    بک‌تست بدون آن نماد دوباره اجرا شود.
    """
    def run(fr, label):
        _res, bk, _al = portfolio_live_replay(fr, spreads, **kw)
        tr = [r[2] for r in _res.values() if r[2] is not None and not r[2].empty]
        n = int(sum(len(x) for x in tr))
        return {"حالت": label,
                "بازده٪": round((bk.equity / bk.start_equity - 1.0) * 100.0, 2),
                "حداکثر_افت٪": round(bk.max_dd * 100.0, 2),
                "تعداد_معامله": n}

    print("   [۰/%d] سبد کامل..." % len(frames))
    base = run(frames, "سبد کامل (مبنا)")
    rows = [base]

    for i, sym in enumerate(list(frames.keys()), start=1):
        print(f"   [{i}/{len(frames)}] بدون {sym}...")
        sub = {k: v for k, v in frames.items() if k != sym}
        if not sub:
            continue
        r = run(sub, f"بدون {sym}")
        r["Δبازده٪"] = round(r["بازده٪"] - base["بازده٪"], 2)
        r["Δافت٪"] = round(r["حداکثر_افت٪"] - base["حداکثر_افت٪"], 2)
        rows.append(r)

    out = pd.DataFrame(rows)

    # قضاوت بر اساس «بازده به ازای هر واحد افت» — نه علامتِ تنهای بازده و افت.
    # وگرنه حالتی که بازده را ۱۸۰٪ بهتر و افت را ۰.۴٪ بدتر می‌کند، اشتباهاً
    # «مبادله» برچسب می‌خورد در حالی که آشکارا معامله‌ی خوبی است.
    out["بازده_به_افت"] = (out["بازده٪"] / out["حداکثر_افت٪"].replace(0, np.nan)).round(1)
    base_ratio = float(out["بازده_به_افت"].iloc[0])
    out["Δبازده_به_افت"] = (out["بازده_به_افت"] - base_ratio).round(1)

    def _verdict(row):
        if pd.isna(row.get("Δبازده٪")):
            return ""
        d = row["Δبازده_به_افت"]
        if d >= base_ratio * 0.10:
            return "حذفش حساب را واضح بهتر می‌کند ✅"
        if d > 0:
            return "کمی بهتر — قاطع نیست ➕"
        if d <= -base_ratio * 0.10:
            return "حذفش حساب را واضح بدتر می‌کند ❌"
        return "کمی بدتر — قاطع نیست ➖"

    out["حکم"] = out.apply(_verdict, axis=1)
    out = pd.concat([out.iloc[[0]],
                     out.iloc[1:].sort_values("Δبازده_به_افت", ascending=False)],
                    ignore_index=True)
    cols = ["حالت", "تعداد_معامله", "بازده٪", "Δبازده٪", "حداکثر_افت٪", "Δافت٪",
            "بازده_به_افت", "Δبازده_به_افت", "حکم"]
    return out[[c for c in cols if c in out.columns]]


def main():
    global BACKTEST_START, BACKTEST_END
    version_name = os.path.basename(os.getcwd())
    outdir = os.path.join(os.getcwd(), "خروجی")
    os.makedirs(outdir, exist_ok=True)

    years = None  # از 2023 تا پایان داده، به‌صورت پویا محاسبه می‌شود

    # Spread estimates (edit if needed) — جدولش بالای فایل است (SPREAD_TABLE)
    spreads = dict(SPREAD_TABLE)

    changes = [
        "نماد EURUSD به‌دلیل دراودان بالا حذف شد و نماد GBPJPY اضافه شد.",
        "خروجی‌ها محدود شد: فقط تنظیمات_بکتست.json، ژورنال.txt، ژورنال_این_ورژن.pdf، نتایج_اعدادی.xlsx",
        "نتایج_اعدادی.xlsx شامل ستون‌های مقایسه با نسخه قبلی (اگر پیدا شود) است."
    ]
    upgrades = [
        "گزارش زون‌محور: برای هر زون فقط یک نتیجه نهایی (FinalStatus/FinalReason)",
        "گزارش رویدادها: Touch1/Touch2/ثبت سفارش/لغو/پر شدن/خروج با زمان دقیق",
        "دلایل حذف برحسب زون با درصد واقعی (نه شمارش رویداد تکراری)",
        "خروجی‌ها محدود شد: فقط نتایج_اعدادی.xlsx + ژورنال (txt/pdf) + تنظیمات_بکتست.json"
    ]

    q_answers = {
        "چرا تغییری ایجاد کردم؟": "برای اینکه اندازه‌گیری علمی و قابل اعتماد شود؛ اول اندازه‌گیری را دقیق می‌کنیم، بعد تصمیم روی قوانین می‌گیریم.",
        "انتظارم چی بود؟": "اینکه بفهمیم دقیقاً از کل زون‌ها چند درصد در هر مرحله حذف می‌شوند و گلوگاه اصلی کجاست.",
        "چه نتیجه‌ای رخ داد؟": "در فایل نتایج_اعدادی.xlsx ستون «نتیجه_تغییر» و ستون‌های Δ (اختلاف) نشان می‌دهد حذف EURUSD و اضافه شدن GBPJPY نسبت به نسخه قبلی بهتر/بدتر شده است. اگر نسخه قبلی پیدا نشود، در همان فایل درج می‌شود: Baseline یافت نشد.",
        "چه تغییری ایجاد کردم؟": "نماد EURUSD به‌دلیل دراودان بالا حذف شد و نماد GBPJPY اضافه شد."
    }

    # DATA DIR: folder '0' on Desktop (your screenshot)
    datadir = os.path.join(os.path.expandvars(r"%USERPROFILE%"), "Desktop", "0")

    # دیتای هر نماد: XAUUSD.zip یا پوشه‌ی بازشده‌ی XAUUSD (با CSVهای داخلش)
    zip_files = find_data_sources(datadir)
    if not zip_files:
        rars = glob.glob(os.path.join(datadir, "*.rar"))
        hint = (" — فایل‌های اینجا RAR هستند؛ بازشان کن (Extract) یا همان ZIPهای خروجی export_data را بگذار."
                if rars else "")
        raise FileNotFoundError(f"هیچ دیتایی (ZIP یا پوشه‌ی CSV) در مسیر دیتا پیدا نشد: {datadir}{hint}")

    # اسپرد واقعی متاتریدر خودت (spreads.csv در پوشه‌ی دیتا)؛ نمادهایی که در آن نیستند → جدول تقریبی
    mt5_spreads = load_mt5_spreads(datadir)
    if mt5_spreads:
        spreads.update(mt5_spreads)
        SPREAD_TABLE.update(mt5_spreads)
        print("📏 اسپرد هر نماد از spreads.csv (متاتریدر خودت): " + " | ".join(
            f"{k} {v / pip_size(k):.1f}" for k, v in sorted(mt5_spreads.items())) + " پیپ")
    else:
        print("⚠️ spreads.csv در پوشه‌ی دیتا نیست → اسپرد از جدول تقریبی. برای اسپرد واقعی export_spreads.bat را اجرا کن.")

    all_metrics=[]
    all_reasons=[]
    all_trades=[]
    all_zones=[]
    all_events=[]
    all_zone_reasons=[]
    entry_mode_rows=[]
    rr_mode_rows=[]
    minrisk_mode_rows=[]
    distcancel_mode_rows=[]
    manage_mode_rows=[]
    sl_mode_rows=[]
    quality_mode_rows=[]
    max_data_time = None

    # --- همه‌ی دیتاها یک‌جا خوانده می‌شود (در حالت «عین لایو» همه با هم لازم‌اند) ---
    _tz, _tt, _tb = TF_SETS[STRATEGY_TF]
    print(f"🕒 تایم‌فریم‌های استراتژی (STRATEGY_TF = \"{STRATEGY_TF}\"): "
          f"زون و ورود -{_tz} | روند/رنج -{_tt} | زون بزرگ -{_tb}")
    print("📐 قوانین استراتژی:")
    print(f"   ورود: پراکسیمال {DEFAULT_ENTRY_OFF*100:+.0f}٪ ارتفاع بیس (مثبت = بیرون، به سمت قیمت) | "
          f"استاپ: {DEFAULT_SL_OFF*100:.0f}٪ پشت دیستال | تارگت: {DEFAULT_RR:g}R")
    print(f"   روند (تایم روند): {TREND_MODE} | سقف/کف ساختار: {STRUCT_SWING_N} کندل هر طرف | "
          f"فقط هم‌جهت روند: {'بله' if TRADE_WITH_TREND_ONLY else 'خیر'}"
          f"{' (۴ساعته و ۱۵دقیقه)' if ZONE_TF_TREND_REQUIRED else ' (فقط ۴ساعته)'} | "
          f"فیلتر رنج: {'روشن' if RANGE_FILTER else 'خاموش'}")
    print(f"   بیس: کنسالیدیشن اوی {'تا ' + str(LEGOUT_CLEAR_BARS) + ' کندل' if LEGOUT_CLEAR_BARS else 'خاموش'} | "
          f"لگ‌اوت قوی {'≥ ' + str(MIN_LEGOUT_BODY_ATR) + '×ATR' if MIN_LEGOUT_BODY_ATR else 'خاموش'} | "
          f"تأیید چاک {'روشن' if CHOCH_CONFIRM else 'خاموش'} (۱دقیقه: بیس‌های چسبیده یکی، ≤{CHOCH_CLUSTER_MAX_BARS} کندل و "
          f"≤{CHOCH_CLUSTER_GAP_ATR:g}×ATR) | بی‌اعتباری با کلوز پشت بیس: "
          f"{'روشن' if ZONE_INVALIDATE_ON_CLOSE else 'خاموش'}")
    _has_big = TF_SETS[STRATEGY_TF][2] is not None
    print(f"   تایم بالا: داخل زون مخالف {'ممنوع' if HTF_ZONE_FILTER else 'آزاد'} | "
          f"فاصله تا زون مخالف {'≥ ' + str(OPP_ZONE_ROOM_R) + 'R' if OPP_ZONE_ROOM_R else 'خاموش'} | "
          f"فیبو {('بای زیر ' + str(FIB_BUY_MAX) + '، سل بالای ' + str(FIB_SELL_MIN)) if (FIB_FILTER and _has_big) else 'خاموش (تایم روزانه ندارد)' if FIB_FILTER else 'خاموش'} | "
          f"سی‌پی پشت‌سرهم: {MAX_CONSECUTIVE_CP if MAX_CONSECUTIVE_CP else 'خاموش'}")
    print(f"   تأیید ۱دقیقه: اوردرِ بعد از تأیید با دور شدن {LTF_CANCEL_R:g}R بدون پر شدن لغو | "
          f"ورود روی بیس ۱دقیقه فقط اگر استاپ ≥ {LTF_MIN_RISK_SPREAD:g}× اسپرد")
    print(f"   بازه‌ی معامله: {BACKTEST_START.date()} تا {BACKTEST_END.date() if BACKTEST_END is not None else 'پایان دیتا'} "
          f"(گرم‌کردن {WARMUP_DAYS} روز قبلش)")
    print("🔧 تنظیمات واقع‌بینی بک‌تست:")
    print(f"   کندل ورود بدون تایم پایین‌تر: {ENTRY_BAR_MODE}"
          f"{'  ⚠️ (خوش‌بینانه — فقط برای مقایسه)' if ENTRY_BAR_MODE == 'optimistic' else ''}")
    print(f"   سفارش روی لمسِ همین کندل: {'از کندل بعد (مثل لایو)' if NO_SAME_BAR_TOUCH_FILL else '⚠️ همین کندل (نگاه به آینده)'}")
    print(f"   مدل Bid/Ask با اسپرد: {'روشن' if MODEL_BID_ASK else 'خاموش'}")
    print(f"   ریسک هر معامله: {LIVE_RISK_PER_TRADE * 100:g}٪ | وزن سشن: "
          f"{'روشن' if USE_DEFAULT_SESSION_WEIGHTS else 'خاموش (ریسک همه‌ی سشن‌ها یکسان)'} | "
          f"کمیسیون: {'ندارد' if COMMISSION_SPREAD_MULT == 0 else f'{COMMISSION_SPREAD_MULT:g}× اسپرد'}")
    frames = {}
    no_ltf = []
    for zp in zip_files:
        symbol = os.path.basename(zp).split(".")[0]  # e.g. USDJPY.W.D.H4.zip => USDJPY
        h4, d1, w1, m15 = load_timeframes_from_zip(zp)
        if m15 is None and USE_M15 and symbol not in LIVE_EXCLUDE_SYMBOLS:
            no_ltf.append(symbol)
        if not h4.empty:
            end_t = pd.to_datetime(h4["time"].max(), errors="coerce")
            if pd.notna(end_t):
                max_data_time = end_t if max_data_time is None else max(max_data_time, end_t)
        if symbol in LIVE_EXCLUDE_SYMBOLS:
            print(f"⛔ {symbol}: طبق LIVE_EXCLUDE_SYMBOLS از سبد کنار گذاشته شد")
            continue
        frames[symbol] = (h4, d1, w1, m15)

    # بازه‌ی بک‌تست با دیتای ۱دقیقه هماهنگ می‌شود: اگر متاتریدر دیتای ۱دقیقه‌ی کل بازه را نداشت،
    # فقط جایی بک‌تست می‌شود که همه‌ی نمادها دیتای ۱دقیقه دارند.
    _ltf = [f[3] for f in frames.values() if f[3] is not None and len(f[3])]
    if LTF_MODE and _ltf:
        l0 = max(pd.Timestamp(x["time"].min()) for x in _ltf)
        l1 = min(pd.Timestamp(x["time"].max()) for x in _ltf)
        s0, e0 = BACKTEST_START, (BACKTEST_END if BACKTEST_END is not None else l1)
        ns, ne = max(s0, l0), min(e0, l1)
        if ns >= ne:                      # هیچ هم‌پوشانی ندارند → کل بازه‌ی دیتای ۱دقیقه
            ns, ne = l0, l1
        if ns > s0 + pd.Timedelta(days=1) or ne < e0 - pd.Timedelta(days=1):
            print(f"ℹ️ دیتای ۱دقیقه فقط از {l0:%Y-%m-%d %H:%M} تا {l1:%Y-%m-%d %H:%M} هست → بازه‌ی بک‌تست: "
                  f"{ns:%Y-%m-%d} تا {ne:%Y-%m-%d} (به‌جای {s0:%Y-%m-%d} تا {e0:%Y-%m-%d})")
            BACKTEST_START, BACKTEST_END = pd.Timestamp(ns), pd.Timestamp(ne)

    if USE_M15:
        if no_ltf and len(no_ltf) == len(frames):
            _finer = "M1/M5" if STRATEGY_TF == "M15" else "M1/M5/M15"
            print(f"   دیتای تایم پایین‌تر ({_finer}) داخل ZIPها نیست → کندل ورود با حالت «{ENTRY_BAR_MODE}» حساب می‌شود.")
        elif no_ltf:
            print(f"   ⚠️ این نمادها دیتای تایم پایین‌تر ندارند و با حالت «{ENTRY_BAR_MODE}» حساب می‌شوند: {', '.join(no_ltf)}")
        else:
            print("   دیتای تایم پایین‌تر برای همه‌ی نمادها پیدا شد → ترتیب اتفاقات داخل کندل از روی آن حساب می‌شود.")

    # --- گزارش دیتایی که واقعاً خوانده شد ---
    # نبودن دیتا خودش خطا می‌دهد و معلوم است؛ خطر واقعی «دیتای اشتباه» است که
    # بی‌سروصدا نتیجه‌ی غلط می‌دهد. پس همان اول کار دقیقاً می‌نویسیم چه خواندیم.
    _starts = [f[0]["time"].min() for f in frames.values() if not f[0].empty]
    _ends = [f[0]["time"].max() for f in frames.values() if not f[0].empty]
    if _starts:
        d0, d1_ = min(_starts), max(_ends)
        print(f"\n📂 دیتا از: {datadir}")
        print(f"   {len(frames)} نماد | از {pd.Timestamp(d0).date()} تا {pd.Timestamp(d1_).date()}"
              f"  ({(pd.Timestamp(d1_) - pd.Timestamp(d0)).days / 365.25:.1f} سال)")
        _short = [s for s, f in frames.items()
                  if not f[0].empty and pd.Timestamp(f[0]["time"].min()) > pd.Timestamp(d0) + pd.Timedelta(days=90)]
        if _short:
            print(f"   ⚠️ این نمادها دیتای کوتاه‌تری دارند: {', '.join(_short)}")
        if pd.Timestamp(d0) < BACKTEST_START:
            print(f"   معامله‌ها از {BACKTEST_START.date()}؛ {WARMUP_DAYS} روز قبلش فقط برای گرم‌کردن روند و زون‌ها "
                  f"خوانده می‌شود و قبل‌ترش استفاده نمی‌شود.")

    live_results = None
    live_book = None
    live_alloc = None
    if LIVE_MODE:
        _cap = lambda v: str(v) if v and v > 0 else "بی‌سقف"
        print(f"\n🔗 حالت «عین لایو»: {len(frames)} نماد هم‌زمان روی یک حساب | "
              f"سفارش کل حساب: {_cap(LIVE_MAX_PENDING_TOTAL)} | پوزیشن باز کل حساب: {_cap(LIVE_MAX_OPEN_TOTAL)} | "
              f"سفارش هر نماد: {_cap(LIVE_MAX_PENDING_PER_SYMBOL)}")
        if LTF_MODE and all(fr[3] is None for fr in frames.values()):
            raise ValueError("دیتای ۱دقیقه داخل ZIPها نیست (فایل -1.csv) ولی بک‌تست با تأیید ۱دقیقه است. "
                             "export_data را با تایم M1 اجرا کن و ZIPهای تازه را در پوشه‌ی 0 بگذار.")
        print(f"   [اجرای اصلی] {LTF_RUN_NAMES.get(LTF_MODE, LTF_MODE)} ...", flush=True)
        live_results, live_book, live_alloc = portfolio_live_replay(
            frames, spreads, entry_off=DEFAULT_ENTRY_OFF, sl_off=DEFAULT_SL_OFF,
            rr=DEFAULT_RR, manage_mode=DEFAULT_MANAGE, min_risk_atr=DEFAULT_MIN_RISK_ATR,
            invalidate_on_breach=ZONE_INVALIDATE_ON_CLOSE, ltf_mode=LTF_MODE)
        print(f"   اکویتی پایانی: {live_book.equity:,.0f} | "
              f"بازده {(live_book.equity/live_book.start_equity-1)*100:.2f}٪ | "
              f"حداکثر افت {live_book.max_dd*100:.2f}٪")

    # --- آزمایش تغییر طراحی: هر تغییر جداگانه، روی همان دیتا و همان حساب «عین لایو» ---
    design_sheets, design_rows = [], []
    simple_runs = []
    if LIVE_MODE and live_book is not None:
        simple_runs.append((LTF_RUN_NAMES.get(LTF_MODE, str(LTF_MODE)), live_results, live_book, TREND_MODE))
    if DESIGN_TESTS and LIVE_MODE and live_book is not None and DESIGN_VARIANTS:
        _t0 = max(pd.Timestamp(d0), BACKTEST_START) if _starts else BACKTEST_START
        mid_t = _t0 + (pd.Timestamp(d1_) - _t0) / 2 if _starts else BACKTEST_START
        _base_name = {"choch": "روند فقط با چاک (= سربرگ خلاصه)",
                      "choch_tl": "روند با چاک و ترندلاین (= سربرگ خلاصه)",
                      "legacy": "روند به روش قدیمی ربات (= سربرگ خلاصه)"}.get(TREND_MODE, "مبنا (= سربرگ خلاصه)")
        design_rows.append(design_compare_row(_base_name, live_results, live_book,
                                              mid_t, "قوانین استراتژی بالای فایل (ورود +۱۰٪، بیس معتبر، روند ۴ساعته، فیبو و زون مخالف)"))
        n_var = len(DESIGN_VARIANTS)
        print(f"\n🧪 آزمایش: {n_var} اجرای کامل دیگر (هر کدام جدا) — مرز دو نیمه: {mid_t.date()}")
        for k, (name, (kw, desc)) in enumerate(DESIGN_VARIANTS.items(), start=1):
            print(f"   [{k}/{n_var}] {name}: {desc} ...", flush=True)
            if kw.get("ltf_mode") and all(fr[3] is None for fr in frames.values()):
                print("        ⚠️ دیتای ۱دقیقه داخل ZIPها نیست (فایل -1.csv) → این اجرا رد شد. "
                      "export_data را با تایم M1 اجرا کن.")
                continue
            call = dict(entry_off=DEFAULT_ENTRY_OFF, sl_off=DEFAULT_SL_OFF, rr=DEFAULT_RR,
                        manage_mode=DEFAULT_MANAGE, min_risk_atr=DEFAULT_MIN_RISK_ATR,
                        invalidate_on_breach=ZONE_INVALIDATE_ON_CLOSE)
            call.update(kw)
            try:
                res_v, book_v, _al = portfolio_live_replay(frames, spreads, **call)
            except Exception as e:
                print(f"   ⚠️ آزمایش {name} ناموفق بود: {e}")
                continue
            design_sheets.append((name, desc, design_symbol_table(res_v, book_v)))
            simple_runs.append((name.replace("_", " "), res_v, book_v, kw.get("trend_mode", TREND_MODE)))
            row = design_compare_row(name, res_v, book_v, mid_t, desc)
            design_rows.append(row)
            print(f"        بازده {row['بازده_کل_حساب٪']:.2f}٪ | افت {row['بیشترین_افت٪']:.2f}٪ | "
                  f"برد {row['درصد_برد']:.1f}٪ | معامله {row['تعداد_معامله']}")
        design_rows = design_verdicts(design_rows)

    for symbol, (h4, d1, w1, m15) in frames.items():
        if LIVE_MODE:
            res = live_results.get(symbol)
            if res is None:
                continue
            mdf, rdf, tdf, zdf, edf, zreason = res
        else:
            mdf, rdf, tdf, zdf, edf, zreason = backtest_one(symbol, h4,d1,w1, years, spreads.get(symbol, 0.0),
                                                            entry_off=DEFAULT_ENTRY_OFF, sl_off=DEFAULT_SL_OFF,
                                                            rr=DEFAULT_RR, m15=m15,
                                                            min_risk_atr=DEFAULT_MIN_RISK_ATR,
                                                            manage_mode=DEFAULT_MANAGE)

        # مقایسه‌ی فیلترهای کیفیت زون (Odds Enhancers)
        if COMPARE_QUALITY_MODES:
            for mode_name, kw in QUALITY_MODES.items():
                if not kw:
                    m_q = mdf.copy()
                else:
                    m_q = backtest_one(symbol, h4, d1, w1, years, spreads.get(symbol, 0.0),
                                       entry_off=DEFAULT_ENTRY_OFF, sl_off=DEFAULT_SL_OFF,
                                       rr=DEFAULT_RR, m15=m15, manage_mode=DEFAULT_MANAGE,
                                       **kw)[0].copy()
                m_q["کیفیت_زون"] = mode_name
                quality_mode_rows.append(m_q)

        # مقایسه‌ی فاصله‌ی حد ضرر (۲۵٪ در برابر ۵۰٪ پشت دیستال)
        if COMPARE_SL_MODES:
            for mode_name, so in SL_MODES.items():
                if abs(so - DEFAULT_SL_OFF) < 1e-12:
                    m_sl = mdf.copy()
                else:
                    m_sl = backtest_one(symbol, h4, d1, w1, years, spreads.get(symbol, 0.0),
                                        entry_off=DEFAULT_ENTRY_OFF, sl_off=so, rr=DEFAULT_RR,
                                        m15=m15, manage_mode=DEFAULT_MANAGE)[0].copy()
                m_sl["حالت_استاپ"] = mode_name
                sl_mode_rows.append(m_sl)

        # مقایسه‌ی حالت‌های مدیریت معامله (سیو سود / ریسک‌فری)
        if COMPARE_MANAGE_MODES:
            for mode_name, mm in MANAGE_MODES.items():
                if mm == DEFAULT_MANAGE:
                    m_mm = mdf.copy()
                else:
                    m_mm = backtest_one(symbol, h4, d1, w1, years, spreads.get(symbol, 0.0),
                                        entry_off=DEFAULT_ENTRY_OFF, rr=DEFAULT_RR, m15=m15,
                                        manage_mode=mm)[0].copy()
                m_mm["مدیریت"] = mode_name
                manage_mode_rows.append(m_mm)

        # اجرای RR های دیگر فقط برای مقایسه (گزارش‌های کامل با DEFAULT_RR است)
        if COMPARE_RR_MODES:
            for mode_name, rrv in RR_MODES.items():
                if abs(rrv - DEFAULT_RR) < 1e-12:
                    m_rr = mdf.copy()
                else:
                    m_rr = backtest_one(symbol, h4, d1, w1, years, spreads.get(symbol, 0.0),
                                        entry_off=DEFAULT_ENTRY_OFF, rr=rrv, m15=m15)[0].copy()
                m_rr["حالت_RR"] = mode_name
                rr_mode_rows.append(m_rr)

        # مقایسه‌ی آستانه‌های «لغو در صورت دور شدن قیمت»
        if COMPARE_DISTCANCEL_MODES:
            for mode_name, dcr in DISTCANCEL_MODES.items():
                if abs(dcr - DEFAULT_DIST_CANCEL_R) < 1e-12:
                    m_dc = mdf.copy()
                else:
                    m_dc = backtest_one(symbol, h4, d1, w1, years, spreads.get(symbol, 0.0),
                                        entry_off=DEFAULT_ENTRY_OFF, rr=DEFAULT_RR, m15=m15,
                                        dist_cancel_r=dcr)[0].copy()
                m_dc["قانون_لغو_دور"] = mode_name
                distcancel_mode_rows.append(m_dc)

        # مقایسه‌ی آستانه‌های فیلتر «حداقل اندازه‌ی زون»
        if COMPARE_MINRISK_MODES:
            for mode_name, mra in MINRISK_MODES.items():
                if abs(mra - DEFAULT_MIN_RISK_ATR) < 1e-12:
                    m_mr = mdf.copy()
                else:
                    m_mr = backtest_one(symbol, h4, d1, w1, years, spreads.get(symbol, 0.0),
                                        entry_off=DEFAULT_ENTRY_OFF, rr=DEFAULT_RR, m15=m15,
                                        min_risk_atr=mra)[0].copy()
                m_mr["حداقل_زون"] = mode_name
                minrisk_mode_rows.append(m_mr)

        # اجرای حالت‌های دیگر نقطه‌ی ورود فقط برای مقایسه (بقیه‌ی گزارش‌ها با حالت اصلی است)
        if COMPARE_ENTRY_MODES:
            for mode_name, eoff in ENTRY_MODES.items():
                if abs(eoff - DEFAULT_ENTRY_OFF) < 1e-12:
                    m_mode = mdf.copy()
                else:
                    m_mode = backtest_one(symbol, h4, d1, w1, years, spreads.get(symbol, 0.0),
                                          entry_off=eoff, m15=m15)[0].copy()
                m_mode["حالت_ورود"] = mode_name
                entry_mode_rows.append(m_mode)

        all_metrics.append(mdf)
        all_reasons.append(rdf)
        all_trades.append(tdf)
        all_zones.append(zdf)
        all_events.append(edf)
        all_zone_reasons.append(zreason)
        # (خروجی معاملات_*.csv غیرفعال شد: طبق درخواست فقط ۴ فایل خروجی)

    metrics_df=pd.concat(all_metrics, ignore_index=True)
    reasons_df=pd.concat(all_reasons, ignore_index=True)
    trades_df=pd.concat(all_trades, ignore_index=True) if all_trades else pd.DataFrame()
    zones_df=pd.concat(all_zones, ignore_index=True)
    events_df=pd.concat(all_events, ignore_index=True)
    zone_reasons_df=pd.concat(all_zone_reasons, ignore_index=True)

    # مدت واقعی بک‌تست: از شروع 2023 تا انتهای دیتای موجود
    if max_data_time is not None:
        end_t = max_data_time if BACKTEST_END is None else min(max_data_time, BACKTEST_END)
        years = max((end_t - BACKTEST_START).days / 365.25, 1.0 / 12.0)
    else:
        years = 1.0 / 12.0

    # --- Review change impact (compares with previous version if available) ---
    metrics_df, baseline_path = augment_metrics_with_change_review(metrics_df, os.getcwd(), years,
                                                                   book=live_book, trades=trades_df)

    
    # --- خروجی‌ها: فقط دو فایل در پوشه «خروجی» ---
    # 1) فایل خلاصه
    summary_path = os.path.join(outdir, "خلاصه_نتایج.xlsx")
    # 2) فایل جزئیات حرفه‌ای
    detailed_path = os.path.join(outdir, "جزئیات_حرفه‌ای.xlsx")

    try:

        # آماده‌سازی زمان‌ها
        if not trades_df.empty:
            for c in ["زمان_ورود", "زمان_خروج"]:
                if c in trades_df.columns:
                    trades_df[c] = pd.to_datetime(trades_df[c], errors="coerce")

        # --- جداول پایه ---
        # خلاصه‌ی نمادها (همان نتایج اعدادی)
        sym_metrics = metrics_df.copy()

        # خلاصه کلی (پورتفوی تقریب وزن‌مساوی روی نمادها)
        _m = sym_metrics[sym_metrics["نماد"] != "کل"].copy() if "کل" in sym_metrics.get("نماد", pd.Series()).astype(str).values else sym_metrics.copy()
        overview = {}
        overview["نسخه"] = version_name
        overview["years"] = round(float(years), 4)
        overview["datadir"] = datadir
        overview["ReserveCapitalPercent"] = 15
        overview["RiskPerTradePercent"] = 1
        overview["MaxOrders"] = 3
        overview["EntryOffsetPct"] = 10
        overview["StopOffsetPct"] = 25
        overview["RR"] = 3
        overview["SymbolsCount"] = int(len(_m))
        overview["TotalTrades"] = int(_m["تعداد"].fillna(0).sum()) if "تعداد" in _m.columns else (int(len(trades_df)) if not trades_df.empty else 0)
        overview["AvgWinRatePct"] = float(_m["درصد_برد"].mean()) if "درصد_برد" in _m.columns else np.nan
        overview["AvgProfitFactor"] = float(_m["فاکتور_سود"].mean()) if "فاکتور_سود" in _m.columns else np.nan
        overview["AvgNetReturnPct"] = float(_m["بازده_خالص٪"].mean()) if "بازده_خالص٪" in _m.columns else np.nan
        overview["MedianNetReturnPct"] = float(_m["بازده_خالص٪"].median()) if "بازده_خالص٪" in _m.columns else np.nan
        overview["AvgMaxDrawdownPct"] = float(_m["حداکثر_افت٪"].mean()) if "حداکثر_افت٪" in _m.columns else np.nan

        # بهترین/بدترین نماد بر اساس بازده
        if "بازده_خالص٪" in _m.columns and "نماد" in _m.columns and len(_m) > 0:
            best_row = _m.sort_values("بازده_خالص٪", ascending=False).iloc[0]
            worst_row = _m.sort_values("بازده_خالص٪", ascending=True).iloc[0]
            overview["BestSymbol"] = str(best_row["نماد"])
            overview["BestNetReturnPct"] = float(best_row["بازده_خالص٪"])
            overview["WorstSymbol"] = str(worst_row["نماد"])
            overview["WorstNetReturnPct"] = float(worst_row["بازده_خالص٪"])
        else:
            overview["BestSymbol"] = ""
            overview["BestNetReturnPct"] = np.nan
            overview["WorstSymbol"] = ""
            overview["WorstNetReturnPct"] = np.nan

        overview_df = pd.DataFrame([overview])

        # --- معاملات: تست 1/2، شمارش‌ها ---
        if trades_df.empty:
            test_counts = pd.DataFrame(columns=["تست", "تعداد"])
            trades_by_symbol = pd.DataFrame(columns=["نماد", "تعداد"])
            trades_by_year_symbol = pd.DataFrame(columns=["نماد", "سال", "تعداد"])
        else:
            test_counts = trades_df.groupby("تست").size().reset_index(name="تعداد").sort_values("تست")
            trades_by_symbol = trades_df.groupby("نماد").size().reset_index(name="تعداد").sort_values("تعداد", ascending=False)
            trades_df["سال"] = trades_df["زمان_خروج"].dt.year.fillna(trades_df["زمان_ورود"].dt.year)
            trades_by_year_symbol = trades_df.groupby(["نماد", "سال"]).size().reset_index(name="تعداد").sort_values(["نماد", "سال"])

        # --- زون‌ها: تعداد ساخته‌شده/تریدشده ---
        if zones_df.empty:
            zone_stats = pd.DataFrame(columns=["نماد", "TotalZonesBuilt", "UniqueZonesTraded"])
        else:
            built = zones_df.groupby("نماد").size().reset_index(name="TotalZonesBuilt")
            traded = (trades_df.groupby("نماد")["ZoneID"].nunique().reset_index(name="UniqueZonesTraded")
                      if (not trades_df.empty and "ZoneID" in trades_df.columns) else
                      pd.DataFrame({"نماد": built["نماد"], "UniqueZonesTraded": 0}))
            zone_stats = built.merge(traded, on="نماد", how="left").fillna(0).sort_values("TotalZonesBuilt", ascending=False)

        # --- بازده سالانه/ماهانه برای هر نماد (با بازسازی اکویتی همان فرمول کد) ---
        def _equity_series_for_symbol(sym_trades: pd.DataFrame, reserve=0.15, risk_per_trade=0.01, start_equity=100000.0):
            if sym_trades.empty:
                return pd.DataFrame(columns=["زمان", "اکویتی"])
            t = sym_trades.copy()
            # ترتیب بر اساس زمان خروج
            t = t.sort_values("زمان_خروج")
            eq = start_equity
            rows = []
            for _, r in t.iterrows():
                res_r = float(r.get("نتیجه_R", 0.0))
                usable = eq * (1.0 - reserve)
                risk_amt = usable * risk_per_trade
                eq = eq + risk_amt * res_r
                rows.append({"زمان": r["زمان_خروج"], "اکویتی": eq})
            return pd.DataFrame(rows)

        annual_rows=[]
        monthly_rows=[]
        avg_rows=[]
        if not trades_df.empty:
            for sym, g in trades_df.groupby("نماد"):
                es = _equity_series_for_symbol(g, reserve=0.15, risk_per_trade=0.01, start_equity=100000.0)
                if es.empty:
                    continue
                es = es.dropna(subset=["زمان"])
                if es.empty:
                    continue
                es = es.sort_values("زمان")
                es["سال"] = es["زمان"].dt.year
                es["ماه"] = es["زمان"].dt.to_period("M").astype(str)

                # سالانه
                for y, gy in es.groupby("سال"):
                    eq_end = float(gy["اکویتی"].iloc[-1])
                    # equity start = last equity before this year, or 100000 if first year
                    prev = es[es["زمان"].dt.year < y]
                    eq_start = float(prev["اکویتی"].iloc[-1]) if not prev.empty else 100000.0
                    ret = (eq_end - eq_start) / eq_start * 100.0 if eq_start != 0 else 0.0
                    annual_rows.append({"نماد": sym, "سال": int(y), "بازده_سالانه٪": round(ret, 2), "اکویتی_شروع": round(eq_start, 2), "اکویتی_پایان": round(eq_end, 2)})

                # ماهانه
                for mth, gm in es.groupby("ماه"):
                    eq_end = float(gm["اکویتی"].iloc[-1])
                    # equity start = last equity before this month, or 100000 if first month
                    prev = es[es["زمان"] < pd.to_datetime(mth + "-01")]
                    eq_start = float(prev["اکویتی"].iloc[-1]) if not prev.empty else 100000.0
                    ret = (eq_end - eq_start) / eq_start * 100.0 if eq_start != 0 else 0.0
                    monthly_rows.append({"نماد": sym, "ماه": mth, "بازده_ماهانه٪": round(ret, 2), "اکویتی_شروع": round(eq_start, 2), "اکویتی_پایان": round(eq_end, 2)})

        annual_df = pd.DataFrame(annual_rows).sort_values(["نماد","سال"]) if annual_rows else pd.DataFrame(columns=["نماد","سال","بازده_سالانه٪","اکویتی_شروع","اکویتی_پایان"])
        monthly_df = pd.DataFrame(monthly_rows).sort_values(["نماد","ماه"]) if monthly_rows else pd.DataFrame(columns=["نماد","ماه","بازده_ماهانه٪","اکویتی_شروع","اکویتی_پایان"])

        # میانگین‌ها (سالانه/ماهانه برای هر نماد)
        if not annual_df.empty:
            a = annual_df.groupby("نماد")["بازده_سالانه٪"].mean().reset_index(name="میانگین_بازده_سالانه٪")
        else:
            a = pd.DataFrame(columns=["نماد","میانگین_بازده_سالانه٪"])
        if not monthly_df.empty:
            m = monthly_df.groupby("نماد")["بازده_ماهانه٪"].mean().reset_index(name="میانگین_بازده_ماهانه٪")
        else:
            m = pd.DataFrame(columns=["نماد","میانگین_بازده_ماهانه٪"])
        avg_df = a.merge(m, on="نماد", how="outer").sort_values("نماد")

        # --- دلایل (از reasons_df) ---
        reasons_out = reasons_df.copy() if not reasons_df.empty else pd.DataFrame(columns=["نماد","دلیل","تعداد"])

        # --- تحلیل حرفه‌ای توزیع/زمان معاملات (فقط اگر فایل جزئیات خواسته شده) ---
        dist_sheets = distribution_sheets(trades_df) if WRITE_DETAILS else {}

        # --- فایل خلاصه (فقط شاخص‌های کلیدی درخواستی) ---
        summary_df = metrics_df.copy()
        if "درصد_برد" in summary_df.columns:
            summary_df["درصد_لاس"] = 100.0 - pd.to_numeric(summary_df["درصد_برد"], errors="coerce").fillna(0.0)
        else:
            summary_df["درصد_لاس"] = np.nan

        # فقط شاخص‌های کلیدی — خروجی تمیز و خوانا
        summary_cols = [
            "نماد", "تعداد", "درصد_برد", "فاکتور_سود", "میانگین_R", "بازده_خالص٪", "حداکثر_افت٪",
            "فاصله_استاپ_پیپ", "هزینه_هر_معامله_R", "اسپرد_پیپ"
        ]
        for c in summary_cols:
            if c not in summary_df.columns:
                summary_df[c] = np.nan
        summary_out = summary_df[summary_cols].copy()

        # --- شیت‌های مقایسه (نقطه‌ی ورود / RR) ---
        cmp_out = _aggregate_mode_rows(entry_mode_rows, "حالت_ورود") if (COMPARE_ENTRY_MODES and entry_mode_rows) else None
        rr_out = _aggregate_mode_rows(rr_mode_rows, "حالت_RR") if (COMPARE_RR_MODES and rr_mode_rows) else None
        mr_out = _aggregate_mode_rows(minrisk_mode_rows, "حداقل_زون") if (COMPARE_MINRISK_MODES and minrisk_mode_rows) else None
        dc_out = _aggregate_mode_rows(distcancel_mode_rows, "قانون_لغو_دور") if (COMPARE_DISTCANCEL_MODES and distcancel_mode_rows) else None
        mg_out = _aggregate_mode_rows(manage_mode_rows, "مدیریت") if (COMPARE_MANAGE_MODES and manage_mode_rows) else None
        sl_out = _aggregate_mode_rows(sl_mode_rows, "حالت_استاپ") if (COMPARE_SL_MODES and sl_mode_rows) else None
        q_out = _aggregate_mode_rows(quality_mode_rows, "کیفیت_زون") if (COMPARE_QUALITY_MODES and quality_mode_rows) else None

        # --- تحلیل سشن‌های معاملاتی ---
        sess_out = hour_out = sesssym_out = None
        if ANALYZE_SESSIONS:
            try:
                sess_out, hour_out, sesssym_out = session_analysis(trades_df)
            except Exception as e:
                print("⚠️ تحلیل سشن ناموفق بود:", str(e))

        # --- شبیه‌سازی حساب مشترک (پرتفوی) ---
        # --- تست پایداری نمادها (نیمه‌ی اول در برابر نیمه‌ی دوم) ---
        stab_out = None
        if STABILITY_TEST and WRITE_EXTRA_SHEETS:
            try:
                stab_out = stability_split_test(trades_df)
                if stab_out is not None:
                    bad = stab_out[stab_out["حکم"].str.contains("ضررده|فقط نیمه", na=False)]
                    print(f"🧪 تست پایداری: {len(stab_out)} نماد بررسی شد | "
                          f"{len(bad)} نماد لبه‌ی ناپایدار دارد (شیت «پایداری_نماد»)")
            except Exception as e:
                print("⚠️ تست پایداری ناموفق بود:", str(e))

        # --- تست حذف تک‌نماد (زمان‌بر) ---
        loo_out = None
        if LEAVE_ONE_OUT_TEST and LIVE_MODE:
            try:
                print(f"\n🧪 تست حذف تک‌نماد: {len(frames)+1} اجرای کامل — این چند ده دقیقه طول می‌کشد...")
                loo_out = leave_one_out_test(
                    frames, spreads, entry_off=DEFAULT_ENTRY_OFF, sl_off=DEFAULT_SL_OFF,
                    rr=DEFAULT_RR, manage_mode=DEFAULT_MANAGE, min_risk_atr=DEFAULT_MIN_RISK_ATR)
                print("   تمام شد (شیت «حذف_تک‌نماد»)")
            except Exception as e:
                print("⚠️ تست حذف تک‌نماد ناموفق بود:", str(e))

        port = None
        try:
            if LIVE_MODE and live_book is not None:
                # سقف‌ها همان موقع ساخته شدن معامله اعمال شده‌اند — دوباره فیلتر نمی‌کنیم
                port = live_book_report(live_book, trades_df, live_alloc)
            else:
                port = portfolio_replay(trades_df, symbols=(PORTFOLIO_SYMBOLS or None))
        except Exception as e:
            print("⚠️ شبیه‌سازی پرتفوی ناموفق بود:", str(e))

        # --- مقایسه‌ی وزن‌دهی ریسک بر اساس سشن ---
        sw_out = None
        if COMPARE_SESSION_WEIGHTS:
            try:
                sw_rows = []
                for label, weights in SESSION_WEIGHT_MODES.items():
                    pr = portfolio_replay(trades_df, symbols=(PORTFOLIO_SYMBOLS or None),
                                          session_weights=(weights or None))
                    if pr is None:
                        continue
                    s = pr["stats"].copy()
                    s.insert(0, "وزن‌دهی", label)
                    m = pr["monthly"]
                    s["بدترین_ماه٪"] = round(float(m["بازده٪"].min()), 2) if not m.empty else 0.0
                    s["ماه‌های_منفی"] = int((m["بازده٪"] < 0).sum()) if not m.empty else 0
                    sw_rows.append(s)
                if sw_rows:
                    sw_out = pd.concat(sw_rows, ignore_index=True)
            except Exception as e:
                print("⚠️ مقایسه‌ی وزن سشن ناموفق بود:", str(e))

        # --- مقایسه‌ی «سقف اجرا» (شبیه ربات لایو) روی همان حساب مشترک ---
        ec_out = None
        if COMPARE_EXECCAP_MODES:
            try:
                ec_rows = []
                for label, (mo, ps) in EXECCAP_MODES.items():
                    pr = portfolio_replay(trades_df, symbols=(PORTFOLIO_SYMBOLS or None),
                                          max_open=mo, per_symbol_max_open=ps)
                    if pr is None:
                        continue
                    s = pr["stats"].copy()
                    s.insert(0, "سقف_اجرا", label)
                    m = pr["monthly"]
                    s["بدترین_ماه٪"] = round(float(m["بازده٪"].min()), 2) if not m.empty else 0.0
                    s["ماه‌های_منفی"] = int((m["بازده٪"] < 0).sum()) if not m.empty else 0
                    ec_rows.append(s)
                if ec_rows:
                    ec_out = pd.concat(ec_rows, ignore_index=True)
            except Exception as e:
                print("⚠️ مقایسه‌ی سقف اجرا ناموفق بود:", str(e))

        # --- مقایسه‌ی محدودیت‌های ضرر (سپر ایمنی) روی همان حساب مشترک ---
        ll_out = None
        if COMPARE_LOSSLIMIT_MODES:
            try:
                ll_rows = []
                for label, (ld, lw) in LOSSLIMIT_MODES.items():
                    pr = portfolio_replay(trades_df, symbols=(PORTFOLIO_SYMBOLS or None),
                                          max_losses_day=ld, max_losses_week=lw)
                    if pr is None:
                        continue
                    s = pr["stats"].copy()
                    s.insert(0, "محدودیت", label)
                    # بدترین ماه هر حالت هم برای قضاوت مهم است
                    m = pr["monthly"]
                    s["بدترین_ماه٪"] = round(float(m["بازده٪"].min()), 2) if not m.empty else 0.0
                    s["ماه‌های_منفی"] = int((m["بازده٪"] < 0).sum()) if not m.empty else 0
                    ll_rows.append(s)
                if ll_rows:
                    ll_out = pd.concat(ll_rows, ignore_index=True)
            except Exception as e:
                print("⚠️ مقایسه‌ی محدودیت ضرر ناموفق بود:", str(e))

        if LIVE_MODE and live_book is not None:
            # در حالت «عین لایو» همه‌ی نمادها روی یک حساب معامله می‌کنند، پس عدد هر
            # نماد «بازده مستقل» نیست؛ سهم آن نماد از بازده حساب است (جمعشان = بازده کل).
            # اسم ستون‌ها را صادقانه می‌کنیم تا کسی اشتباه نخواند.
            summary_out = summary_out.rename(columns={
                "بازده_خالص٪": "سهم_از_بازده_حساب٪",
                "حداکثر_افت٪": "افت_سهم_این_نماد٪",
            })

        _reviews = None
        with pd.ExcelWriter(summary_path, engine="openpyxl") as sw:
            if SIMPLE_EXCEL and simple_runs:
                _reviews = write_simple_excel(sw, simple_runs, frames)
            else:
                summary_out.to_excel(sw, sheet_name="خلاصه", index=False)
            # آزمایش‌های طراحی: یک سربرگ مقایسه + یک سربرگ برای هر آزمایش
            if design_rows and not SIMPLE_EXCEL:
                pd.DataFrame(design_rows).to_excel(sw, sheet_name="مقایسه_طراحی‌ها", index=False)
                for _nm, _desc, _tbl in design_sheets:
                    _sh = str(_nm)[:31]
                    pd.DataFrame([{"آزمایش": _nm, "توضیح": _desc}]).to_excel(sw, sheet_name=_sh, index=False)
                    _tbl.to_excel(sw, sheet_name=_sh, index=False, startrow=3)
            # سربرگ‌های اضافه (پایداری، پرتفوی، مقایسه‌های قدیمی، ...) فقط اگر خواسته شود
            if WRITE_EXTRA_SHEETS:
                pd.DataFrame([
                    {"تنظیم": "ENTRY_BAR_MODE (کندل ورود)", "مقدار": ENTRY_BAR_MODE},
                    {"تنظیم": "NO_SAME_BAR_TOUCH_FILL (سفارش از کندل بعد از لمس)", "مقدار": NO_SAME_BAR_TOUCH_FILL},
                    {"تنظیم": "MODEL_BID_ASK (اسپرد در پر شدن و خروج)", "مقدار": MODEL_BID_ASK},
                    {"تنظیم": "دیتای تایم پایین‌تر", "مقدار": "ندارد" if (not USE_M15 or no_ltf) else "دارد"},
                ]).to_excel(sw, sheet_name="تنظیمات_واقع_بینی", index=False)
                if stab_out is not None:
                    stab_out.to_excel(sw, sheet_name="پایداری_نماد", index=False)
                if loo_out is not None:
                    loo_out.to_excel(sw, sheet_name="حذف_تک‌نماد", index=False)
                if cmp_out is not None:
                    cmp_out.to_excel(sw, sheet_name="مقایسه_نقطه_ورود", index=False)
                if rr_out is not None:
                    rr_out.to_excel(sw, sheet_name="مقایسه_RR", index=False)
                if mr_out is not None:
                    mr_out.to_excel(sw, sheet_name="مقایسه_حداقل_زون", index=False)
                if dc_out is not None:
                    dc_out.to_excel(sw, sheet_name="مقایسه_لغو_دور", index=False)
                if mg_out is not None:
                    mg_out.to_excel(sw, sheet_name="مقایسه_مدیریت", index=False)
                if sl_out is not None:
                    sl_out.to_excel(sw, sheet_name="مقایسه_استاپ", index=False)
                if q_out is not None:
                    q_out.to_excel(sw, sheet_name="مقایسه_کیفیت_زون", index=False)
                if sw_out is not None:
                    sw_out.to_excel(sw, sheet_name="مقایسه_وزن_سشن", index=False)
                if sess_out is not None:
                    sess_out.to_excel(sw, sheet_name="تحلیل_سشن", index=False)
                    hour_out.to_excel(sw, sheet_name="تحلیل_ساعت_خام", index=False)
                    sesssym_out.to_excel(sw, sheet_name="سشن_هر_نماد", index=False)
                    if SESSION_STABILITY:
                        stab = session_stability(trades_df)
                        if stab is not None:
                            stab.to_excel(sw, sheet_name="پایداری_سشن", index=False)
                if port is not None:
                    port["stats"].to_excel(sw, sheet_name="پرتفوی", index=False)
                    if WRITE_PORTFOLIO_DETAIL:
                        port["yearly"].to_excel(sw, sheet_name="پرتفوی_سالانه", index=False)
                        port["monthly"].to_excel(sw, sheet_name="پرتفوی_ماهانه", index=False)
                if ec_out is not None:
                    ec_out.to_excel(sw, sheet_name="مقایسه_سقف_اجرا", index=False)
                if ll_out is not None:
                    ll_out.to_excel(sw, sheet_name="مقایسه_محدودیت_ضرر", index=False)
            # راست‌به‌چپ و عرض ستون‌ها برای خوانایی
            for _ws in sw.book.worksheets:
                _ws.sheet_view.rightToLeft = True
                for _col in _ws.columns:
                    _w = max((len(str(_c.value)) for _c in _col[:300] if _c.value is not None), default=8)
                    _ws.column_dimensions[_col[0].column_letter].width = min(max(10, _w * 1.1), 70)

        # نمودار هر معامله (بعد از ذخیره‌ی اکسل، تا اگر مشکلی پیش آمد اکسل از دست نرود)
        if SIMPLE_EXCEL and TRADE_CHARTS and simple_runs and _reviews:
            chart_dir = os.path.join(outdir, "نمودار_معاملات")
            print(f"\n🖼️ نمودار معاملات در «{chart_dir}» ...", flush=True)
            for _k, (_nm, _tb, _raw) in enumerate(_reviews, start=1):
                try:
                    _n = draw_trade_charts(chart_dir, _k, _nm, _raw, frames)
                    print(f"   {_nm}: {_n} نمودار")
                except Exception as e:
                    print(f"   ⚠️ نمودار «{_nm}» ساخته نشد: {e}")

        # --- خروجی نهایی (جزئیات کامل) — فقط اگر WRITE_DETAILS روشن باشد ---
        if WRITE_DETAILS:
            with pd.ExcelWriter(detailed_path, engine="openpyxl") as writer:
                overview_df.to_excel(writer, sheet_name="خلاصه_کلی", index=False)
                sym_metrics.to_excel(writer, sheet_name="نتایج_اعدادی", index=False)
                trades_by_symbol.to_excel(writer, sheet_name="معاملات_هر_نماد", index=False)
                trades_by_year_symbol.to_excel(writer, sheet_name="معاملات_سال_نماد", index=False)
                test_counts.to_excel(writer, sheet_name="تست1_تست2", index=False)
                zone_stats.to_excel(writer, sheet_name="زون‌ها", index=False)
                annual_df.to_excel(writer, sheet_name="بازده_سالانه", index=False)
                monthly_df.to_excel(writer, sheet_name="بازده_ماهانه", index=False)
                avg_df.to_excel(writer, sheet_name="میانگین_بازده", index=False)
                reasons_out.to_excel(writer, sheet_name="دلایل", index=False)
                for sheet_name, ddf in dist_sheets.items():
                    safe_name = ("تحلیل_" + str(sheet_name))[:31]
                    ddf.to_excel(writer, sheet_name=safe_name, index=False)
            print("جزئیات_حرفه‌ای.xlsx ساخته شد ✅")
    except Exception as e:
        import traceback
        print("⚠️ ساخت فایل خروجی ناموفق بود:", str(e))
        traceback.print_exc()

    print("تمام شد ✅")
    print("خلاصه_نتایج.xlsx ساخته شد ✅ |", summary_path)
    if WRITE_DETAILS:
        print("جزئیات_حرفه‌ای.xlsx ساخته شد ✅ |", detailed_path)
    print("مسیر خروجی:", outdir)

if __name__ == "__main__":
    main()