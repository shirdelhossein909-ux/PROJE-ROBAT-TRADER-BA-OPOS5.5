# -*- coding: utf-8 -*-
"""نسخه‌ی آزمایشی run_backtest.py با گزینه‌ی PESS_ENTRY_BAR می‌سازد (خود فایل اصلی دست نمی‌خورد).

PESS_ENTRY_BAR = False  → رفتار فعلی بکتستر (سقف/کفِ کندل ورود بعد از پر شدن فرض می‌شود)
PESS_ENTRY_BAR = "mid"  → مسیر کندل از رنگش حدس زده می‌شود (صعودی O→L→H→C ، نزولی O→H→L→C)
PESS_ENTRY_BAR = True   → بدبینانه: در کندل ورود فقط کلوز برای سیو سود/تارگت قابل اتکاست
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))

OLD = '''                # بدون M15: بدبینانه (اگر هر دو لمس شد، استاپ) + اعمال مدیریت سیوسود/ریسک‌فری
                exited, exit_price, reason = process_pos_candle(pos, h, l, t)'''
NEW = '''                # بدون M15: بدبینانه (اگر هر دو لمس شد، استاپ) + اعمال مدیریت سیوسود/ریسک‌فری
                if PESS_ENTRY_BAR == "mid":
                    # میانه: مسیر کندل از رنگش حدس زده می‌شود (صعودی: O→L→H→C ، نزولی: O→H→L→C)
                    if direction == "BUY":
                        fav = h if c >= o else max(c, p["entry"])
                        exited, exit_price, reason = process_pos_candle(pos, fav, l, t)
                    else:
                        fav = l if c <= o else min(c, p["entry"])
                        exited, exit_price, reason = process_pos_candle(pos, h, fav, t)
                elif PESS_ENTRY_BAR:
                    # کندل ورود: سقف/کف مطلوب ممکن است قبل از پر شدن بوده باشد؛ فقط کلوز قابل اتکاست
                    if direction == "BUY":
                        exited, exit_price, reason = process_pos_candle(pos, max(c, p["entry"]), l, t)
                    else:
                        exited, exit_price, reason = process_pos_candle(pos, h, min(c, p["entry"]), t)
                else:
                    exited, exit_price, reason = process_pos_candle(pos, h, l, t)'''


def build():
    s = open(os.path.join(REPO, "run_backtest.py"), encoding="utf-8").read()
    if OLD not in s:
        raise RuntimeError("run_backtest.py عوض شده؛ بخش کندل ورود پیدا نشد")
    s = s.replace(OLD, NEW).replace("USE_M15 = False\n", "USE_M15 = False\nPESS_ENTRY_BAR = False\n", 1)
    with open(os.path.join(HERE, "rb_pess.py"), "w", encoding="utf-8") as f:
        f.write(s)


if __name__ == "__main__":
    build()
