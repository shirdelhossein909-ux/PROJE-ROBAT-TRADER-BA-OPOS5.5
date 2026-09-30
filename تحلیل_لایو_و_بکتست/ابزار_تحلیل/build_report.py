# -*- coding: utf-8 -*-
"""ساختن گزارش نهایی: یک صفحه‌ی HTML فارسی (ساده و کامل) + یک فایل اکسل جزئیات."""
import os, sys, pickle, html
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
OUTDIR = os.path.dirname(HERE)
CACHE = os.path.join(HERE, "_cache")
sys.path.insert(0, HERE)
from compare import close  # noqa: E402

HTML_PATH = os.path.join(OUTDIR, "گزارش_مقایسه_لایو_و_بکتست.html")
XLSX_PATH = os.path.join(OUTDIR, "جزئیات_مقایسه_لایو_و_بکتست.xlsx")

FA = str.maketrans("0123456789-", "۰۱۲۳۴۵۶۷۸۹−")


RS = "R"
LRI, PDI = "\u2066", "\u2069"   # جداسازی جهت: علامت منفی/مثبت در متن راست‌به‌چپ جابه‌جا نشود


def num(txt):
    """یک عدد/عبارت لاتین را در متن راست‌به‌چپ چپ‌به‌راست نگه می‌دارد."""
    return LRI + txt + PDI


def fa(x, nd=None, sign=False, pct=False, money=False, suffix=""):
    """عدد → متن فارسی."""
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return "—"
    if isinstance(x, str):
        return x.translate(FA)
    if nd is None:
        nd = 0 if float(x).is_integer() else 2
    s = f"{x:{'+' if sign else ''},.{nd}f}"
    s = s.replace(",", "٬").replace(".", "٫")
    if pct:
        s += "٪"
    if money:
        s += "$"
    return LRI + s.translate(FA) + suffix + PDI


def esc(s):
    return html.escape(str(s))


# ---------------------------------------------------------------- داده‌ها
live = pd.read_pickle(os.path.join(CACHE, "live_trades.pkl"))
deals = pd.read_pickle(os.path.join(CACHE, "live_deals.pkl"))
orders = pd.read_pickle(os.path.join(CACHE, "live_orders.pkl"))
emu = pickle.load(open(os.path.join(CACHE, "emu_results.pkl"), "rb"))
dec = pd.read_pickle(os.path.join(CACHE, "decisions.pkl"))
mA = pd.read_pickle(os.path.join(CACHE, "match_A_backtester_like.pkl"))
classic = pickle.load(open(os.path.join(CACHE, "classic.pkl"), "rb"))
cfull = pickle.load(open(os.path.join(CACHE, "classic_full.pkl"), "rb"))

START_EQ = 100000.0


def emu_stats(name):
    r = emu[name]
    t = r["trades"]
    return dict(n=len(t), wins=int((t["R"] > 0).sum()), R=float(t["R"].sum()),
                usd=r["equity"] - START_EQ, ret=(r["equity"] / START_EQ - 1) * 100, dd=r["maxdd"] * 100)


live_bal = deals[deals["type"] != "balance"][["time", "balance"]].dropna()
live_curve = [(pd.Timestamp("2026-08-14"), 0.0)] + [(t, (b / START_EQ - 1) * 100) for t, b in zip(live_bal["time"], live_bal["balance"])]
peak, ldd = START_EQ, 0.0
for b in live_bal["balance"]:
    peak = max(peak, b)
    ldd = max(ldd, (peak - b) / peak)
S_LIVE = dict(n=len(live), wins=int((live["profit"] > 0).sum()), R=float(live["R_price"].sum()),
              usd=float(live["profit"].sum()), ret=float(live["profit"].sum()) / START_EQ * 100, dd=ldd * 100)
S = {k: emu_stats(k) for k in ("A_backtester_like", "F_pess_entry", "G_pess_spread", "H_pess_spread_down")}
ct = classic["trades"]
S_CL = dict(n=len(ct), wins=int((ct["نتیجه_R"] > 0).sum()), R=float(ct["نتیجه_R"].sum()),
            usd=classic["equity"] - START_EQ, ret=(classic["equity"] / START_EQ - 1) * 100, dd=classic["maxdd"] * 100)

n_sync = len(dec)
n_sync_same = int(((dec.only_emu == 0) & (dec.only_live == 0)).sum())
emu_orders = int(dec.emu_n.sum())
both_orders = int(dec.both.sum())
n_dup_sync = int((dec.live_dups > 0).sum())
n_orders_total = int(orders["type"].str.contains("limit").sum())

# تطبیق معامله‌ها
mb = mA[mA["وضعیت"] == "هر دو"]
n_live_in_emu = len(mb)
# کلاسیک ∩ لایو
from emulate import digits  # noqa: E402
ck = [(s, "BUY" if d == "خرید" else "SELL", round(e, digits(s)), round(sl, digits(s)))
      for s, d, e, sl in zip(ct["نماد"], ct["جهت"], ct["ورود"], ct["حدضرر"])]
lk = [(s, d, round(e, digits(s)), round(sl, digits(s))) for s, d, e, sl in zip(live.sym, live.dir, live.entry, live.sl)]
used, n_cl_live = set(), 0
for x in ck:
    for j, y in enumerate(lk):
        if j not in used and close(x, y):
            used.add(j)
            n_cl_live += 1
            break


def cat(r):
    if pd.isna(r):
        return None
    return "TP" if r > 1.2 else ("partial" if r > 0 else "SL")


def agree_count(name):
    from compare import match_trades
    m = match_trades(name)
    b = m[m["وضعیت"] == "هر دو"]
    b = b[~((b["نماد"] == "USDCHF") & (b["زمان_پر_شدن_لایو"] >= "2026-09-25"))]  # بعد از پایان دیتا بسته شد
    return len(b), int((b["R_لایو"].map(cat) == b["R_بکتست"].map(cat)).sum()), float(b["R_لایو"].sum()), float(b["R_بکتست"].sum())


AG_A = agree_count("A_backtester_like")
AG_F = agree_count("F_pess_entry")

# کل ۲ سال
two = {}
for k, lab in ((False, "بکتستر فعلی (بدون تغییر)"), ("mid", "کندل ورود «میانه» (از روی رنگ کندل)"), (True, "کندل ورود «بدبینانه»")):
    d = cfull[k]
    t = d["trades"]
    two[k] = dict(label=lab, n=len(t), wr=(t["نتیجه_R"] > 0).mean() * 100, R=t["نتیجه_R"].sum(),
                  ret=(d["equity"] / START_EQ - 1) * 100, dd=d["mdd"] * 100,
                  neg=int((d["monthly"] < 0).sum()), months=len(d["monthly"]), monthly=d["monthly"],
                  per_sym=d["per_sym"])
same_bar = cfull[False]["trades"]
n_same_bar = int((same_bar["زمان_ورود"] == pd.to_datetime(same_bar["زمان_خروج"])).sum())

# ---------------------------------------------------------------- جدول معامله‌به‌معامله
emuH = emu["H_pess_spread_down"]["trades"]


def h_result(row):
    k = (row["نماد"], row["جهت"], round(row["ورود"], digits(row["نماد"])), round(row["استاپ"], digits(row["نماد"])))
    t_ref = row["زمان_پر_شدن_لایو"] if pd.notna(row.get("زمان_پر_شدن_لایو")) else row["کندل_پر_شدن_بکتست"]
    for _, e in emuH.iterrows():
        if close(e["key"], k) and abs(e["fill_time"] - pd.Timestamp(t_ref).floor("4h")) <= pd.Timedelta(hours=8):
            return e["R"], e["why"] + (" + سیو سود" if e["partial"] else "")
    return None, "پر نشد"


rows = []
for _, r in mA.iterrows():
    hr, hw = h_result(r)
    rows.append({
        "وضعیت": r["وضعیت"], "نماد": r["نماد"], "جهت": "خرید" if r["جهت"] == "BUY" else "فروش",
        "زون (کامنت لایو)": r.get("زون_لایو", ""),
        "زمان پر شدن (سرور)": r["زمان_پر_شدن_لایو"] if pd.notna(r.get("زمان_پر_شدن_لایو")) else r["کندل_پر_شدن_بکتست"],
        "ورود": r["ورود"], "استاپ": r["استاپ"], "تارگت": r["تارگت"], "فاصله‌ی استاپ (پیپ)": r["ریسک_پیپ"],
        "نتیجه‌ی لایو": r.get("نتیجه_لایو"), "R لایو": r.get("R_لایو"), "سود لایو $": r.get("سود_لایو"),
        "نتیجه‌ی بکتست (روش فعلی)": r.get("نتیجه_بکتست"), "R بکتست (روش فعلی)": r.get("R_بکتست"),
        "نتیجه‌ی بکتست واقع‌بینانه": hw, "R بکتست واقع‌بینانه": hr,
    })
TT = pd.DataFrame(rows)


