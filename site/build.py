# -*- coding: utf-8 -*-
"""ساخت index.html از src.html: داده‌ی نمودار و کد ابزارهای عمومی داخل صفحه گذاشته می‌شود.
اجرا:  python site/build.py"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(HERE, "..", "public_tools")

META = [
    ("backtest_engine.py", "بکتستر با قفل ضد دیدن آینده", "Backtester with a look-ahead lock",
     "شبیه‌سازی روی کندل‌های یک‌دقیقه با قیمت خرید و فروش جدا، اسپرد، سواپ و سیو سود در 2R. قبل از اجرا، استراتژی را روی ۲۵ برش از داده امتحان می‌کند؛ اگر آینده را ببیند، بکتست اجرا نمی‌شود. یک استراتژی نمونه‌ی ساده دارد که می‌شود جایش استراتژی خودتان را گذاشت.",
     "Simulates on 1-minute candles with separate bid and ask, spread, swap and a partial close at 2R. Before running, it re-tests the strategy on 25 cuts of the data; if the strategy sees the future, the backtest refuses to run. Ships with a simple sample strategy you can replace with your own.",
     "آزموده با ۱۴ حالت دست‌ساز با جواب معلوم، ۳ استراتژی متقلب که همه گیر افتادند، و مقایسه‌ی ۶۲۴ معامله با یک شبیه‌ساز کندل‌به‌کندل (همه یکسان).",
     "Tested with 14 hand-built cases with known answers, 3 cheating strategies (all caught), and 624 trades matched one by one against a candle-by-candle simulator."),
    ("watchdog.py", "نگهبان ربات", "Robot watchdog",
     "اگر ربات بسته شد یا گیر کرد، دوباره اجرایش می‌کند، دلیلش را از رویدادهای ویندوز پیدا می‌کند و در پیام‌رسان بله گزارش می‌دهد. برای هر رباتی که فایل ضربان بنویسد کار می‌کند.",
     "Restarts the robot if it closes or hangs, finds the cause in the Windows event log, and reports it on the Bale messenger. Works with any robot that writes a heartbeat file.",
     "آزموده با یک ربات ساختگی در سه حالت: ربات خاموش، ربات گیرکرده و خاموشی عمدی.",
     "Tested against a fake robot in three scenarios: robot down, robot hung, and an intentional stop."),
    ("history_downloader.py", "دانلودر تاریخچه", "History downloader",
     "کندل‌های ۱دقیقه، ۱۵دقیقه و ۴ساعته را سال‌به‌سال و از جدید به قدیم از متاتریدر ۵ می‌گیرد، سال‌های کامل را نگه می‌دارد و برای هر نماد یک فایل فشرده‌ی آماده‌ی بکتست می‌سازد.",
     "Downloads 1-minute, 15-minute and 4-hour candles from MetaTrader 5 year by year, newest first, keeps finished years, and builds one backtest-ready archive per symbol.",
     "آزموده با یک متاتریدر ساختگی: خروجی مرتب و بدون کندل تکراری.",
     "Tested against a fake MetaTrader: sorted output with no duplicate candles."),
    ("spread_meter.py", "اسپردسنج", "Spread meter",
     "اسپرد واقعی بروکر را از تیک‌های متاتریدر اندازه می‌گیرد و میانه و میانگین را در یک فایل می‌نویسد تا بکتستر از آن استفاده کند.",
     "Measures the broker's real spread from MetaTrader ticks and writes the median and mean to a file the backtester reads.",
     "آزموده با تیک‌های ساختگی: میانه‌ی ۳٫۰۰ پیپ، همان عددی که انتظار داشتیم.",
     "Tested with synthetic ticks: a median of 3.00 pips, exactly as expected."),
]


def main():
    src = open(os.path.join(HERE, "src.html"), encoding="utf-8").read()
    series = open(os.path.join(HERE, "data", "live_vs_backtest.json"), encoding="utf-8").read().strip()
    codes = []
    for fn, nfa, nen, dfa, den, tfa, ten in META:
        code = open(os.path.join(TOOLS, fn), encoding="utf-8").read()
        codes.append({"file": fn, "name_fa": nfa, "name_en": nen, "desc_fa": dfa, "desc_en": den,
                      "test_fa": tfa, "test_en": ten, "lines": code.count("\n") + 1, "code": code})
    blob = json.dumps(codes, ensure_ascii=False).replace("</", "<\\/")
    out = src.replace("/*@@SERIES@@*/", series.replace("</", "<\\/")).replace("/*@@CODES@@*/", blob)
    assert "@@" not in out
    with open(os.path.join(HERE, "index.html"), "w", encoding="utf-8") as f:
        f.write(out)
    print(f"index.html: {len(out.encode('utf-8')) / 1024:.0f} KB")


if __name__ == "__main__":
    main()
