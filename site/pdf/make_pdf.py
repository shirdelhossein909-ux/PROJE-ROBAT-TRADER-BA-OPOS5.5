# -*- coding: utf-8 -*-
"""رزومه‌ی پی‌دی‌اف (فارسی و انگلیسی) از روی HTML با مرورگر کرومیوم.
اجرا:  python site/pdf/make_pdf.py
خروجی: site/pdf/رزومه_حسین_شیردل.pdf و site/pdf/Hossein_Shirdel_Resume.pdf"""
import json
import os
import random
import re

import qrcode
import qrcode.image.svg

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = "https://claude.ai/artifact/Fxk1vwBMx9CHXirQA5yZ9Q"
SITE_SHORT = "claude.ai/artifact/Fxk1vwBMx9CHXirQA5yZ9Q"
PHONE = "09928436013"
EMAIL = "shirdelhossein909@gmail.com"
FA_DIG = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def qr_svg(url):
    img = qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage, box_size=10, border=1)
    s = img.to_string(encoding="unicode")
    s = re.sub(r"<\?xml[^>]*>", "", s)
    s = re.sub(r'width="[^"]*mm" height="[^"]*mm"', 'width="100%" height="100%"', s)
    return s.replace('fill="#000000"', 'fill="#0c1120"')


# ---------------- small charts (inline SVG) ----------------
def candle_strip(lang):
    """مسیر در یک نگاه: کندل‌ها با برچسب مرحله‌ها (نمایشی)"""
    rnd = random.Random(1403)
    steps = [(8, 1, "نوروز ۱۴۰۳: شروع", "Mar 2024: start"),
             (22, -1, "خودکنترلی", "Self-control"),
             (34, 1, "جرقه‌ی هوش مصنوعی", "The AI spark"),
             (50, -1, "اینترنت ملی", "Internet cut"),
             (64, -1, "بکتست فریبنده", "Misleading backtest"),
             (78, 1, "بازسازی", "Rebuild")]
    mk = {i: k for i, k, _, _ in steps}
    n, price, C = 84, 100.0, []
    for i in range(n):
        o = price
        if i in mk:
            c = o + (5.0 if mk[i] > 0 else -6.5)
        elif i - 1 in mk and mk[i - 1] < 0:
            c = o - 1.2 + rnd.gauss(0, .5)
        else:
            c = o + .55 + rnd.gauss(0, 1.1)
        h = max(o, c) + abs(rnd.gauss(0, .8)) + .2
        l = min(o, c) - abs(rnd.gauss(0, .8)) - .2
        C.append((o, h, l, c))
        price = c
    lo = min(x[2] for x in C) - 2
    hi = max(x[1] for x in C) + 2
    W, H, T, B = 760, 150, 8, 42
    ph = H - T - B
    x = lambda i: 10 + (i + .5) * (W - 20) / n
    y = lambda v: T + (hi - v) / (hi - lo) * ph
    out = [f'<svg viewBox="0 0 {W} {H}" width="100%" xmlns="http://www.w3.org/2000/svg" direction="ltr">']
    ema, a = [], 2 / 11
    for i, (o, h, l, c) in enumerate(C):
        ema.append(c if not i else ema[-1] + a * (c - ema[-1]))
        col = "#1f8f84" if c >= o else "#d64541"
        out.append(f'<line x1="{x(i):.1f}" x2="{x(i):.1f}" y1="{y(h):.1f}" y2="{y(l):.1f}" stroke="{col}" stroke-width="1"/>')
        top, bh = y(max(o, c)), max(1.4, abs(y(o) - y(c)))
        out.append(f'<rect x="{x(i) - 2.6:.1f}" y="{top:.1f}" width="5.2" height="{bh:.1f}" fill="{col}"/>')
    pts = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(ema))
    out.append(f'<polyline points="{pts}" fill="none" stroke="#b8862b" stroke-width="2" stroke-linejoin="round"/>')
    for i, k, fa, en in steps:
        col = "#1f8f84" if k > 0 else "#d64541"
        out.append(f'<line x1="{x(i):.1f}" x2="{x(i):.1f}" y1="{y(C[i][2]) + 4:.1f}" y2="{H - B + 12}" stroke="#c9ced8" stroke-dasharray="2 2"/>')
        out.append(f'<circle cx="{x(i):.1f}" cy="{H - B + 16}" r="3.4" fill="{col}"/>')
        txt = fa if lang == "fa" else en
        out.append(f'<text x="{x(i):.1f}" y="{H - B + 34}" text-anchor="middle" class="sl">{txt}</text>')
    out.append("</svg>")
    return "".join(out)


