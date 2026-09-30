# -*- coding: utf-8 -*-
"""تبدیل ReportHistory متاتریدر به جدول‌های تمیز: پوزیشن‌ها، سفارش‌ها، دیل‌ها."""
import os, warnings
import openpyxl
import pandas as pd

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))          # پوشه‌ی اصلی پروژه
CACHE = os.path.join(HERE, "_cache")                     # خروجی‌های میانی
os.makedirs(CACHE, exist_ok=True)


def _t(s):
    return pd.to_datetime(s, format="%Y.%m.%d %H:%M:%S") if s else pd.NaT


def parse():
    wb = openpyxl.load_workbook(os.path.join(REPO, "ReportHistory-111078331.xlsx"))
    rows = list(wb.worksheets[0].iter_rows(values_only=True))
    idx = {r[0]: i for i, r in enumerate(rows) if r[0] in ("Positions", "Orders", "Deals", "Working Orders", "Balance:")}

    pos = []
    for r in rows[idx["Positions"] + 2: idx["Orders"]]:
        if not r[0]:
            continue
        pos.append(dict(open_time=_t(r[0]), position=int(r[1]), symbol=r[2], side=r[3].upper(),
                        volume=float(r[4]), entry=float(r[5]), sl=float(r[6]), tp=float(r[7]),
                        close_time=_t(r[8]), close_price=float(r[9]), commission=float(r[10]),
                        swap=float(r[11]), profit=float(r[12])))
    orders = []
    for r in rows[idx["Orders"] + 2: idx["Deals"]]:
        if not r[0]:
            continue
        orders.append(dict(open_time=_t(r[0]), order=int(r[1]), symbol=r[2], type=r[3],
                           volume=float(str(r[4]).split("/")[0]), price=r[5], sl=r[6], tp=r[7],
                           close_time=_t(r[8]), state=r[9], comment=r[11]))
    deals = []
    for r in rows[idx["Deals"] + 2: idx["Working Orders"]]:
        if not r[0] or not isinstance(r[1], int):
            continue
        deals.append(dict(time=_t(r[0]), deal=int(r[1]), symbol=r[2], type=r[3], direction=r[4],
                          volume=float(r[5]) if r[5] else None, price=r[6], order=r[7],
                          commission=r[8], fee=r[9], swap=r[10], profit=r[11], balance=r[12],
                          comment=r[13]))
    working = []
    for r in rows[idx["Working Orders"] + 2: idx["Balance:"]]:
        if not r[0]:
            continue
        working.append(dict(open_time=_t(r[0]), order=int(r[1]), symbol=r[2], type=r[3],
                            price=r[5], sl=r[6], tp=r[7], comment=r[11]))
    return (pd.DataFrame(pos), pd.DataFrame(orders), pd.DataFrame(deals), pd.DataFrame(working))


if __name__ == "__main__":
    pos, orders, deals, working = parse()
    for n, df in (("live_positions", pos), ("live_orders", orders), ("live_deals", deals), ("live_working", working)):
        df.to_pickle(os.path.join(CACHE, n + ".pkl"))
        print(n, len(df))
    lim = orders[orders["type"].str.contains("limit")]
    print(lim["state"].value_counts())
    print("first order", orders["open_time"].min(), "last", orders["open_time"].max())
    # خوشه‌های ثبت سفارش = زمان همگام‌سازی‌ها
    lim = lim.sort_values("open_time")
    print(lim["open_time"].dt.floor("h").value_counts().sort_index().head(30))