def why_note(r):
    if r["وضعیت"] == "فقط بکتست":
        return {("XAUUSD"): "طلا ساعت ۰۰ بسته است؛ کف کندل در دقایق اول بازگشایی بود (قبل از ثبت سفارش) / اسپرد بازگشایی",
                ("AUDJPY"): "ربات در این ساعت خاموش بود (۲۸ آگوست)",
                ("CHFJPY"): "کف کندل فقط ۱.۹ پیپ زیر ورود بود؛ با اسپرد، قیمت Ask به ورود نرسید",
                ("AUDUSD"): "کف کندل ۲.۲ پیپ زیر ورود و در ساعت رول‌اوور (اسپرد پهن) بود",
                ("NZDCAD"): "جهش لحظه‌ای قیمت Bid در رول‌اوور ساعت ۰۰ (۲۶ پیپ) — Ask آن‌جا نرفت"}.get(r["نماد"], "")
    if r["وضعیت"] == "هر دو":
        rl, rb_ = r["R لایو"], r["R بکتست (روش فعلی)"]
        if pd.notna(rl) and pd.notna(rb_) and cat(rl) != cat(rb_):
            if r["نماد"] == "USDCHF" and str(r["زمان پر شدن (سرور)"]) >= "2026-09-25":
                return "دیتا ۲۵ سپتامبر تمام شد؛ این معامله ۲۸ سپتامبر با تارگت بسته شد"
            return "بکتست فرض کرد بعد از ورود، قیمت به 2R/تارگت رسیده؛ ولی آن حرکت قبل از پر شدن سفارش بود"
        if r["نماد"] == "GBPJPY" and rl < 2.3 and pd.notna(rb_) and rb_ > 2.3:
            return "باگ سیو سود: حجم ۹ بار نصف شد و فقط ۰٫۰۱ لات به تارگت رسید"
    return ""


TT["توضیح اختلاف"] = TT.apply(why_note, axis=1)

# ---------------------------------------------------------------- نمودارها (SVG درون‌خطی)


def line_chart(series, x0, x1, y_fmt, width=920, height=330, x_ticks=None, zero=True):
    L, R, T, B = 58, 70, 14, 34
    ys = [v for _, _, pts in series for _, v in pts]
    vmin, vmax = min(ys + [0]), max(ys + [0])
    span = vmax - vmin or 1
    vmin -= span * 0.08
    vmax += span * 0.08
    W, H = width - L - R, height - T - B

    def X(t):
        return L + (pd.Timestamp(t) - x0) / (x1 - x0) * W

    def Y(v):
        return T + (vmax - v) / (vmax - vmin) * H

    import math
    raw = (vmax - vmin) / 5
    mag = 10 ** math.floor(math.log10(raw))
    step = min((m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw), default=raw)
    out = [f'<svg viewBox="0 0 {width} {height}" class="chart" role="img" direction="ltr">']
    v = math.ceil(vmin / step) * step
    while v <= vmax:
        out.append(f'<line x1="{L}" x2="{L+W}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" class="grid{" zero" if abs(v) < 1e-9 and zero else ""}"/>')
        out.append(f'<text x="{L-8}" y="{Y(v)+4:.1f}" class="ylab" text-anchor="end">{y_fmt(v)}</text>')
        v += step
    for t, lab in (x_ticks or []):
        out.append(f'<line x1="{X(t):.1f}" x2="{X(t):.1f}" y1="{T}" y2="{T+H}" class="grid"/>')
        out.append(f'<text x="{X(t):.1f}" y="{T+H+22}" class="xlab" text-anchor="middle">{lab}</text>')
    ends = sorted(((Y(sorted(p, key=lambda q: q[0])[-1][1]), i) for i, (_, _, p) in enumerate(series)))
    lab_y, last = {}, -1e9
    for y, i in ends:
        y = max(y, last + 15)
        lab_y[i] = y
        last = y
    for si, (label, cls, pts) in enumerate(series):
        pts = sorted(pts, key=lambda p: p[0])
        d = []
        for i, (t, v) in enumerate(pts):
            if i == 0:
                d.append(f"M{X(t):.1f},{Y(v):.1f}")
            else:
                d.append(f"H{X(t):.1f}V{Y(v):.1f}")
        out.append(f'<path d="{"".join(d)}" class="ln {cls}"/>')
        t, v = pts[-1]
        out.append(f'<circle cx="{X(t):.1f}" cy="{Y(v):.1f}" r="3.5" class="dot {cls}"/>')
        out.append(f'<text x="{X(t)+7:.1f}" y="{lab_y[si]+4:.1f}" class="endlab {cls}">{y_fmt(v)}</text>')
    out.append("</svg>")
    return "".join(out)


def pct_fmt(v):
    return fa(v, 1 if abs(v) < 10 else 0, sign=True, pct=True)


x0, x1 = pd.Timestamp("2026-08-14"), pd.Timestamp("2026-09-30")
ticks = [(pd.Timestamp(d), fa(pd.Timestamp(d).strftime("%m/%d"))) for d in
         ("2026-08-17", "2026-08-24", "2026-08-31", "2026-09-07", "2026-09-14", "2026-09-21", "2026-09-28")]


def emu_curve(name):
    return [(x0, 0.0)] + [(t, (e / START_EQ - 1) * 100) for t, e in emu[name]["curve"]]


CH1 = line_chart([("لایو", "s-live", live_curve),
                  ("بکتست روش فعلی", "s-bt", emu_curve("A_backtester_like")),
                  ("بکتست واقع‌بینانه", "s-real", emu_curve("H_pess_spread_down"))],
                 x0, x1, pct_fmt, x_ticks=ticks)


def month_curve(k):
    m = two[k]["monthly"]
    eq = (1 + m / 100).cumprod()
    return [(pd.Timestamp("2024-10-01"), 0.0)] + [(t, (e - 1) * 100) for t, e in zip(m.index, eq)]


mx0, mx1 = pd.Timestamp("2024-10-01"), pd.Timestamp("2026-10-01")
mticks = [(pd.Timestamp(d), fa(pd.Timestamp(d).strftime("%Y/%m"))) for d in
          ("2025-01-01", "2025-05-01", "2025-09-01", "2026-01-01", "2026-05-01", "2026-09-01")]
CH2 = line_chart([("فعلی", "s-bt", month_curve(False)), ("میانه", "s-real", month_curve("mid")),
                  ("بدبینانه", "s-live", month_curve(True))], mx0, mx1, pct_fmt, x_ticks=mticks)

# آبشار R
wf = [("بکتست «عین لایو» با روش فعلی بکتستر", S["A_backtester_like"]["R"], "total"),
      ("اصلاح فرضِ کندل ورود", S["F_pess_entry"]["R"] - S["A_backtester_like"]["R"], "step"),
      ("اسپرد واقعی به‌جای مدل هزینه‌ی بکتستر", S["G_pess_spread"]["R"] - S["F_pess_entry"]["R"], "step"),
      ("خاموشی‌های ربات", S["H_pess_spread_down"]["R"] - S["G_pess_spread"]["R"], "step"),
      ("باگ سیو سود، رول‌اوور، اختلاف اسپرد و …", S_LIVE["R"] - S["H_pess_spread_down"]["R"], "step"),
      ("نتیجه‌ی واقعی لایو", S_LIVE["R"], "total")]
cum, pos = 0.0, []
for lab, v, kind in wf:
    if kind == "total":
        a, b = 0.0, v
        cum = v
    else:
        a, b = cum, cum + v
        cum = b
    pos.append((lab, v, kind, a, b))
lo = min(min(a, b) for _, _, _, a, b in pos + [("", 0, "", 0, 0)])
hi = max(max(a, b) for _, _, _, a, b in pos + [("", 0, "", 0, 0)])
lo, hi = lo - 1, hi + 1


def pc(x):
    return (x - lo) / (hi - lo) * 100


WF = ['<div class="wf">']
for lab, v, kind, a, b in pos:
    cls = "tot" if kind == "total" else ("up" if v >= 0 else "down")
    l_, r_ = min(pc(a), pc(b)), max(pc(a), pc(b))
    WF.append(f'<div class="wf-row"><div class="wf-lab">{esc(lab)}</div>'
              f'<div class="wf-track"><span class="wf-zero" style="left:{pc(0):.2f}%"></span>'
              f'<span class="wf-bar {cls}" style="left:{l_:.2f}%;width:{max(r_-l_,0.6):.2f}%"></span></div>'
              f'<div class="wf-val {cls}">{fa(v, 1, sign=True, suffix=RS)}</div></div>')
WF.append("</div>")
WF = "".join(WF)

# ---------------------------------------------------------------- جدول‌های HTML


def scen_row(name, s, note="", cls=""):
    wr = s["wins"] / s["n"] * 100 if s["n"] else 0
    return (f'<tr class="{cls}"><td class="nm">{esc(name)}</td><td>{fa(s["n"])}</td><td>{fa(s["wins"])}</td>'
            f'<td>{fa(wr, 0, pct=True)}</td><td class="{"neg" if s["R"] < 0 else "pos"}">{fa(s["R"], 1, sign=True)}</td>'
            f'<td class="{"neg" if s["usd"] < 0 else "pos"}">{fa(s["usd"], 0, sign=True)}</td>'
            f'<td class="{"neg" if s["ret"] < 0 else "pos"}">{fa(s["ret"], 2, sign=True, pct=True)}</td>'
            f'<td>{fa(s["dd"], 1, pct=True)}</td><td class="note">{note}</td></tr>')