def compare_chart(lang):
    """شش هفته، سه روایت (داده‌ی واقعی)"""
    data = json.load(open(os.path.join(HERE, "..", "data", "live_vs_backtest.json"), encoding="utf-8"))
    import datetime as dt
    t0, t1 = dt.datetime(2026, 8, 17), dt.datetime(2026, 9, 29)
    W, H, L, R, T, B = 700, 230, 44, 120, 10, 26
    pw, ph, y0, y1 = W - L - R, H - T - B, -5, 6
    X = lambda t: L + (t - t0).total_seconds() / (t1 - t0).total_seconds() * pw
    Y = lambda v: T + (y1 - v) / (y1 - y0) * ph

    def pct(v):
        s = ("+" if v > 0 else "−" if v < 0 else "") + f"{abs(v):.1f}%"
        return s.replace(".", "٫").replace("%", "٪").translate(FA_DIG) if lang == "fa" else s
    out = [f'<svg viewBox="0 0 {W} {H}" width="100%" xmlns="http://www.w3.org/2000/svg" direction="ltr">']
    for g in range(y0, y1 + 1, 2):
        out.append(f'<line x1="{L}" x2="{L + pw}" y1="{Y(g):.1f}" y2="{Y(g):.1f}" stroke="{"#8a93a6" if g == 0 else "#e3e6ec"}" stroke-width="1"/>')
        out.append(f'<text x="{L - 6}" y="{Y(g) + 4:.1f}" text-anchor="end" class="ax"><tspan direction="ltr" unicode-bidi="embed">{pct(g)}</tspan></text>')
    labels_fa = ["۲۶ مرداد", "۹ شهریور", "۲۳ شهریور", "۶ مهر"]
    labels_en = ["Aug 17", "Aug 31", "Sep 14", "Sep 28"]
    for k, t in enumerate([t0 + dt.timedelta(days=14 * j) for j in range(4)]):
        out.append(f'<text x="{X(t):.1f}" y="{H - 6}" text-anchor="middle" class="ax">{(labels_fa if lang == "fa" else labels_en)[k]}</text>')
    defs = [("old", "#eb6834", "6 4", 2, "بکتست با روش قدیم", "Backtest, old method"),
            ("real", "#1baf7a", "", 2, "بکتست واقع‌بینانه", "Realistic backtest"),
            ("live", "#2a78d6", "", 2.6, "حساب زنده", "Live account")]
    ends = []
    for key, col, dash, w, fa, en in defs:
        pts = [(t0, 0.0)] + [(dt.datetime.strptime(a, "%Y-%m-%d %H:%M"), b) for a, b in data[key]]
        d = f"M{X(pts[0][0]):.1f} {Y(0):.1f}"
        for t, v in pts[1:]:
            d += f" H{X(t):.1f} V{Y(v):.1f}"
        d += f" H{X(t1):.1f}"
        out.append(f'<path d="{d}" fill="none" stroke="#ffffff" stroke-width="{w + 3}"/>')
        out.append(f'<path d="{d}" fill="none" stroke="{col}" stroke-width="{w}" stroke-dasharray="{dash}" stroke-linejoin="round"/>')
        out.append(f'<circle cx="{X(t1):.1f}" cy="{Y(pts[-1][1]):.1f}" r="3.5" fill="{col}"/>')
        ends.append([Y(pts[-1][1]), pts[-1][1], fa if lang == "fa" else en, col])
    ends.sort()
    for i in range(1, len(ends)):
        if ends[i][0] - ends[i - 1][0] < 27:
            ends[i][0] = ends[i - 1][0] + 27
    for yy, v, name, col in ends:
        out.append(f'<text x="{X(t1) + 8:.1f}" y="{yy + 3:.1f}" class="ev">{pct(v)}</text>')
        out.append(f'<text x="{X(t1) + 8:.1f}" y="{yy + 16:.1f}" class="en2" fill="{col}">{name}</text>')
    out.append("</svg>")
    return "".join(out)


