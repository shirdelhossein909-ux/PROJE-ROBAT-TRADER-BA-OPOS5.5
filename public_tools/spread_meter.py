# -*- coding: utf-8 -*-
"""اندازه‌گیری اسپرد واقعی هر نماد از متاتریدر ۵

بخشی از سیستم معامله‌گری خودکار حسین شیردل (ساخته‌شده با هوش مصنوعی).

اجرا:  python spread_meter.py      (متاتریدر ۵ باز و لاگین باشد)
پیش‌نیاز: pip install MetaTrader5 numpy

اسپرد (Ask − Bid) همه‌ی تیک‌های چند روز اخیر خوانده می‌شود و میانگین و «میانه»اش در spreads.csv ذخیره
می‌شود. بک‌تست باید از میانه استفاده کند: پرش‌های لحظه‌ای اسپرد (رول‌اوور نیمه‌شب، باز شدن بازار)
میانگینِ نمادهای کم‌معامله را چند برابر اسپرد معمول نشان می‌دهد. روزبه‌روز خوانده می‌شود تا حافظه پر نشود.
اگر تیک نیامد، از ستون اسپرد کندل‌های ۱۵دقیقه و در آخر از اسپرد همین لحظه استفاده می‌شود.
"""

import os
import sys
import datetime as dt

# ================== تنظیمات ==================
SYMBOLS = ["XAUUSD", "EURUSD", "GBPJPY"]
SPREAD_DAYS = 5                # چند روز اخیر
OUT_DIR = os.path.join(os.path.expanduser("~"), "Desktop", "history_data")
TERMINAL_PATH = ""             # مسیر terminal64.exe — فقط اگر چند متاتریدر نصب است
SPREADS_NAME = "spreads.csv"
# =============================================

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
    import MetaTrader5 as mt5
except ImportError:
    _fail("پکیج MetaTrader5 نصب نیست. در CMD بزن:  pip install MetaTrader5")


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


def main():
    """اسپرد همه‌ی نمادها → spreads.csv"""
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
    paths = write_spreads(rows, [OUT_DIR])
    print("\nذخیره شد:")
    for p_ in paths:
        print("   " + p_)
    return 0


if __name__ == "__main__":
    try:
        code = main()
    except KeyboardInterrupt:
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