SCEN = "".join([
    scen_row("لایو واقعی (هیستوری متاتریدر)", S_LIVE, "۱۴ آگوست تا ۲۹ سپتامبر", "hl"),
    scen_row("بکتست عین لایو — با روش فعلیِ بکتستر", S["A_backtester_like"], "همان عددی که بکتستر شما نشان می‌دهد"),
    scen_row("＋ کندل ورود واقع‌بینانه", S["F_pess_entry"], "فقط یک فرض عوض شد"),
    scen_row("＋ اسپرد واقعی (Bid/Ask)", S["G_pess_spread"], "بدون کمیسیون، مثل حساب دمو"),
    scen_row("＋ خاموشی‌های ربات = بکتست واقع‌بینانه", S["H_pess_spread_down"], "نزدیک‌ترین به لایو", "hl2"),
    scen_row("بکتستر کلاسیک run_backtest.py (بدون تغییر)", S_CL, f"فقط {fa(n_cl_live)} معامله‌اش با لایو یکی بود"),
])

TWO = "".join(
    f'<tr class="{"hl" if k is False else ""}"><td class="nm">{esc(v["label"])}</td><td>{fa(v["n"])}</td><td>{fa(v["wr"], 1, pct=True)}</td>'
    f'<td class="{"neg" if v["R"] < 0 else "pos"}">{fa(v["R"], 0, sign=True)}</td>'
    f'<td class="{"neg" if v["ret"] < 0 else "pos"}">{fa(v["ret"], 1, sign=True, pct=True)}</td>'
    f'<td>{fa(v["dd"], 1, pct=True)}</td><td>{fa(v["neg"])} از {fa(v["months"])}</td></tr>'
    for k, v in two.items())

PERSYM = two[False]["per_sym"][["count", "sum"]].rename(columns={"count": "n", "sum": "orig"})
PERSYM["mid"] = two["mid"]["per_sym"]["sum"]
PERSYM_HTML = "".join(
    f'<tr><td class="nm">{s}</td><td>{fa(int(r.n))}</td><td class="{"neg" if r.orig < 0 else "pos"}">{fa(r.orig, 1, sign=True)}</td>'
    f'<td class="{"neg" if r.mid < 0 else "pos"}">{fa(r.mid, 1, sign=True)}</td></tr>'
    for s, r in PERSYM.sort_values("orig", ascending=False).iterrows())


def txt(v):
    return "—" if v is None or (isinstance(v, float) and pd.isna(v)) else v


def trow(r):
    st = r["وضعیت"]
    badge = {"هر دو": '<span class="b ok">هر دو</span>', "فقط بکتست": '<span class="b warn">فقط بکتست</span>',
             "فقط لایو": '<span class="b bad">فقط لایو</span>'}[st]
    t = pd.Timestamp(r["زمان پر شدن (سرور)"])
    d = digits(r["نماد"])

    def rr(x):
        if x is None or pd.isna(x):
            return "—"
        return f'<span class="{"neg" if x < 0 else "pos"}">{fa(x, 2, sign=True)}</span>'
    mism = r["توضیح اختلاف"]
    return (f'<tr class="{"mm" if mism else ""}"><td>{badge}</td><td class="nm">{r["نماد"]}</td><td>{r["جهت"]}</td>'
            f'<td>{fa(t.strftime("%m/%d %H:%M"))}</td><td class="num">{fa(r["ورود"], d)}</td>'
            f'<td>{fa(r["فاصله‌ی استاپ (پیپ)"], 1)}</td>'
            f'<td>{esc(txt(r["نتیجه‌ی لایو"]))}</td><td>{rr(r["R لایو"])}</td>'
            f'<td>{esc(txt(r["نتیجه‌ی بکتست (روش فعلی)"]))}</td><td>{rr(r["R بکتست (روش فعلی)"])}</td>'
            f'<td>{rr(r["R بکتست واقع‌بینانه"])}</td><td class="note">{esc(mism)}</td></tr>')


TRADES_HTML = "".join(trow(r) for _, r in TT.iterrows())