# ---------------- text ----------------
T = {
"fa": dict(
    dir="rtl", lang="fa",
    name="حسین شیردل",
    role="سازنده‌ی سیستم‌های واقعی با هوش مصنوعی · معامله‌گری خودکار",
    contact=[("تلفن", PHONE.translate(FA_DIG)), ("ایمیل", EMAIL), ("شهر", "همدان")],
    qr_cap="سایت کامل: همه‌ی لاگ‌ها، نمودارها و کدها",
    summary="حدود یک سال است که با مدل‌های هوش مصنوعی روز دنیا، مثل کلود و جی‌پی‌تی، یک <b>سیستم معامله‌گری خودکار پنج‌بخشی</b> برای متاتریدر ۵ طراحی می‌کنم و می‌سازم: از دانلود داده و اندازه‌گیری هزینه‌ها تا بکتست، ربات معامله‌گر و نگهبانی که شبانه‌روز مراقب ربات است. وقتی بکتست ۸۲۵٪ سود نشان داد و حساب زنده ضرر کرد، به جای توجیه، معامله‌به‌معامله مقایسه کردم، <b>خطای بکتست را خودم پیدا کردم</b> و سیستم را از نو ساختم.",
    facts=[("۵", "بخش، یک سیستم"), ("۶٬۵۰۰+", "خط کد پایتون"), ("۳ ماه", "اجرای زنده روی حساب دمو"), ("۶ سال", "داده‌ی یک‌دقیقه‌ای")],
    sys_h="پروژه: سیستم معامله‌گری خودکار",
    parts=[("نگهبان", "هر ۶۰ ثانیه ضربان ربات را چک می‌کند؛ اگر ربات بسته شد یا گیر کرد، دوباره اجرایش می‌کند، دلیل را از رویدادهای ویندوز پیدا می‌کند (آپدیت، خاموشی ناگهانی، خروج کاربر، کرش) و در پیام‌رسان بله گزارش می‌دهد.", True),
           ("ربات معامله‌گر", "استراتژی را روی متاتریدر ۵ اجرا می‌کند و هر کار را با دلیل دقیقش به بله می‌فرستد. مغزش با بکتستر یکی است.", False),
           ("بکتستر", "شبیه‌سازی روی کندل‌های یک‌دقیقه با قیمت خرید و فروش جدا، اسپرد واقعی و سواپ؛ گزارش اکسل و قیف دلیل‌ها.", False),
           ("دانلودر تاریخچه", "داده‌ی ۶ سال را سال‌به‌سال از متاتریدر می‌گیرد و اگر نیمه‌کاره بماند ادامه می‌دهد.", False),
           ("اسپردسنج", "اسپرد واقعی بروکر را از هزاران تیک اندازه می‌گیرد (میانه، نه میانگین).", False)],
    journey_h="مسیر در یک نگاه",
    journey_note="نمودار نمایشی: هر کندل یک قدم از مسیر است؛ سبز پیشرفت، قرمز شکست.",
    story=[("نوروز ۱۴۰۳", "ورود به بازار و یک سال تمرین روزانه؛ یک سال دانشگاه رفتم و بعد کنار گذاشتم تا با تمام وقت روی این کار تمرکز کنم."),
           ("کشف", "مشکل اصلی معامله‌گرها استراتژی نیست، خودکنترلی است. از آنتون کریل شنیدم آینده‌ی معامله‌گری با هوش مصنوعی است و تصمیم گرفتم این دو را ترکیب کنم."),
           ("یک سال اخیر", "ساخت سیستم با هوش مصنوعی، سه ماه اجرای زنده، پیدا کردن خطای بکتست و بازسازی کامل.")],
    ch_h="بزرگ‌ترین چالش: بکتستی که سه ماه ما را فریب داد",
    ch_p1="یکی از بزرگ‌ترین خطرها در ساختن ربات معامله‌گر، <b>بکتست غیرواقعی</b> است. بکتست قدیمی ما روی ۶ سال داده ۸۲۵٪ سود نشان می‌داد. ربات سه ماه در بازار زنده کار کرد، اما نتیجه اصلاً شبیه بکتست نبود و مجبور شدیم ربات را از نو برنامه‌ریزی کنیم.",
    ch_p2="مقایسه‌ی معامله‌به‌معامله نشان داد مغز ربات درست کار می‌کرد و خطا در بکتستر بود: وقتی سفارشی وسط یک کندل ۴ساعته پر می‌شد، بکتستر فرض می‌کرد سقف و کف کندل <b>بعد از</b> ورود رخ داده و سودی را ثبت می‌کرد که در واقع <b>قبل از</b> ورود اتفاق افتاده بود. یعنی بکتست از آینده خبر داشت.",
    chart_h="شش هفته، سه روایت از همان معامله‌ها",
    chart_sub="بازده تجمعی حساب ۱۰۰٬۰۰۰ دلاری، ۲۶ مرداد تا ۶ مهر ۱۴۰۵ (داده‌ی واقعی)",
    proofs=[('<bdi dir="ltr"><s>+۷۷٫۶٪</s></bdi> ← <bdi dir="ltr">−۵۱٫۲٪</bdi>', "دو سال بکتست، قبل و بعد از اصلاح همین یک فرض"),
            ("۱۷۴ از ۱۸۶", "بار، سفارش‌های روی حساب دقیقاً همان بود که بکتست می‌خواست"),
            ("۲۶ ← ۳۱ از ۳۳", "معامله‌ی مشترک درست پیش‌بینی شد؛ قبل و بعد از اصلاح"),
            ("۰٫۶٪", "احتمال نتیجه‌ی حساب زنده اگر بکتست قدیمی راست می‌گفت")],
    fix="<b>کاری که کردیم:</b> بکتستر را روی داده‌ی یک‌دقیقه‌ای از نو ساختیم، با قیمت خرید و فروش جدا، اسپرد واقعی و سواپ. ربات و بکتستر حالا یک مغز مشترک دارند و آزمایش‌ها نشان می‌دهد در هر لحظه تصمیمشان یکی است. بکتستر عمومی‌ام قفلی دارد که اگر استراتژی آینده را ببیند، اجرا نمی‌شود. <b>امروز</b> در مرحله‌ی بازسازی ربات و بکتست دوباره با این موتور جدید هستیم.",
    net_h="وقتی اینترنت ملی شد، ربات زبان باز کرد",
    net_p="ربات روی سرور مجازی کار می‌کرد که یک‌باره بی‌هیچ دلیل ظاهری ارتباطش قطع شد. بعدها فهمیدم درست همان زمانی بود که اینترنت ایران ملی شد و به سرور دسترسی نداشتم. همین باعث شد موتوری بسازم که هر اتفاق را <b>کامل و خوانا</b> به پیام‌رسان داخلی «بله» بفرستد: هر سفارش با ریسک واقعی، هر لغو با دلیل دقیق، سیو سود، گزارش روزانه و پیام‌های نگهبان.",
    logs=[["🗑 سفارش لغو شد | زون <bdi>AUDUSD_H4_00300</bdi> | فروش", "├ عمر سفارش: ۵۹ دقیقه", "├ دلیل دقیق: روند روزانه: صعودی | روند <bdi>H4</bdi>: نزولی", "└ اقدام بعدی: دوباره چیده نمی‌شود"],
          ["🚨 ربات از کار افتاد! ۱۵ دقیقه است ضربان نزده — دارم دوباره راه‌اندازی‌اش می‌کنم…"],
          ["🛡 نگهبان: ✅ ربات برگشت (آخرین ضربان <bdi>0.3</bdi> دقیقه پیش)."]],
    log_cap="لاگ‌های واقعی نسخه‌ی قبلی ربات روی حساب دمو",
    method_h="روش کار من",
    method_p="امروز حتی برنامه‌نویس‌های باتجربه هم بیشتر کدشان را با هوش مصنوعی می‌نویسند. مهارت کمیاب، دانستن این است که <b>چه باید ساخت، چطور درستی‌اش را سنجید و کجا باید به نتیجه شک کرد.</b> نقش من طراحی سیستم، تعریف دقیق رفتار، آزمودن و داوری است.",
    loop=[("تعریف دقیق", "هر قانون و حالت خاص به زبان ساده و بی‌ابهام"), ("ساخت با هوش مصنوعی", "مدل کد می‌نویسد، من ساختار و تصمیم‌ها را هدایت می‌کنم"),
          ("آزمون با جواب معلوم", "داده‌ی ساختگی، متاتریدر ساختگی، حالت‌های از پیش دانسته"), ("مقایسه با واقعیت", "بکتست در برابر حساب زنده، معامله‌به‌معامله"),
          ("اصلاح و قفل کردن", "هر اصلاح با آزمونی که نمی‌گذارد خطا برگردد")],
    skills_h="مهارت‌ها",
    skills=["ساخت سیستم‌های نرم‌افزاری واقعی با هوش مصنوعی (کلود، جی‌پی‌تی): طراحی، تعریف دقیق، هدایت و آزمودن",
            "طراحی و راستی‌آزمایی بکتست: پیدا کردن «دیدن آینده»، تطبیق بکتست با حساب زنده",
            "معامله‌گری خودکار با متاتریدر ۵؛ اجرای ربات روی سرور مجازی ویندوز",
            "پایش و گزارش‌دهی: نگهبان خودکار، گزارش کامل در پیام‌رسان بله",
            "تحلیل بازار با پرایس‌اکشن (عرضه و تقاضا)؛ حدود دو سال و نیم تجربه از نوروز ۱۴۰۳",
            "تحلیل نتیجه‌ها در گزارش‌های اکسل"],
    info_h="اطلاعات فردی",
    info=[("متولد", "۱۳۸۳"), ("محل زندگی", "همدان"), ("تحصیلات", "دیپلم کامپیوتر، مدرسه‌ی شهید مطهری فریمان؛ یک سال دانشگاه و سپس ترک تحصیل برای تمرکز بر این پروژه"),
          ("نظام وظیفه", "مشمول"), ("زبان انگلیسی", "پایه")],
    work_h="شرایط همکاری",
    work=[("نوع همکاری", "حضوری یا دورکاری"), ("حقوق", "توافقی"), ("پروژه‌ی آزمایشی", "آماده‌ی یک پروژه‌ی آزمایشی کوتاه، رایگان یا با حقوق توافقی")],
    want="دنبال جایگاهی در تیم هوش مصنوعی، استارتاپ یا شرکت فین‌تک هستم؛ برای ساخت ابزار و سیستم با هوش مصنوعی، خودکارسازی فرایندها و بکتست و تحلیل داده‌ی بازار.",
    cta_h="همه‌ی جزئیات در سایت",
    cta_p="لاگ‌های واقعی، نمودار کامل، ۱۴ ایرادی که پیدا و ثبت شد، و کد کامل چهار ابزار عمومی (دانلودر تاریخچه، اسپردسنج، بکتستر و نگهبان).",
    made="این رزومه و سایتش با هوش مصنوعی ساخته شده‌اند.",
    page=lambda i, n: f"صفحه‌ی {str(i).translate(FA_DIG)} از {str(n).translate(FA_DIG)}",
),
"en": dict(
    dir="ltr", lang="en",
    name="Hossein Shirdel",
    role="Builder of real systems with AI · automated trading",
    contact=[("Phone", "+98 992 843 6013"), ("Email", EMAIL), ("City", "Hamedan, Iran")],
    qr_cap="Full site: every log, chart and line of public code",
    summary="For about a year I have been designing and building, with leading AI models such as Claude and GPT, a <b>five-part automated trading system</b> for MetaTrader 5: data download and cost measurement, a backtester, a trading robot, and a watchdog that looks after the robot day and night. When the backtest showed 825% profit and the live account lost money, I did not explain it away. I compared them trade by trade, <b>found the flaw in the backtest myself</b>, and rebuilt the system.",
    facts=[("5", "parts, one system"), ("6,500+", "lines of Python"), ("3 months", "live on a demo account"), ("6 years", "of 1-minute data")],
    sys_h="Project: an automated trading system",
    parts=[("Watchdog", "Checks the robot's heartbeat every 60 seconds; if the robot closes or hangs, it restarts it, finds the cause in the Windows event log (updates, power loss, sign-outs, crashes) and reports it on the Bale messenger.", True),
           ("Trading robot", "Runs the strategy on MetaTrader 5 and reports every action with its exact reason on Bale. It shares its decision engine with the backtester.", False),
           ("Backtester", "Simulates on 1-minute candles with separate bid and ask, real spread and swap; Excel report and a reason funnel.", False),
           ("History downloader", "Pulls 6 years of data from MetaTrader year by year and resumes if interrupted.", False),
           ("Spread meter", "Measures the broker's real spread from thousands of ticks (median, not mean).", False)],
    journey_h="The journey at a glance",
    journey_note="Illustrative: each candle is a step of the journey; green for progress, red for setbacks.",
    story=[("March 2024", "Into the markets and a year of daily practice. After one year at university I left to focus on this full time."),
           ("Insight", "A trader's real problem is self-control, not strategy. Anton Kreil said trading's future belongs to AI, and I decided to combine the two."),
           ("The past year", "Built the system with AI, ran it live for three months, found the backtest flaw, and rebuilt everything.")],
    ch_h="The biggest challenge: a backtest that fooled us for three months",
    ch_p1="One of the biggest dangers in building a trading robot is <b>an unrealistic backtest</b>. Our old backtest showed 825% profit over 6 years. The robot ran live for three months, but the results looked nothing like the backtest, and we had to rebuild the robot from scratch.",
    ch_p2="A trade-by-trade comparison showed that the robot's logic was right and the flaw was in the backtester. When an order filled inside a 4-hour candle, it assumed the candle's high and low happened <b>after</b> the entry, so it credited profits that really happened <b>before</b> the entry. The backtest could see the future.",
    chart_h="Six weeks, three versions of the same trades",
    chart_sub="Cumulative return on a $100,000 account, Aug 17 to Sep 28, 2026 (real data)",
    proofs=[("<s>+77.6%</s> → −51.2%", "two-year backtest, before and after fixing that one assumption"),
            ("174 / 186", "syncs where the orders on the account matched the backtest exactly"),
            ("26 → 31 / 33", "shared trades predicted correctly, before and after the fix"),
            ("0.6%", "chance of the live result if the old backtest had been right")],
    fix="<b>What we did:</b> rebuilt the backtester on 1-minute data with separate bid and ask, real spread and swap. The robot and the backtester now share one decision engine, and tests show their decisions match at every moment. My public backtester has a lock that refuses to run a strategy that sees the future. <b>Today</b> we are rebuilding the robot and re-running backtests with this new engine.",
    net_h="When the internet went national, the robot learned to talk",
    net_p="The robot was running on a virtual server when it went out of reach with no visible reason. Later I realized it was exactly when Iran's internet was cut to the national network and I could not reach the server. So I built an engine that sends every event, <b>complete and readable</b>, to the domestic messenger Bale: every order with its real risk, every cancellation with its exact reason, partial closes, daily reports, and watchdog messages.",
    logs=[["🗑 Order cancelled | zone AUDUSD_H4_00300 | sell", "├ Order age: 59 minutes", "├ Exact reason: daily trend up | H4 trend down", "└ Next step: not re-placed"],
          ["🚨 Robot down! No heartbeat for 15 minutes — restarting it now…"],
          ["🛡 Watchdog: ✅ robot is back (last heartbeat 0.3 minutes ago)."]],
    log_cap="Real logs from the previous robot on a demo account, translated from Persian",
    method_h="How I work",
    method_p="Today even experienced programmers write most of their code with AI. The scarce skill is knowing <b>what to build, how to prove it works, and when to doubt a result.</b> My role is system design, precise specification, testing and judgment.",
    loop=[("Specify", "every rule and edge case in plain, unambiguous language"), ("Build with AI", "the model writes the code; I direct structure and decisions"),
          ("Test against known answers", "synthetic data, a fake MetaTrader, cases with known results"), ("Compare with reality", "backtest versus live account, trade by trade"),
          ("Fix and lock in", "every fix ships with a test that keeps the mistake from returning")],
    skills_h="Skills",
    skills=["Building real software systems with AI (Claude, GPT): design, specification, direction and testing",
            "Backtest design and validation: detecting look-ahead, reconciling backtests with live accounts",
            "Automated trading on MetaTrader 5; running robots on Windows virtual servers",
            "Monitoring and reporting: an automatic watchdog and full reports on the Bale messenger",
            "Price-action market analysis (supply and demand); about two and a half years of experience since March 2024",
            "Analyzing results in Excel reports"],
    info_h="Personal details",
    info=[("Born", "2004"), ("Based in", "Hamedan, Iran"), ("Education", "High-school diploma in computing, Shahid Motahari School, Fariman; one year of university, then left to focus on this project"),
          ("Military service", "Not yet completed"), ("English", "Basic")],
    work_h="Working together",
    work=[("Arrangement", "On-site or remote"), ("Salary", "Negotiable"), ("Trial project", "Happy to start with a short trial project, unpaid or at a negotiated rate")],
    want="I am looking for a role on an AI team, a startup or a fintech company, building tools and systems with AI, automating processes, and running backtests and analysis on market data.",
    cta_h="Every detail is on the site",
    cta_p="Real logs, the full chart, the 14 issues we found and logged, and full source for four public tools (history downloader, spread meter, backtester and watchdog).",
    made="This résumé and its site were built with AI.",
    page=lambda i, n: f"Page {i} of {n}",
),
}

