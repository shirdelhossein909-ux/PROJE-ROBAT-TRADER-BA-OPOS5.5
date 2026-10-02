# سایت رزومه (دوزبانه)

- `src.html` متن و طراحی صفحه است.
- `build.py` کد ابزارهای پوشه‌ی `public_tools` و داده‌ی نمودار (`data/live_vs_backtest.json`) را داخل صفحه می‌گذارد و `index.html` را می‌سازد.
- `index.html` همان صفحه‌ای است که منتشر می‌شود.

بعد از هر تغییر در `src.html` یا ابزارها: `python site/build.py`