# ---------------------------------------------------------------- ایرادها
BUGS = [
    # (گروه، شدت، عنوان، چه شد، مدرک، اثر، راه‌حل)
    ("بکتستر", "خیلی بالا", "فرض خوش‌بینانه در «کندل ورود»",
     "وقتی سفارش لیمیت داخل یک کندل ۴ساعته پر می‌شود، بکتستر فرض می‌کند سقف/کفِ همان کندل «بعد از» پر شدن اتفاق افتاده؛ پس سیو سودِ 2R یا حتی تارگت را همان‌جا می‌دهد. در واقعیت معمولاً برعکس است: کندلی که پایین می‌آید تا به زون خرید برسد، سقفش را اول کندل زده.",
     f"روی ۳۳ معامله‌ی مشترک با لایو، روش فعلی فقط {fa(AG_A[1])} مورد را درست پیش‌بینی کرد (بکتست {fa(AG_A[3], 1, sign=True, suffix=RS)} در برابر لایو {fa(AG_A[2], 1, sign=True, suffix=RS)}). روش واقع‌بینانه {fa(AG_F[1])} از {fa(AG_F[0])} را درست گفت. در ۲ سال دیتا، {fa(n_same_bar)} معامله از {fa(two[False]['n'])} (بیش از نصف) داخل همان کندل ورود بسته شده‌اند.",
     f"بزرگ‌ترین علت اختلاف: حدود {fa(S['F_pess_entry']['R'] - S['A_backtester_like']['R'], 1, suffix=RS)} در همین ۶ هفته. روی ۲ سال: بکتست فعلی {fa(two[False]['ret'], 1, sign=True, pct=True)} ولی با اصلاح این یک فرض {fa(two['mid']['ret'], 1, sign=True, pct=True)} تا {fa(two[True]['ret'], 1, sign=True, pct=True)}.",
     "در کندل ورود، سیو سود/تارگت را فقط وقتی قبول کن که «کلوز» کندل آن را تأیید کند (یا از رنگ کندل مسیر را حدس بزن). بهتر از آن: دیتای M1 یا M5 بگیر تا ترتیب واقعی معلوم شود. ابزار make_rb_pess.py همین گزینه را (PESS_ENTRY_BAR) به بکتستر اضافه می‌کند."),
    ("بکتستر", "بالا", "M15 در حالت «سیو سود» اصلاً استفاده نمی‌شود",
     "کد رفع ابهام با M15 (resolve_entry_candle_m15 و resolve_both_hit_m15) فقط وقتی اجرا می‌شود که manage_mode برابر \"none\" باشد. حالت انتخابی شما «partial2» است؛ یعنی حتی اگر دیتای M15 هم بدهید، کندل ورود باز هم خوش‌بینانه حساب می‌شود.",
     "run_backtest.py: شرط if manage_mode == \"none\" در بخش پر شدن و در process_pos_candle.",
     "اطمینان کاذب: روشن کردن USE_M15 مشکل را حل نمی‌کرد.",
     "منطق M15/M1 را برای همه‌ی حالت‌های مدیریت (سیو سود، ریسک‌فری) پیاده کن."),
    ("بکتستر", "بالا", "بکتستر کلاسیک همان ربات لایو نیست",
     "ربات لایو هر ۴ ساعت کل استراتژی را روی یک پنجره‌ی لغزان (۲۰۰۰ کندل) «از نو» بازپخش می‌کند و هر نماد را جدا (بدون سقف کل حساب) شبیه‌سازی می‌کند؛ ولی بکتستر کلاسیک یک بار پیوسته جلو می‌رود، زون‌های لمس‌نشده را در تاریخچه مسلح می‌کند و سقف ۸ را اعمال می‌کند. حافظه‌ی زون‌ها (کدام زون مصرف شده) در این دو فرق دارد. همچنین در بکتستر کلاسیک زونی که در همین کندل لمس شده، در همین کندل سفارش می‌گیرد و پر می‌شود — کاری که لایو (اگر از قبل مسلح نبوده) نمی‌تواند.",
     f"در همین ۶ هفته فقط {fa(n_cl_live)} از {fa(len(live))} معامله‌ی لایو در بکتستر کلاسیک وجود داشت؛ ولی شبیه‌ساز «عین لایو» هر {fa(n_live_in_emu)} معامله را بازتولید کرد. «پایش هفتگی» شما هم به همین دلیل ~۵۰٪ ناهمخوانی می‌دید.",
     "هر نتیجه‌ای که از بکتستر کلاسیک گرفته شده، رفتار واقعی ربات را نشان نمی‌دهد.",
     "بکتست رسمی را به روش «عین لایو» (walk-forward) انجام بده — ابزار precompute_states.py + emulate.py دقیقاً همین است — یا ربات لایو را طوری بازنویسی کن که وضعیت زون‌ها را پیوسته نگه دارد نه اینکه هر بار بازپخش کند."),
    ("بکتستر", "متوسط", "دیتای فقط Bid و مدل هزینه‌ی نادرست",
     "دیتا فقط قیمت Bid است. سفارش خرید لیمیت وقتی پر می‌شود که Ask برسد؛ حد ضرر/سود فروش با Ask اجرا می‌شود. بکتستر به‌جای مدل Bid/Ask، هر معامله را ۰٫۵ اسپرد «کمیسیون» کم می‌کند. جهش‌های لحظه‌ای ساعت رول‌اوور (۰۰:۰۰) هم در دیتای Bid «پر شدن خیالی» می‌سازد.",
     "NZDCAD ۱۵ سپتامبر ساعت ۰۰: کف Bid ۲۶ پیپ زیر ورود رفت ولی سفارش واقعی پر نشد؛ CHFJPY و AUDUSD هم فقط ۲ پیپ از ورود گذشتند و در لایو پر نشدند.",
     "۳ معامله‌ی «فقط بکتست» در همین بازه از همین‌جا آمده‌اند.",
     "اسپرد را به‌صورت Bid/Ask مدل کن و در ساعت رول‌اوور (حدود ۲۳:۵۵ تا ۰۰:۱۰ سرور) پر شدن را قبول نکن."),
    ("ربات لایو", "بالا", "باگ «سیو سود»: ۹ بار نصف کردن یک پوزیشن",
     "در روزهای ۱۵ تا ۲۱ آگوست، متاتریدر برای هر دستور کد 0 برمی‌گرداند (در حالی که دستور انجام می‌شد). ربات فقط کد 10009 را موفق حساب می‌کند؛ پس فکر کرد سیو سود انجام نشد و هر ۳۰ ثانیه دوباره نصف کرد.",
     "پوزیشن GBPJPY (۱۹ آگوست ۰۸:۳۴ تا ۰۸:۳۹): ۳٫۶۶ لات → ۱٫۸۳ → ۰٫۹۱ → … → ۰٫۰۱ لات. فقط ۰٫۰۱ لات به تارگت رسید.",
     "حدود ۲۵۰ دلار (نزدیک نیم R) سود از دست رفت؛ اگر قیمت برعکس می‌شد، خطرناک‌تر هم بود (پوزیشن بی‌قاعده کوچک می‌شد).",
     "بعد از order_send، به کد برگشتی اکتفا نکن: با positions_get حجم فعلی پوزیشن را بخوان؛ اگر کم شده، «انجام شد» ثبت کن. حجم اولیه‌ی هر تیکت را ذخیره کن و هیچ‌وقت بیش از یک بار نصف نکن."),
    ("ربات لایو", "بالا", "شماره‌ی زون ناپایدار ← سفارش تکراری و زون جامانده",
     "شناسه‌ی زون (مثل USDCHF_H4_00347) از روی «شماره‌ی ترتیب» در پنجره‌ی ۲۰۰۰ کندلی ساخته می‌شود. وقتی پنجره جلو می‌رود و زون قدیمی بیرون می‌افتد، شماره‌ی همه‌ی زون‌ها یکی جابه‌جا می‌شود. ربات سفارش‌ها را با همین کامنت تطبیق می‌دهد؛ پس گاهی سفارش زون الف را به‌جای زون ب نگه می‌دارد و برای زون الف یک سفارش دوم هم می‌گذارد.",
     f"در {fa(n_dup_sync)} همگام‌سازی، روی حساب دو سفارش کاملاً یکسان بود (USDCHF 0.81217 دو بار؛ AUDUSD 0.72575 دو بار) و سفارش زون درست (0.81109 و 0.72222) وجود نداشت. کامنت XAUUSD_H4_00367 روی سه معامله‌ی کاملاً متفاوت (4338، 4625 و 4369) آمده است.",
     "خطر دو برابر شدن ریسک روی یک زون + جا ماندن زون دیگر. در این دوره شانس آوردید و هر دو سفارش تکراری پر نشدند.",
     "شناسه‌ی پایدار بساز (مثلاً جهت + زمان تولد زون + پراکسیمال/دیستال) و سفارش‌ها را با آن یا با قیمت ورود/استاپ تطبیق بده."),
    ("ربات لایو", "بالا", "خاموشی ربات در ساعات باز بازار",
     "دو بار ربات وسط هفته از کار افتاد: ۲۴ آگوست ۱۰:۴۷ تا ۲۳:۲۹ (به وقت سرور، ۱۲٫۷ ساعت، بی‌صدا — نگهبان هم چیزی گزارش نکرد) و ۲۷ آگوست ۲۳:۲۵ تا دوشنبه ۳۱ آگوست (کل جمعه ۲۸ آگوست). در دومی نگهبان ۴۶۴ بار تلاش کرد ربات را بالا بیاورد و هر بار خطای «WinError 87» گرفت.",
     "فایل نگهبان.txt و فاصله‌ی لاگ‌ها؛ در متاتریدر هیچ سفارشی در ساعت‌های ۱۲، ۱۶ و ۲۰ روز ۲۴ آگوست و کل روز ۲۸ آگوست ثبت نشد.",
     f"یک معامله‌ی برنده‌ی بکتست (AUDJPY خرید 114.445، ⁦+2.4R⁩) از دست رفت و سفارش‌های کهنه روی حساب ماندند. در مجموع حدود {fa(S['H_pess_spread_down']['R'] - S['G_pess_spread']['R'], 1, suffix=RS)}.",
     "ربات را به‌صورت سرویس ویندوز یا Task Scheduler با «ری‌استارت خودکار» اجرا کن؛ خطای WinError 87 در کد نگهبان (پارامتر اشتباه در ساختن پروسه) را درست کن؛ اگر تا ۵ دقیقه بعد از هر کندل ۴ساعته همگام‌سازی انجام نشد، از بله هشدار بده."),
    ("ربات لایو", "متوسط", "طلا ساعت ۰۰:۰۰ (بازار بسته) و خطای «No prices»",
     "بازار طلا از ۰۰:۰۰ تا ۰۱:۰۰ سرور بسته است ولی ربات ساعت ۰۰ همه‌ی نمادها را همگام می‌کند. لغو/جایگزینی سفارش طلا شکست می‌خورد و سفارش قدیمی (با حجم سشن قبلی) می‌ماند و می‌تواند در ثانیه‌های اول ساعت ۰۱ پر شود، قبل از اینکه همگام‌سازی ۰۱:۰۰ آن را درست کند.",
     "۳۶ خطای «No prices» برای طلا. پوزیشن طلای ۱۹ آگوست ساعت ۰۱:۰۰:۲۱ با ۰٫۰۲ لات (ریسک ۱۸۶ دلار به‌جای حدود ۴۳۰) پر شد، در حالی که همگام‌سازی ساعت ۰۰ گفته بود «روند ناهم‌جهت».",
     "حجم اشتباه و ورودهایی که استراتژی در آن لحظه نمی‌خواست (این بار به‌طور اتفاقی سودده شد).",
     "برای هر نماد ساعت معاملاتی‌اش را چک کن (symbol_info / sessions) و وقتی بازارش بسته است به سفارش‌هایش دست نزن؛ یا سفارش‌های طلا را قبل از بسته شدن بازار جمع کن."),
    ("ربات لایو", "متوسط", "لغو و ثبت دوباره‌ی همه‌ی سفارش‌ها هر ۴ ساعت",
     f"چون وزن ریسک هر سشن فرق دارد، تقریباً در هر همگام‌سازی همه‌ی سفارش‌ها لغو و با حجم تازه دوباره گذاشته می‌شوند ({fa(n_orders_total)} سفارش در ۶ هفته). هر بار چند ثانیه سفارشی روی حساب نیست و در ساعت ۰۰ (رول‌اوور) خطای «No prices» می‌گیرد.",
     "بخش Orders هیستوری متاتریدر؛ خطاهای No prices برای GBPNZD، AUDJPY و GBPJPY در ساعت ۰۰.",
     "ریسک جا ماندن از ورود در همان چند ثانیه، شلوغی و فشار روی سرور بروکر (در حساب واقعی ممکن است محدودیت درخواست داشته باشد).",
     "یا وزن‌دهی سشن را حذف کن (آزمونش روی بکتستر معیوب انجام شده بود) یا فقط وقتی حجم واقعاً باید تغییر کند و بیرون از ساعت رول‌اوور جایگزین کن."),
    ("ربات لایو", "کم", "فیلترِ یک کندل عقب‌تر برای سفارش‌های «زون لمس‌شده»",
     "در بازپخش، سفارش‌های pending با فیلترهای کندل ماقبل آخر تأیید می‌شوند؛ اگر آخرین کندل فیلتر را قرمز کند، ربات تا ۴ ساعت بعد سفارش را روی حساب نگه می‌دارد، در حالی که بکتستر همان اول کندل لغوش می‌کند.",
     "run_backtest.py، بخش return_state: فیلترهای «armed» از آخرین کندل، ولی «pending» از کندل قبل.",
     "در این دوره اثرش کم بود (حدود ۱R، مخلوط).",
     "در replay_state اگر «دلیل_نبود» سبز نبود، pending را هم کنار بگذار."),
    ("ربات لایو", "کم", "کدهای برگشتی و متن لاگ",
     "در روزهای ۱۵–۲۱ آگوست همه‌ی سفارش‌های موفق به‌صورت «❌ رد شد | کد 0 | Done» ثبت شدند و «عمر سفارش» در لاگ ۳ ساعت کمتر از واقع نشان داده می‌شود (ساعت سرور با UTC قاطی شده).",
     "لاگ ۱۵ تا ۲۱ آگوست (بیش از ۴۰۰ پیام «کد 0»).",
     "لاگ گمراه‌کننده؛ عیب‌یابی سخت می‌شود.",
     "نتیجه‌ی هر دستور را با خواندن دوباره‌ی وضعیت حساب تأیید کن؛ برای عمر سفارش از time_setup_msc و اختلاف ساعت سرور استفاده کن."),
    ("امنیت", "بالا", "توکن ربات «بله» داخل کد و روی گیت‌هاب",
     "BALE_TOKEN مستقیم در live_trader.py نوشته شده و در مخزن گیت‌هاب است.",
     "live_trader.py خط ۸۹.",
     "هر کسی به مخزن دسترسی داشته باشد می‌تواند از طرف ربات پیام بدهد یا پیام‌هایش را بخواند.",
     "توکن را در بله باطل و عوض کن و از متغیر محیطی یا فایل تنظیمات بیرون از گیت بخوان."),
    ("استراتژی", "بالا", "استاپ‌های خیلی کوچک و حجم‌های خیلی بزرگ",
     "فیلتر حداقل اندازه‌ی زون خاموش است. بعضی معاملات استاپ ۳ تا ۶ پیپی داشتند (USDCHF با ۳٫۲ پیپ و ۱۳٫۲ لات، NZDCAD با ۵٫۹ پیپ و ۱۴٫۴ لات). اسپرد ۱–۲ پیپی یعنی بخش بزرگی از ریسک فقط هزینه است.",
     "۹ معامله‌ی لایو با استاپ کمتر از ۱۰ پیپ: فقط ۲ برد، ⁦−3.95R⁩. در بکتست ۲ساله (واقع‌بینانه) معاملاتی که استاپشان کمتر از ۴ برابر اسپرد بود میانگین ⁦−0.43R⁩ داشتند.",
     "در حساب واقعی با کمیسیون (~۷ دلار در هر لات) یک معامله‌ی ۱۳ لاتی حدود ۹۰ دلار (≈۰٫۲R) فقط کمیسیون می‌دهد.",
     "حداقل فاصله‌ی استاپ را نسبت به اسپرد یا ATR ببند (مثلاً ≥ ۸–۱۰ برابر اسپرد) — ولی فقط بعد از اصلاح بکتستر آن را آزمایش کن."),
    ("استراتژی", "بالا", "تایم‌فریم H4 برای این اندازه‌ی زون خیلی درشت است",
     "زون‌ها از کندل‌های کوچک ساخته می‌شوند و ورود وسط زون است؛ پس فاصله‌ی ورود تا استاپ و تارگت اغلب کوچک‌تر از طول یک کندل ۴ساعته است.",
     f"در ۲ سال بکتست، {fa(n_same_bar)} از {fa(two[False]['n'])} معامله همان کندل ورود بسته شده‌اند؛ یعنی نتیجه‌ی بیش از نیمی از معاملات با دیتای H4 «قابل دانستن نیست».",
     "هر نتیجه‌ای از بکتست H4 این استراتژی عملاً حدس است.",
     "یا بکتست را با M1/M5 انجام بده، یا طراحی را عوض کن (زون‌های بزرگ‌تر، ورود روی پراکسیمال، تایم‌فریم بالاتر برای زون)."),
]
SEV = {"خیلی بالا": "sev4", "بالا": "sev3", "متوسط": "sev2", "کم": "sev1"}