CSS = """
@page { size: A4; margin: 0; }
* { box-sizing: border-box; }
:root { --ink: #0c1120; --ink2: #121a2b; --fg: #151b29; --fg2: #3d4558; --muted: #6b7386; --rule: #e3e6ec; --gold: #b8862b; --gold-l: #e0b44c;
  --up: #1f8f84; --down: #d64541; --paper: #ffffff; --tint: #f5f6f9; }
html, body { margin: 0; background: var(--paper); color: var(--fg); -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { font: 400 9.6pt/1.75 "Vazirmatn", Tahoma, sans-serif; }
html[lang=en] body { font: 400 9.4pt/1.5 "IBM Plex Sans", "Segoe UI", sans-serif; }
.page { width: 210mm; height: 297mm; position: relative; overflow: hidden; page-break-after: always; display: flex; flex-direction: column; }
.page:last-child { page-break-after: auto; }
.pad { padding: 0 14mm; }
b { font-weight: 700; color: var(--fg); }
h2 { font-size: 12.5pt; font-weight: 800; margin: 0 0 2.2mm; color: var(--ink); display: flex; align-items: center; gap: 2.5mm; }
html[lang=en] h2 { font-family: "IBM Plex Sans Condensed", "IBM Plex Sans", sans-serif; font-weight: 700; font-size: 13pt; }
h2::before { content: ""; width: 1.4mm; height: 4.6mm; background: var(--gold); border-radius: .6mm; flex: none; }
p { margin: 0; color: var(--fg2); }
.sec { margin-top: 5.5mm; }
/* header */
.head { background: var(--ink); color: #e9ecf3; padding: 11mm 14mm 9mm; display: grid; grid-template-columns: 1fr 31mm; gap: 8mm; align-items: center; position: relative; }
.head::after { content: ""; position: absolute; inset-inline: 0; bottom: 0; height: 1.2mm; background: linear-gradient(90deg, var(--gold-l), #f3d27e 40%, var(--gold-l)); }
.head h1 { margin: 0; font-size: 25pt; line-height: 1.2; font-weight: 900; color: #fff; }
html[lang=en] .head h1 { font-family: "IBM Plex Sans Condensed", sans-serif; font-weight: 700; font-size: 27pt; line-height: 1.05; }
.head .role { color: var(--gold-l); font-weight: 700; font-size: 10.5pt; margin-top: 1.5mm; }
.contact { display: flex; flex-wrap: wrap; gap: 1.5mm 7mm; margin-top: 4mm; font-size: 9pt; color: #b9c1d2; }
.contact span b { color: #8a95ab; font-weight: 500; margin-inline-end: 1.5mm; }
.contact .v { color: #e9ecf3; font-family: "IBM Plex Mono", monospace; direction: ltr; unicode-bidi: isolate; }
html[lang=fa] .contact .v.fa-num { font-family: "Vazirmatn", sans-serif; }
.qr { background: #fff; border-radius: 2.5mm; padding: 1.6mm; width: 31mm; height: 31mm; }
.qr-cap { grid-column: 2; font-size: 7pt; color: #b9c1d2; text-align: center; margin-top: -5mm; line-height: 1.4; }
/* facts */
.facts { display: grid; grid-template-columns: repeat(4, 1fr); gap: 4mm; margin-top: 4mm; }
.fact { border-top: .5mm solid var(--rule); padding-top: 2mm; }
.fact b { display: block; font-size: 15pt; line-height: 1.3; font-weight: 800; color: var(--ink); }
html[lang=en] .fact b { font-family: "IBM Plex Mono", monospace; font-weight: 500; font-size: 14pt; }
.fact span { color: var(--muted); font-size: 8.4pt; }
/* parts */
.parts { display: grid; grid-template-columns: 1fr 1fr; gap: 3mm; }
.part { border: .3mm solid var(--rule); border-radius: 2.5mm; padding: 3mm 3.6mm; }
.part h3 { margin: 0 0 .8mm; font-size: 10.3pt; font-weight: 800; color: var(--ink); }
html[lang=en] .part h3 { font-family: "IBM Plex Sans Condensed", sans-serif; font-weight: 700; font-size: 10.8pt; }
.part p { font-size: 8.7pt; line-height: 1.65; }
html[lang=en] .part p { line-height: 1.45; }
.part.star { grid-column: 1 / -1; border-color: var(--gold); background: linear-gradient(180deg, rgba(224, 180, 76, .12), rgba(224, 180, 76, 0) 80%); display: grid; grid-template-columns: 26mm 1fr; gap: 4mm; align-items: center; }
.part.star .ekg { height: 14mm; }
.part.star h3 { font-size: 11.5pt; }
.badge { display: inline-block; font-size: 7pt; color: var(--gold); border: .3mm solid var(--gold); border-radius: 10mm; padding: 0 2mm; margin-inline-start: 2mm; vertical-align: middle; font-weight: 700; }
/* journey */
.strip { border: .3mm solid var(--rule); border-radius: 2.5mm; padding: 2mm 3mm 1mm; }
.strip .sl { font-size: 8.4px; fill: var(--fg2); font-family: "Vazirmatn", sans-serif; font-weight: 700; }
html[lang=en] .strip .sl { font-family: "IBM Plex Sans", sans-serif; font-weight: 600; font-size: 9px; }
.note { font-size: 7.6pt; color: var(--muted); margin-top: 1mm; }
.story3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 4mm; margin-top: 3mm; }
.story3 div b { display: block; color: var(--gold); font-size: 9pt; }
.story3 div p { font-size: 8.6pt; line-height: 1.65; }
html[lang=en] .story3 div p { line-height: 1.45; }
/* chart */
.chartbox { border: .3mm solid var(--rule); border-radius: 2.5mm; padding: 3mm 4mm 2mm; margin-top: 3mm; }
.chartbox h3 { margin: 0; font-size: 10pt; font-weight: 800; color: var(--ink); }
html[lang=en] .chartbox h3 { font-family: "IBM Plex Sans Condensed", sans-serif; font-weight: 700; }
.chartbox .sub { font-size: 8pt; color: var(--muted); }
.ax { font: 9px "IBM Plex Mono", monospace; fill: #6b7386; }
html[lang=fa] .ax { font-family: "Vazirmatn", sans-serif; font-size: 9.5px; }
.ev { font: 600 11px "IBM Plex Mono", monospace; fill: #151b29; }
html[lang=fa] .ev { font-family: "Vazirmatn", sans-serif; font-weight: 800; }
.en2 { font: 600 9.5px "IBM Plex Sans", sans-serif; }
html[lang=fa] .en2 { font-family: "Vazirmatn", sans-serif; font-weight: 700; }
.two { display: grid; grid-template-columns: 1fr 1fr; gap: 6mm; }
.proofs { display: grid; grid-template-columns: repeat(4, 1fr); gap: 3.5mm; margin-top: 3.5mm; }
.proof { border-top: .5mm solid var(--rule); padding-top: 1.8mm; }
.proof b { display: block; font-size: 12pt; font-weight: 800; color: var(--ink); line-height: 1.4; }
html[lang=en] .proof b { font-family: "IBM Plex Mono", monospace; font-weight: 500; font-size: 11pt; }
.proof b s { color: var(--muted); text-decoration-color: var(--down); }
.proof span { font-size: 7.9pt; color: var(--fg2); line-height: 1.5; display: block; }
.fixbox { background: var(--tint); border-radius: 2.5mm; padding: 3mm 4mm; margin-top: 3.5mm; }
.fixbox p { font-size: 9pt; }
/* logs */
.netgrid { display: grid; grid-template-columns: 1fr 74mm; gap: 6mm; align-items: start; }
.phone { background: var(--ink); border-radius: 4mm; padding: 3mm; display: grid; gap: 2mm; }
.phone .bar { color: #e9ecf3; font-weight: 800; font-size: 8.6pt; font-family: "Vazirmatn", sans-serif; display: flex; align-items: center; gap: 2mm; direction: rtl; }
html[lang=en] .phone .bar { direction: ltr; font-family: "IBM Plex Sans", sans-serif; }
.phone .bar i { width: 5mm; height: 5mm; border-radius: 50%; background: var(--gold-l); color: var(--ink); display: grid; place-items: center; font-style: normal; font-size: 7.5pt; }
.msg { background: #1a2335; color: #e9ecf3; border-radius: 2.5mm; padding: 1.8mm 2.6mm; font-size: 8pt; line-height: 1.6; font-family: "Vazirmatn", sans-serif; }
html[lang=en] .msg { font-family: "IBM Plex Sans", sans-serif; line-height: 1.4; }
.msg span { display: block; }
.cap { font-size: 7.2pt; color: var(--muted); margin-top: 1.2mm; }
/* method */
.loop { display: grid; grid-template-columns: repeat(5, 1fr); gap: 2.5mm; margin-top: 3mm; counter-reset: s; }
.loop div { border-top: .6mm solid var(--gold); padding-top: 1.8mm; counter-increment: s; }
.loop div b { display: block; font-size: 9pt; }
.loop div b::before { content: counter(s) ". "; color: var(--gold); }
html[lang=fa] .loop div b::before { content: counter(s, persian) ". "; }
.loop div span { font-size: 8pt; color: var(--fg2); line-height: 1.5; display: block; }
ul.sk { margin: 0; padding: 0; list-style: none; display: grid; gap: 1.6mm; }
ul.sk li { display: grid; grid-template-columns: 2mm 1fr; gap: 2.5mm; color: var(--fg2); font-size: 9pt; line-height: 1.6; }
html[lang=en] ul.sk li { line-height: 1.4; }
ul.sk li::before { content: ""; width: 1.6mm; height: 1.6mm; border-radius: 50%; background: var(--gold); margin-top: 2.2mm; }
html[lang=en] ul.sk li::before { margin-top: 1.6mm; }
dl.kv { margin: 0; display: grid; gap: 0; border-top: .3mm solid var(--rule); }
dl.kv div { display: grid; grid-template-columns: 27mm 1fr; gap: 3mm; padding: 1.7mm 0; border-bottom: .3mm solid var(--rule); font-size: 9pt; }
dl.kv dt { color: var(--muted); }
dl.kv dd { margin: 0; color: var(--fg); }
.cta { margin-top: auto; background: var(--ink); color: #e9ecf3; padding: 7mm 14mm; display: grid; grid-template-columns: 1fr 30mm; gap: 7mm; align-items: center; }
.cta h2 { color: #fff; font-size: 14pt; }
.cta p { color: #b9c1d2; font-size: 9pt; }
.cta .link { font-family: "IBM Plex Mono", monospace; color: var(--gold-l); font-size: 9pt; margin-top: 2mm; direction: ltr; unicode-bidi: isolate; display: inline-block; }
.foot { display: flex; justify-content: space-between; font-size: 7.4pt; color: var(--muted); padding: 3mm 14mm 5mm; margin-top: auto; }
.cta + .foot { display: none; }
"""

