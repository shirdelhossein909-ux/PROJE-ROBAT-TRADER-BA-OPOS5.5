# -*- coding: utf-8 -*-
"""اجرای کامل تحلیل «لایو در برابر بکتست عین لایو» — به ترتیب:

  1) parse_live.py         خواندن ReportHistory متاتریدر
  2) live_trades.py        ساختن جدول معاملات واقعی (R، ریسک دلاری، ...)
  3) precompute_states.py  مغز ربات در هر کندل H4 با همان پنجره‌ی دیتای لایو (~۵ دقیقه روی ۴ هسته)
  4) emulate.py            شبیه‌سازی «عین لایو» در چند سناریو
  5) compare.py            مقایسه‌ی تصمیم‌به‌تصمیم و معامله‌به‌معامله
  6) classic.py            بکتستر کلاسیک run_backtest.py در همان بازه
  7) classic_full.py       کل ۲ سال: بکتستر اصلی در برابر «کندل ورود واقع‌بینانه»
  8) build_report.py       ساختن گزارش HTML و فایل اکسل در پوشه‌ی بالایی

اجرا:  python run_all.py      (از داخل همین پوشه)
"""
import os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
STEPS = ["parse_live.py", "live_trades.py", "precompute_states.py", "emulate.py",
         "compare.py", "classic.py", "classic_full.py", "build_report.py"]

if __name__ == "__main__":
    for s in STEPS:
        print(f"\n===== {s} =====", flush=True)
        r = subprocess.run([sys.executable, "-W", "ignore", os.path.join(HERE, s)], cwd=HERE)
        if r.returncode != 0:
            sys.exit(f"مرحله‌ی {s} با خطا تمام شد.")