def bug_cards(group):
    out = []
    i = 0
    for g, sev, title, what, ev, eff, fix in BUGS:
        if g != group:
            continue
        i += 1
        out.append(f'''<details class="bug" {'open' if sev in ('خیلی بالا',) else ''}>
<summary><span class="sev {SEV[sev]}">{sev}</span><span class="bt">{esc(title)}</span></summary>
<dl><dt>چه شد؟</dt><dd>{esc(what)}</dd><dt>مدرک</dt><dd>{esc(ev)}</dd>
<dt>اثر</dt><dd>{esc(eff)}</dd><dt>راه‌حل</dt><dd>{esc(fix)}</dd></dl></details>''')
    return "".join(out)


# ---------------------------------------------------------------- HTML
sA, sH = S["A_backtester_like"], S["H_pess_spread_down"]
HTML = f"""<!doctype html>
<html lang="fa" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>مقایسه‌ی لایو و بکتست</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Vazirmatn:wght@400;500;700;800&display=swap" rel="stylesheet">
<style>
:root{{--bg:#f6f7f9;--card:#fff;--ink:#1d2330;--muted:#5d6675;--line:#e3e6eb;--soft:#f0f2f5;
--pos:#0f7b4f;--neg:#c2362b;--live:#d9480f;--bt:#1c64c8;--real:#0e8a6a;--warn:#b7791f;--accent:#3b4bd8;
--sev4:#b4232b;--sev3:#d9480f;--sev2:#b7791f;--sev1:#6b7280}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--bg:#111418;--card:#1a1f26;--ink:#e7eaf0;--muted:#a3abb8;--line:#2c333d;--soft:#222831;
--pos:#3ecf8e;--neg:#ff6b61;--live:#ff8a4c;--bt:#6ea8ff;--real:#3fd0a8;--warn:#f0b35a;--accent:#8c96ff;--sev4:#ff5b61;--sev3:#ff8a4c;--sev2:#f0b35a;--sev1:#9aa3af}}}}
:root[data-theme="dark"]{{--bg:#111418;--card:#1a1f26;--ink:#e7eaf0;--muted:#a3abb8;--line:#2c333d;--soft:#222831;
--pos:#3ecf8e;--neg:#ff6b61;--live:#ff8a4c;--bt:#6ea8ff;--real:#3fd0a8;--warn:#f0b35a;--accent:#8c96ff;--sev4:#ff5b61;--sev3:#ff8a4c;--sev2:#f0b35a;--sev1:#9aa3af}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);font-family:Vazirmatn,Tahoma,"Segoe UI",sans-serif;line-height:1.9;font-size:15.5px}}
main{{max-width:1040px;margin:0 auto;padding:24px 16px 64px}}
h1{{font-size:1.65rem;margin:.2em 0 .1em;font-weight:800;line-height:1.5}}
h2{{font-size:1.25rem;margin:2.2em 0 .6em;font-weight:800;padding-bottom:.3em;border-bottom:2px solid var(--line)}}
h3{{font-size:1.05rem;margin:1.4em 0 .4em}}
p{{margin:.5em 0}}
.sub{{color:var(--muted);font-size:.93rem}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px 18px;margin:12px 0}}
.tldr{{border-right:5px solid var(--accent)}}
.tldr ul{{margin:.3em 0;padding-right:1.2em}} .tldr li{{margin:.35em 0}}
.kpis{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}}
.kpi{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px 16px}}
.kpi .t{{font-weight:700;font-size:.95rem}} .kpi .v{{font-size:1.7rem;font-weight:800;margin:.1em 0}}
.kpi .s{{color:var(--muted);font-size:.86rem;line-height:1.7}}
.kpi.live{{border-top:4px solid var(--live)}} .kpi.bt{{border-top:4px solid var(--bt)}} .kpi.real{{border-top:4px solid var(--real)}}
.pos{{color:var(--pos)}} .neg{{color:var(--neg)}}
.tw{{overflow-x:auto;border:1px solid var(--line);border-radius:12px;background:var(--card)}}
table{{border-collapse:collapse;width:100%;font-size:.88rem}}
th,td{{padding:7px 9px;border-bottom:1px solid var(--line);text-align:center;white-space:nowrap}}
th{{background:var(--soft);font-weight:700;position:sticky;top:0}}
td.nm{{text-align:right;font-weight:600}} td.note{{text-align:right;white-space:normal;min-width:220px;color:var(--muted);font-size:.84rem}}
tr.hl td{{background:color-mix(in srgb,var(--live) 9%,transparent)}} tr.hl2 td{{background:color-mix(in srgb,var(--real) 11%,transparent)}}
tr.mm td{{background:color-mix(in srgb,var(--warn) 9%,transparent)}}
.b{{display:inline-block;padding:0 8px;border-radius:99px;font-size:.78rem;font-weight:700}}
.b.ok{{background:color-mix(in srgb,var(--pos) 16%,transparent);color:var(--pos)}}
.b.warn{{background:color-mix(in srgb,var(--warn) 18%,transparent);color:var(--warn)}}
.b.bad{{background:color-mix(in srgb,var(--neg) 16%,transparent);color:var(--neg)}}
.legend{{display:flex;flex-wrap:wrap;gap:14px;font-size:.88rem;margin:4px 0 6px}}
.legend i{{display:inline-block;width:18px;height:4px;border-radius:2px;vertical-align:middle;margin-left:6px}}
.chartwrap{{overflow-x:auto}} svg.chart{{width:100%;min-width:620px;height:auto;display:block}}
.grid{{stroke:var(--line);stroke-width:1}} .grid.zero{{stroke:var(--muted);stroke-width:1.3}}
.ylab,.xlab{{fill:var(--muted);font-size:12px;font-family:Vazirmatn,Tahoma,sans-serif}}
.endlab{{font-size:12.5px;font-weight:700;font-family:Vazirmatn,Tahoma,sans-serif}}
.ln{{fill:none;stroke-width:2.4;stroke-linejoin:round}}
.s-live{{stroke:var(--live);fill:var(--live)}} .s-bt{{stroke:var(--bt);fill:var(--bt)}} .s-real{{stroke:var(--real);fill:var(--real)}}
path.ln.s-live,path.ln.s-bt,path.ln.s-real{{fill:none}}
.wf{{display:flex;flex-direction:column;gap:8px}}
.wf-row{{display:grid;grid-template-columns:minmax(150px,34%) 1fr 70px;gap:10px;align-items:center;font-size:.9rem}}
.wf-track{{position:relative;height:22px;background:var(--soft);border-radius:6px}}
.wf-zero{{position:absolute;top:-3px;bottom:-3px;width:1.5px;background:var(--muted)}}
.wf-bar{{position:absolute;top:3px;bottom:3px;border-radius:4px}}
.wf-bar.up{{background:var(--pos)}} .wf-bar.down{{background:var(--neg)}} .wf-bar.tot{{background:var(--bt)}}
.wf-val{{font-weight:800;direction:ltr;text-align:left}} .wf-val.up{{color:var(--pos)}} .wf-val.down{{color:var(--neg)}}
.alert{{border:1px solid color-mix(in srgb,var(--neg) 45%,var(--line));background:color-mix(in srgb,var(--neg) 7%,var(--card));border-radius:14px;padding:14px 18px;margin:14px 0}}
.alert b{{color:var(--neg)}}
details.bug{{background:var(--card);border:1px solid var(--line);border-radius:12px;margin:10px 0;padding:0 14px}}
details.bug summary{{cursor:pointer;padding:11px 0;display:flex;gap:10px;align-items:center;list-style:none}}
details.bug summary::-webkit-details-marker{{display:none}}
details.bug summary .bt{{font-weight:700}}
details.bug dl{{margin:0 0 12px}} details.bug dt{{font-weight:700;color:var(--muted);font-size:.85rem;margin-top:.5em}}
details.bug dd{{margin:0 0 .2em}}
.sev{{flex:none;font-size:.75rem;font-weight:800;padding:1px 9px;border-radius:99px;color:#fff}}
.sev4{{background:var(--sev4)}} .sev3{{background:var(--sev3)}} .sev2{{background:var(--sev2)}} .sev1{{background:var(--sev1)}}
ol.plan li{{margin:.55em 0}} ol.plan b{{color:var(--accent)}}
.ex{{background:var(--soft);border-radius:12px;padding:12px 16px;margin:10px 0;font-size:.93rem}}
code{{background:var(--soft);padding:0 5px;border-radius:5px;font-size:.88em;direction:ltr;unicode-bidi:embed}}
.two{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}
footer{{color:var(--muted);font-size:.85rem;margin-top:3em;border-top:1px solid var(--line);padding-top:1em}}
@media (max-width:760px){{.kpis,.two{{grid-template-columns:1fr}} h1{{font-size:1.35rem}} .wf-row{{grid-template-columns:1fr 70px}} .wf-lab{{grid-column:1/-1}}}}
</style></head><body><main>

<h1>مقایسه‌ی لایو و بکتست ربات زون عرضه/تقاضا</h1>
<p class="sub">حساب دمو ۱۱۱۰۷۸۳۳۱ (MetaQuotes-Demo) · لایو از ۱۴ آگوست تا ۲۹ سپتامبر ۲۰۲۶ · ۱۰ نماد · همه‌ی ساعت‌ها به وقت سرور متاتریدر</p>

<div class="card tldr"><h3 style="margin-top:0">خلاصه در چند خط</h3><ul>
<li><b>لایو:</b> {fa(S_LIVE['n'])} معامله، فقط {fa(S_LIVE['wins'])} برد ({fa(S_LIVE['wins']/S_LIVE['n']*100,0,pct=True)})، نتیجه <b class="neg">{fa(S_LIVE['usd'],0,sign=True)} دلار ({fa(S_LIVE['ret'],2,sign=True,pct=True)})</b>، بیشترین افت {fa(S_LIVE['dd'],1,pct=True)}.</li>
<li><b>مغز ربات درست کار کرد:</b> با همان دیتا و همان عمق دید، بکتست «عین لایو» در {fa(n_sync_same)} از {fa(n_sync)} همگام‌سازی دقیقاً همان سفارش‌هایی را خواست که روی حساب بود و <b>هر {fa(n_live_in_emu)} معامله‌ی لایو</b> را با همان ورود/استاپ/تارگت بازتولید کرد.</li>
<li><b>ولی بکتستر با روش فعلی‌اش برای همین ۶ هفته سود نشان می‌دهد</b> ({fa(sA['ret'],2,sign=True,pct=True)}، {fa(sA['wins']/sA['n']*100,0,pct=True)} برد). علت اصلی: بکتستر در «کندل ورود» خوش‌بین است و سیو سود/تارگت‌هایی را می‌دهد که در واقعیت قبل از پر شدن سفارش اتفاق افتاده بودند.</li>
<li>وقتی همین یک فرض درست شود و اسپرد و خاموشی‌های ربات هم حساب شود، بکتست همان بازه <b class="neg">{fa(sH['ret'],2,sign=True,pct=True)}</b> با {fa(sH['wins']/sH['n']*100,0,pct=True)} برد می‌شود — تقریباً همان لایو.</li>
<li><b>هشدار جدی:</b> روی کل ۲ سال دیتای شما، بکتستر فعلی {fa(two[False]['ret'],1,sign=True,pct=True)} نشان می‌دهد ولی با اصلاح همین فرض {fa(two['mid']['ret'],1,sign=True,pct=True)} می‌شود. یعنی سود بکتست‌های قبلی تقریباً کامل از این خطا می‌آمد و لبه‌ی استراتژی فعلاً ثابت نشده است.</li>
<li>ایرادهای اجرایی هم بود: باگ سیو سود (۹ بار نصف کردن)، شماره‌ی زون ناپایدار (سفارش تکراری)، دو خاموشی وسط هفته، طلا در ساعت ۰۰ و استاپ‌های ۳ تا ۶ پیپی.</li>
</ul></div>

<div class="kpis">
<div class="kpi live"><div class="t">لایو واقعی</div><div class="v neg">{fa(S_LIVE['ret'],2,sign=True,pct=True)}</div>
<div class="s">{fa(S_LIVE['n'])} معامله · {fa(S_LIVE['wins'])} برد · {fa(S_LIVE['R'],1,sign=True, suffix=RS)}<br>افت {fa(S_LIVE['dd'],1,pct=True)} · {fa(S_LIVE['usd'],0,sign=True)} دلار</div></div>
<div class="kpi bt"><div class="t">بکتست با روش فعلی بکتستر</div><div class="v pos">{fa(sA['ret'],2,sign=True,pct=True)}</div>
<div class="s">{fa(sA['n'])} معامله · {fa(sA['wins'])} برد · {fa(sA['R'],1,sign=True, suffix=RS)}<br>افت {fa(sA['dd'],1,pct=True)} · همان دیتا و همان دید ربات</div></div>
<div class="kpi real"><div class="t">بکتست واقع‌بینانه</div><div class="v neg">{fa(sH['ret'],2,sign=True,pct=True)}</div>
<div class="s">{fa(sH['n'])} معامله · {fa(sH['wins'])} برد · {fa(sH['R'],1,sign=True, suffix=RS)}<br>افت {fa(sH['dd'],1,pct=True)} · کندل ورود درست + اسپرد + خاموشی</div></div>
</div>

<div class="card"><div class="legend"><span><i style="background:var(--live)"></i>لایو (بالانس)</span><span><i style="background:var(--bt)"></i>بکتست با روش فعلی</span><span><i style="background:var(--real)"></i>بکتست واقع‌بینانه</span></div>
<div class="chartwrap">{CH1}</div>
<p class="sub">درصد سود/زیان حساب ۱۰۰ هزار دلاری. دیتای چارت‌ها ۲۵ سپتامبر تمام می‌شود؛ یک معامله‌ی USDCHF که آن روز باز شد در لایو ۲۸ سپتامبر با تارگت بسته شد.</p></div>

<h2>۱. کار چطور انجام شد؟ (به زبان ساده)</h2>
<div class="card">
<p>ربات لایو هر ۴ ساعت (با بسته شدن هر کندل H4) کل استراتژی را روی <b>آخرین ۲۰۰۰ کندل ۴ساعته، ۵۰۰ کندل روزانه و ۳۰۰ کندل هفتگیِ بسته‌شده</b> دوباره اجرا می‌کند و از روی نتیجه سفارش‌هایش را می‌چیند. من دقیقاً همین را تکرار کردم:</p>
<ol>
<li>برای هر ۱۸۶ کندل ۴ساعته‌ی دوره‌ی لایو و هر ۱۰ نماد، همان تابع مغز ربات (<code>backtest_one</code>) را روی <b>همان پنجره‌ی دیتایی که ربات در آن لحظه می‌دید</b> اجرا کردم — نه یک کندل بیشتر، نه یک کندل کمتر (کندل در حال شکل‌گیری حذف شد؛ طلا که ساعت ۰۱ باز می‌شود جدا لحاظ شد).</li>
<li>سهمیه‌بندی سفارش‌ها را عین ربات انجام دادم: هر نماد حداکثر ۳ سفارش، کل حساب ۸ سفارش، به ترتیب سبد.</li>
<li>بعد در طول هر کندل، پر شدن سفارش‌ها، حد ضرر، حد سود و سیو سود 2R را شبیه‌سازی کردم و با <b>هیستوری متاتریدر</b> (۳۴ پوزیشن، ۸۴ دیل و {fa(n_orders_total)} سفارش لیمیتِ ثبت/لغوشده) مقایسه کردم.</li>
<li>برای اینکه ببینم اختلاف از کجاست، شبیه‌سازی را در چند حالت اجرا کردم (جدول پایین). بکتستر کلاسیک خودتان (<code>run_backtest.py</code> بدون تغییر) را هم روی همین بازه اجرا کردم.</li>
</ol></div>

<h2>۲. نتیجه‌ی کلی سناریوها</h2>
<div class="tw"><table><thead><tr><th>سناریو</th><th>تعداد</th><th>برد</th><th>وین‌ریت</th><th>جمع R</th><th>سود $</th><th>بازده</th><th>بیشترین افت</th><th>توضیح</th></tr></thead>
<tbody>{SCEN}</tbody></table></div>
<p class="sub">«R» یعنی چند برابرِ ریسک: ⁦−1R⁩ یعنی خوردن حد ضرر، ⁦+2.5R⁩ یعنی سیو سود در 2R و رسیدن باقی به تارگت 3R. ریسک هر معامله ۰٫۵٪ × ۰٫۸۵ × وزن سشن است (همان تنظیمات ربات).</p>

<h2>۳. آیا ربات همان کاری را کرد که استراتژی می‌خواست؟</h2>
<div class="two">
<div class="card"><h3 style="margin-top:0">✅ در تصمیم‌گیری: بله، تقریباً کامل</h3>
<p>در {fa(n_sync_same)} از {fa(n_sync)} همگام‌سازی ({fa(n_sync_same/n_sync*100,0,pct=True)}) سفارش‌های روی حساب دقیقاً همان‌هایی بود که بکتست «عین لایو» می‌خواست؛ در کل {fa(both_orders)} از {fa(emu_orders)} سفارش ({fa(both_orders/emu_orders*100,1,pct=True)}).</p>
<p>هر {fa(n_live_in_emu)} معامله‌ی لایو در بکتست هم هست، با همان قیمت ورود، استاپ و تارگت.</p></div>
<div class="card"><h3 style="margin-top:0">⚠️ ۱۲ همگام‌سازی متفاوت بودند</h3>
<ul style="margin:0;padding-right:1.1em"><li>۷ مورد: ربات خاموش/هنگ بود (۲۴ و ۲۸ آگوست) و سفارش‌های کهنه روی حساب ماند.</li>
<li>۳ مورد: سفارش تکراری روی یک زون و جا ماندن زون دیگر (باگ شماره‌ی زون).</li>
<li>۱ مورد: همگام‌سازی ۴ سپتامبر ساعت ۱۶ سه دقیقه طول کشید؛ چند دقیقه بعد سفارش‌ها دقیقاً یکی بودند.</li>
<li>۱ مورد: ۱۵ سپتامبر ساعت ۰۰ (رول‌اوور) لغو یک سفارش GBPNZD با خطای «No prices» شکست خورد.</li></ul>
<p>بکتستر کلاسیک اما فقط <b>{fa(n_cl_live)} از {fa(len(live))}</b> معامله‌ی لایو را داشت — یعنی بکتستر کلاسیک رفتار واقعی ربات را مدل نمی‌کند.</p></div>
</div>

<h2>۴. چرا بکتست سود نشان می‌داد ولی لایو ضرر کرد؟</h2>
<div class="card">
<p>ریشه‌ی اصلی یک فرض در بکتستر است. بکتستر فقط کندل ۴ساعته را می‌بیند (باز، سقف، کف، بسته). وقتی قیمت داخل یک کندل به نقطه‌ی ورود می‌رسد، بکتستر نمی‌داند سقف کندل <b>قبل</b> از پر شدن بوده یا <b>بعد</b> از آن — و همیشه فرض می‌کند «بعد». پس اگر سقف کندل به 2R رسیده باشد، سیو سود را می‌دهد.</p>
<div class="ex"><b>مثال واقعی — USDCHF فروش ۱ سپتامبر، ورود 0.81217، استاپ 0.81300:</b><br>
کندل ۱۶:۰۰ اول تا 0.8097 پایین رفت و بعد بالا آمد و سفارش فروش را پر کرد. بکتستر فکر کرد اول پر شده و بعد تا تارگت پایین رفته ← <span class="pos">⁦+2.42R⁩</span>. در واقعیت بعد از پر شدن قیمت پایین نیامد و استاپ خورد ← <span class="neg">⁦−1R⁩</span>.</div>
<p>این اتفاق در ۷ معامله از ۳۳ معامله‌ی مشترک افتاد. سهم هر عامل از اختلاف (بر حسب R):</p>
{WF}
<p class="sub">«اسپرد واقعی» مثبت شده چون بکتستر برای هر معامله ۰٫۵ اسپرد کمیسیون کم می‌کند ولی حساب دمو کمیسیون ندارد؛ در عوض اسپرد واقعی باعث شد چند سفارش پر نشود.</p>
<p>آزمون دقیق: روی ۳۳ معامله‌ی مشترک، روش فعلی بکتستر نتیجه‌ی {fa(AG_A[1])} معامله را درست پیش‌بینی کرد؛ روش «کندل ورود واقع‌بینانه» نتیجه‌ی <b>{fa(AG_F[1])}</b> معامله را. پس واقعیت بازار با روش واقع‌بینانه جور است.</p>
</div>

<div class="alert"><b>⚠️ مهم‌ترین نکته‌ی این گزارش:</b> همین خطا در همه‌ی بکتست‌های قبلی هم هست. روی کل ۲ سال دیتایی که داده‌اید (اکتبر ۲۰۲۴ تا سپتامبر ۲۰۲۶، ۱۰ نماد سبد):
<div class="tw" style="margin:10px 0"><table><thead><tr><th>روش حساب کندل ورود</th><th>معامله</th><th>وین‌ریت</th><th>جمع R</th><th>بازده</th><th>بیشترین افت</th><th>ماه‌های منفی</th></tr></thead><tbody>{TWO}</tbody></table></div>
یعنی تقریباً <b>کل سودی که بکتستر نشان می‌دهد از همین فرض می‌آید.</b> حقیقت جایی بین این دو است، ولی ۶ هفته لایو دقیقاً با حالت واقع‌بینانه جور درآمد. تا وقتی بکتست با دیتای ریزتر (M1/M5) تکرار نشده، نمی‌شود گفت این استراتژی سودده است.</div>
<div class="card"><div class="legend"><span><i style="background:var(--bt)"></i>بکتستر فعلی</span><span><i style="background:var(--real)"></i>کندل ورود «میانه»</span><span><i style="background:var(--live)"></i>کندل ورود «بدبینانه»</span></div>
<div class="chartwrap">{CH2}</div>
<p class="sub">رشد حساب در بکتستر کلاسیک (۲ سال، ماهانه). تنها تفاوت سه خط، نحوه‌ی حساب کردن کندلی است که سفارش در آن پر شده.</p></div>

<details class="card"><summary><b>سهم هر نماد در ۲ سال (جمع R)</b></summary>
<div class="tw" style="margin-top:8px"><table><thead><tr><th>نماد</th><th>تعداد</th><th>بکتستر فعلی</th><th>کندل ورود میانه</th></tr></thead><tbody>{PERSYM_HTML}</tbody></table></div>
<p class="sub">با روش واقع‌بینانه هیچ نمادی سودده نمی‌ماند؛ پس حذف/اضافه کردن نماد راه‌حل نیست.</p></details>

<h2>۵. ایرادهای بکتستر</h2>
{bug_cards("بکتستر")}

<h2>۶. ایرادهای اجرایی ربات لایو</h2>
{bug_cards("ربات لایو")}
{bug_cards("امنیت")}

<h2>۷. ایرادهای استراتژی و مدیریت ریسک</h2>
{bug_cards("استراتژی")}
<div class="card"><h3 style="margin-top:0">آیا فقط بدشانسی بود؟</h3>
<p>۸ برد از ۳۴ معامله. اگر ادعای بکتستر فعلی (حدود ۴۶٪ برد) درست بود، شانس چنین نتیجه‌ای فقط حدود <b>۰٫۶٪</b> است. با وین‌ریت بکتست واقع‌بینانه (۲۷ تا ۳۱٪) شانسش حدود <b>۲۵ تا ۴۰٪</b> است — یعنی کاملاً عادی. پس لایو «بدشانس» نبود؛ نتیجه‌ی طبیعی استراتژی با اجرای واقعی بود. ۱۳ ضرر پشت‌سرهم و افت ۶٪ هم با همین تصویر جور است.</p>
<p>نمادهای ضررده‌ی لایو (AUDJPY، USDCHF، CHFJPY، AUDUSD) با ۲ تا ۷ معامله قابل قضاوت نیستند؛ روی این عددها نماد حذف نکنید.</p></div>

<h2>۸. پیشنهادها (به ترتیب اولویت)</h2>
<div class="card"><ol class="plan">
<li><b>فعلاً حساب واقعی نه.</b> ربات را روی دمو نگه دارید، ولی فقط برای تست اجرایی؛ تا اصلاح بکتستر و تکرار آزمون، به سود آینده‌اش تکیه نکنید.</li>
<li><b>بکتستر را درست کنید:</b> کندل ورود را حداقل با حالت «میانه» یا «بدبینانه» حساب کنید (گزینه‌ی <code>PESS_ENTRY_BAR</code> در ابزار <code>make_rb_pess.py</code>)، منطق M15 را برای حالت سیو سود هم فعال کنید، و اسپرد را Bid/Ask مدل کنید.</li>
<li><b>دیتای M1 یا M5 بگیرید</b> (همین ۱۰ نماد، چند سال) و بکتست را با ترتیب واقعی حرکت قیمت داخل کندل تکرار کنید. این تنها راه جواب قطعی است.</li>
<li><b>بکتست رسمی را «عین لایو» کنید:</b> ابزار این گزارش (<code>precompute_states.py</code> + <code>emulate.py</code>) دقیقاً همان کاری را می‌کند که ربات می‌کند. «پایش هفتگی» را هم با همین ابزار جایگزین کنید.</li>
<li><b>اگر بعد از اصلاح، استراتژی منفی ماند،</b> طراحی را عوض کنید نه پارامترها را: زون‌های بزرگ‌تر یا از تایم‌فریم بالاتر، ورود روی پراکسیمال یا با تأیید کندلی، حداقل فاصله‌ی استاپ نسبت به اسپرد/ATR. و هر تغییری را فقط روی بکتستر اصلاح‌شده بسنجید (دیتای خارج از نمونه جدا نگه دارید).</li>
<li><b>باگ‌های اجرایی را رفع کنید:</b> تأیید سیو سود با خواندن حجم پوزیشن، شناسه‌ی پایدار زون، اجرای ربات به‌صورت سرویس با ری‌استارت خودکار و هشدار عدم همگام‌سازی، دست نزدن به نمادهایی که بازارشان بسته است.</li>
<li><b>ساده‌سازی:</b> وزن‌دهی سشن باعث لغو و ثبت دوباره‌ی همه‌ی سفارش‌ها هر ۴ ساعت می‌شود و روی بکتستر معیوب انتخاب شده بود؛ یا حذفش کنید یا دوباره روی بکتستر درست آزمایشش کنید.</li>
<li><b>امنیت:</b> توکن بله را همین حالا عوض کنید و از کد بیرون بیاورید.</li>
</ol></div>

<h2>۹. مقایسه‌ی معامله‌به‌معامله</h2>
<p class="sub">ردیف‌های زرد: نتیجه‌ی لایو و بکتست (روش فعلی) فرق داشته. «R واقع‌بینانه» = بکتست با کندل ورود درست + اسپرد + خاموشی‌ها.</p>
<div class="tw"><table><thead><tr><th>وضعیت</th><th>نماد</th><th>جهت</th><th>پر شدن</th><th>ورود</th><th>استاپ (پیپ)</th><th>نتیجه‌ی لایو</th><th>R لایو</th><th>نتیجه‌ی بکتست فعلی</th><th>R بکتست فعلی</th><th>R واقع‌بینانه</th><th>توضیح</th></tr></thead>
<tbody>{TRADES_HTML}</tbody></table></div>

<h2>۱۰. محدودیت‌ها و فایل‌ها</h2>
<div class="card"><ul style="padding-right:1.1em;margin:0">
<li>دیتای چارت‌ها تا ۲۵ سپتامبر است (EURCAD تا ۲۲ سپتامبر، چون کندل آخرش ناقص بود حذف شد). لایو تا ۲۹ سپتامبر ادامه داشت.</li>
<li>دیتا فقط کندل ۴ساعته است؛ ترتیب دقیق حرکت قیمت داخل کندل معلوم نیست. برای همین دو حالت «فعلی» و «واقع‌بینانه» را کنار هم آوردم.</li>
<li>اسپردها از جدول خود <code>run_backtest.py</code> است؛ اسپرد واقعی دمو کمی کمتر و در رول‌اوور خیلی بیشتر است.</li>
<li>کندل‌های روزانه‌ی دیتا از سپتامبر ۲۰۲۴ شروع می‌شوند (ربات ۵۰۰ کندل می‌خواند)؛ چون خود مغز ربات همه‌ی تایم‌فریم‌ها را از شروع پنجره‌ی ۲۰۰۰ کندلی H4 (حدود مه ۲۰۲۵) برش می‌زند، این کمبود روی نتیجه اثری ندارد.</li>
<li>فایل‌ها: <code>جزئیات_مقایسه_لایو_و_بکتست.xlsx</code> (همه‌ی جدول‌ها) و پوشه‌ی <code>ابزار_تحلیل</code> (برای تکرار: <code>python run_all.py</code>).</li>
</ul></div>

<footer>ساخته‌شده با تحلیل هیستوری متاتریدر، لاگ‌های ربات و دیتای «دیتا_هفتگی» · ۳۰ سپتامبر ۲۰۲۶</footer>
</main></body></html>"""