EKG = '<svg class="ekg" viewBox="0 0 160 50" width="100%" xmlns="http://www.w3.org/2000/svg"><line x1="0" y1="30" x2="160" y2="30" stroke="#e3e6ec"/><path d="M0 30 H50 L58 30 L64 12 L72 46 L80 4 L88 38 L94 30 H160" fill="none" stroke="#b8862b" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"/></svg>'


def build(lang):
    t = T[lang]
    qr = qr_svg(SITE + ("#en" if lang == "en" else "#fa"))
    N = 3
    foot = lambda i: f'<div class="foot"><span>{t["name"]} · {t["made"]}</span><span>{t["page"](i, N)}</span></div>'
    contact = "".join(f'<span><b>{k}</b><span class="v{" fa-num" if lang == "fa" and k == "تلفن" else ""}">{v}</span></span>' if k != ("شهر" if lang == "fa" else "City")
                      else f'<span><b>{k}</b>{v}</span>' for k, v in t["contact"])
    facts = "".join(f'<div class="fact"><b>{a}</b><span>{b}</span></div>' for a, b in t["facts"])
    star = t["parts"][0]
    parts = (f'<div class="part star">{EKG}<div><h3>{star[0]}<span class="badge">{"بخش ویژه" if lang == "fa" else "highlight"}</span></h3><p>{star[1]}</p></div></div>' +
             "".join(f'<div class="part"><h3>{a}</h3><p>{b}</p></div>' for a, b, _ in t["parts"][1:]))
    story = "".join(f'<div><b>{a}</b><p>{b}</p></div>' for a, b in t["story"])
    proofs = "".join(f'<div class="proof"><b>{a}</b><span>{b}</span></div>' for a, b in t["proofs"])
    logs = "".join('<div class="msg">' + "".join(f'<span dir="{t["dir"]}">{ln}</span>' for ln in m) + "</div>" for m in t["logs"])
    loop = "".join(f'<div><b>{a}</b><span>{b}</span></div>' for a, b in t["loop"])
    skills = "".join(f"<li><span>{s}</span></li>" for s in t["skills"])
    info = "".join(f"<div><dt>{a}</dt><dd>{b}</dd></div>" for a, b in t["info"])
    work = "".join(f"<div><dt>{a}</dt><dd>{b}</dd></div>" for a, b in t["work"])
    bot = "لاگ ربات" if lang == "fa" else "Robot log"
    return f"""<!doctype html><html lang="{t['lang']}" dir="{t['dir']}"><head><meta charset="utf-8">
<title>{t['name']}</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans+Condensed:wght@600;700&family=IBM+Plex+Sans:wght@400;500;600;700&family=Vazirmatn:wght@400;500;700;800;900&display=swap">
<style>{CSS}</style></head><body>
<section class="page">
  <header class="head">
    <div><h1>{t['name']}</h1><div class="role">{t['role']}</div><div class="contact">{contact}</div></div>
    <div class="qr">{qr}</div><div></div><div class="qr-cap">{t['qr_cap']}</div>
  </header>
  <div class="pad">
    <div class="sec"><p style="font-size:10pt">{t['summary']}</p></div>
    <div class="facts">{facts}</div>
    <div class="sec"><h2>{t['sys_h']}</h2><div class="parts">{parts}</div></div>
    <div class="sec"><h2>{t['journey_h']}</h2><div class="strip">{candle_strip(lang)}</div><div class="note">{t['journey_note']}</div></div>
  </div>
  {foot(1)}
</section>
<section class="page">
  <div class="pad" style="padding-top:12mm">
    <h2>{t['ch_h']}</h2>
    <div class="two"><p>{t['ch_p1']}</p><p>{t['ch_p2']}</p></div>
    <div class="chartbox"><h3>{t['chart_h']}</h3><div class="sub">{t['chart_sub']}</div>{compare_chart(lang)}</div>
    <div class="proofs">{proofs}</div>
    <div class="fixbox"><p>{t['fix']}</p></div>
    <div class="sec"><h2>{t['net_h']}</h2>
      <div class="netgrid"><p>{t['net_p']}</p><div><div class="phone"><div class="bar"><i>{"ل" if lang == "fa" else "R"}</i>{bot}</div>{logs}</div><div class="cap">{t['log_cap']}</div></div></div>
    </div>
  </div>
  {foot(2)}
</section>
<section class="page">
  <div class="pad" style="padding-top:12mm">
    <h2>{"درباره‌ی من" if lang == "fa" else "About me"}</h2><div class="story3" style="margin-top:0">{story}</div>
    <div class="sec"></div>
    <h2>{t['method_h']}</h2><p>{t['method_p']}</p><div class="loop">{loop}</div>
    <div class="two sec">
      <div><h2>{t['skills_h']}</h2><ul class="sk">{skills}</ul></div>
      <div><h2>{t['info_h']}</h2><dl class="kv">{info}</dl></div>
    </div>
    <div class="two sec">
      <div><h2>{t['work_h']}</h2><dl class="kv">{work}</dl></div>
      <div><h2>{"دنبال چه هستم" if lang == "fa" else "What I am looking for"}</h2><p>{t['want']}</p></div>
    </div>
  </div>
  <div class="cta"><div><h2>{t['cta_h']}</h2><p>{t['cta_p']}</p><span class="link">{SITE_SHORT}{"#en" if lang == "en" else ""}</span></div><div class="qr">{qr}</div></div>
</section>
</body></html>"""