with open(HTML_PATH, "w", encoding="utf-8") as f:
    f.write(HTML)

# ---------------------------------------------------------------- اکسل


def scen_df():
    rows = []
    for name, s in (("لایو واقعی", S_LIVE), ("بکتست عین لایو - روش فعلی بکتستر", S["A_backtester_like"]),
                    ("+ کندل ورود واقع‌بینانه", S["F_pess_entry"]), ("+ اسپرد واقعی", S["G_pess_spread"]),
                    ("+ خاموشی‌ها (واقع‌بینانه)", S["H_pess_spread_down"]), ("بکتستر کلاسیک بدون تغییر", S_CL)):
        rows.append({"سناریو": name, "تعداد": s["n"], "برد": s["wins"], "وین‌ریت٪": round(s["wins"] / s["n"] * 100, 1),
                     "جمع R": round(s["R"], 2), "سود $": round(s["usd"], 0), "بازده٪": round(s["ret"], 2),
                     "بیشترین افت٪": round(s["dd"], 2)})
    return pd.DataFrame(rows)


def emu_trades(name):
    t = emu[name]["trades"].copy()
    t = t.drop(columns=["key"])
    t.columns = ["نماد", "جهت", "زون", "زمان ثبت", "کندل پر شدن", "کندل خروج", "ورود", "استاپ", "تارگت",
                 "قیمت خروج", "علت خروج", "سیو سود", "R", "ریسک $", "سود $", "وزن سشن", "استاپ (پیپ)"]
    return t


lt = live.copy()
lt.columns = [{"position": "پوزیشن", "sym": "نماد", "dir": "جهت", "zone_id": "زون", "placed": "زمان ثبت سفارش",
               "fill_time": "زمان پر شدن", "exit_time": "زمان خروج", "entry": "ورود", "sl": "استاپ", "tp": "تارگت",
               "volume": "حجم", "closed_vol": "حجم بسته‌شده", "n_partial_deals": "تعداد دیل سیو سود", "why": "علت خروج",
               "R_price": "R", "profit": "سود $", "risk_usd": "ریسک $", "risk_pips": "استاپ (پیپ)"}.get(c, c) for c in lt.columns]
d2 = dec.copy()
d2["only_emu_keys"] = d2["only_emu_keys"].astype(str)
d2["only_live_keys"] = d2["only_live_keys"].astype(str)
d2.columns = ["کندل (سرور)", "لحظه‌ی مقایسه", "سفارش بکتست", "سفارش لایو", "مشترک", "فقط بکتست", "فقط لایو",
              "تکراری در لایو", "کلیدهای فقط بکتست", "کلیدهای فقط لایو"]
two_df = pd.DataFrame([{"روش": v["label"], "تعداد": v["n"], "وین‌ریت٪": round(v["wr"], 1), "جمع R": round(v["R"], 1),
                        "بازده٪": round(v["ret"], 1), "بیشترین افت٪": round(v["dd"], 1), "ماه منفی": v["neg"],
                        "کل ماه": v["months"]} for v in two.values()])