def main(out_dir=HERE, route_fonts=None):
    import asyncio
    from playwright.async_api import async_playwright

    async def run():
        async with async_playwright() as p:
            b = await p.chromium.launch(executable_path=os.environ.get("CHROMIUM", "/opt/pw-browsers/chromium"))
            res = []
            for lang, fn in (("fa", "رزومه_حسین_شیردل.pdf"), ("en", "Hossein_Shirdel_Resume.pdf")):
                html = build(lang)
                hp = os.path.join(out_dir, f"resume_{lang}.html")
                open(hp, "w", encoding="utf-8").write(html)
                pg = await b.new_page()
                if route_fonts:
                    await pg.route(re.compile(r"https://fonts\.(googleapis|gstatic)\.com/.*"), route_fonts)
                await pg.goto("file://" + hp, wait_until="networkidle")
                await pg.evaluate("document.fonts.ready")
                over = await pg.evaluate("[...document.querySelectorAll('.page')].map(p => p.scrollHeight - p.clientHeight)")
                pdf = os.path.join(out_dir, fn)
                await pg.pdf(path=pdf, format="A4", print_background=True, margin={"top": "0", "bottom": "0", "left": "0", "right": "0"})
                res.append((pdf, over))
                await pg.close()
                os.remove(hp)
            await b.close()
            return res
    return asyncio.run(run())


if __name__ == "__main__":
    for pdf, over in main():
        print(pdf, "overflow per page (px):", over)