ps = PERSYM.reset_index().rename(columns={"نماد": "نماد", "n": "تعداد", "orig": "جمع R بکتستر فعلی", "mid": "جمع R کندل ورود میانه"})
bugs_df = pd.DataFrame(BUGS, columns=["بخش", "شدت", "عنوان", "چه شد", "مدرک", "اثر", "راه‌حل"])
cl = classic["trades"].copy()

with pd.ExcelWriter(XLSX_PATH, engine="openpyxl") as xw:
    scen_df().to_excel(xw, sheet_name="خلاصه_سناریوها", index=False)
    TT.to_excel(xw, sheet_name="معامله_به_معامله", index=False)
    lt.to_excel(xw, sheet_name="معاملات_لایو", index=False)
    emu_trades("A_backtester_like").to_excel(xw, sheet_name="بکتست_روش_فعلی", index=False)
    emu_trades("H_pess_spread_down").to_excel(xw, sheet_name="بکتست_واقع_بینانه", index=False)
    cl[["نماد", "جهت", "ZoneID", "زمان_ورود", "زمان_خروج", "ورود", "حدضرر", "حدسود", "علت_خروج", "نتیجه_R"]].to_excel(
        xw, sheet_name="بکتستر_کلاسیک", index=False)
    d2.to_excel(xw, sheet_name="تطبیق_تصمیم_ها", index=False)
    two_df.to_excel(xw, sheet_name="دو_سال_بکتستر", index=False)
    ps.to_excel(xw, sheet_name="دو_سال_هر_نماد", index=False)
    bugs_df.to_excel(xw, sheet_name="ایرادها_و_راه_حل", index=False)
    for ws in xw.book.worksheets:
        ws.sheet_view.rightToLeft = True
        for col in ws.columns:
            width = max(len(str(c.value)) if c.value is not None else 0 for c in col[:200])
            ws.column_dimensions[col[0].column_letter].width = min(max(10, width * 1.1), 60)

print("HTML:", HTML_PATH)
print("XLSX:", XLSX_PATH)
