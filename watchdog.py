# -*- coding: utf-8 -*-
"""نگهبان ربات — اگر ربات از کار افتاد یا گیر کرد، دوباره راه‌اندازی‌اش می‌کند و در بله خبر می‌دهد.

اجرا:  install_autostart.bat را یک بار با «Run as administrator» اجرا کن. از آن به بعد نگهبان
       بدون پنجره اجرا می‌شود: با هر ورود به ویندوز، و هر ۵ دقیقه یک بار اگر بسته شده باشد.
       (start_watchdog.bat فقط برای اجرای دستی با پنجره است.)

چه می‌کند (هر ۱ دقیقه):
  - ربات هر ۳۰ ثانیه فایل logs/heartbeat.txt را به‌روز می‌کند. اگر این فایل کهنه شد:
      · پروسه‌ی ربات زنده ولی گیر کرده (۱۰ دقیقه بی‌ضربان) → بسته می‌شود تا start_robot.bat بالایش بیاورد
      · پروسه‌ی ربات مرده (۳ دقیقه بی‌ضربان) → start_robot.bat در پنجره‌ی جدید اجرا می‌شود
  - اگر بازار باز است و بیش از ۴ ساعت و ربع همگام‌سازی انجام نشده → هشدار در بله
  - اگر ربات عمداً خاموش شده (Ctrl+C یا stop_robot.bat) → دست نمی‌زند
  - هر بار ربات از کار بیفتد، دلیلش را پیدا و در بله گزارش می‌کند: دلیلی که خود ربات قبل از
    بسته شدن نوشته (کرش، بستن پنجره، Sign out)، ری‌استارت ویندوز، و رویدادهای ثبت‌شده‌ی ویندوز
    (آپدیت، خاموشی ناگهانی، Sign out، کرش برنامه)
نگهبان قبلی با خطای «WinError 87» نمی‌توانست ربات را بالا بیاورد؛ این نسخه با os.startfile
(همان دابل‌کلیک) اجرا می‌کند.
"""

import os
import sys
import json
import time
import datetime as dt
import subprocess
import urllib.request

# ================== تنظیمات ==================
CHECK_SECONDS = 60          # هر چند ثانیه وضعیت را چک کند
HUNG_MINUTES = 10           # ربات زنده ولی این‌قدر بی‌ضربان → گیر کرده → بسته و دوباره اجرا می‌شود
DEAD_MINUTES = 3            # ربات مرده و این‌قدر بی‌ضربان → دوباره اجرا می‌شود
RESTART_WAIT_MINUTES = 4    # بعد از هر تلاش راه‌اندازی، این‌قدر صبر تا ربات بالا بیاید
SYNC_ALERT_HOURS = 4.25     # بازار باز ولی این‌قدر همگام‌سازی نشده → هشدار
REMIND_MINUTES = 30         # تا مشکل حل نشده، هر چند دقیقه یادآوری در بله
# =============================================

HERE = os.path.dirname(os.path.abspath(__file__))
LOGS = os.path.join(HERE, "logs")
BOT_BAT = os.path.join(HERE, "start_robot.bat")
HEARTBEAT = os.path.join(LOGS, "heartbeat.txt")
PID_FILE = os.path.join(LOGS, "robot.pid")
STOP_FLAG = os.path.join(LOGS, "robot_stopped.flag")
LAST_SYNC = os.path.join(LOGS, "last_sync.txt")
LOG_FILE = os.path.join(LOGS, "نگهبان.txt")
EXIT_FILE = os.path.join(LOGS, "last_exit.json")
CRASH_FILE = os.path.join(LOGS, "crash_dump.txt")
REPORTED_FILE = os.path.join(LOGS, "last_down_report.txt")
EXIT_NO_RESTART = 3
TASK_NAME = "ZoneRobot_Watchdog"


def log(msg, bale=False):
    line = f"[{dt.datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    try:
        print(line, flush=True)
    except Exception:
        pass
    try:
        os.makedirs(LOGS, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    if bale:
        bale_send("🛡 نگهبان: " + msg)


# ---------------- بله (همان توکن و چت ربات) ----------------
def _read(path):
    try:
        with open(path, encoding="utf-8-sig") as f:
            return f.read().strip()
    except Exception:
        return ""


def bale_send(text):
    token = os.environ.get("BALE_TOKEN", "").strip() or _read(os.path.join(HERE, "bale_token.txt"))
    chat = _read(os.path.join(LOGS, "bale_chat_id.txt"))
    if not token or not chat:
        return
    try:
        data = json.dumps({"chat_id": chat, "text": text}).encode("utf-8")
        req = urllib.request.Request(f"https://tapi.bale.ai/bot{token}/sendMessage", data=data,
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        try:
            print(f"[بله] ارسال نشد: {e}", flush=True)
        except Exception:
            pass


# ---------------- وضعیت ربات ----------------
def heartbeat_info():
    """(چند دقیقه از آخرین ضربان گذشته, متن وضعیت)"""
    try:
        age = (time.time() - os.path.getmtime(HEARTBEAT)) / 60.0
    except Exception:
        return None, ""
    return age, _read(HEARTBEAT)


def robot_pid():
    try:
        return int(_read(PID_FILE))
    except Exception:
        return None


def pid_alive(pid):
    if not pid:
        return False
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.OpenProcess.restype = wintypes.HANDLE
        k32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        h = k32.OpenProcess(0x1000, False, pid)        # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        try:
            code = wintypes.DWORD()
            ok = k32.GetExitCodeProcess(h, ctypes.byref(code))
            if not (bool(ok) and code.value == 259):    # STILL_ACTIVE
                return False
            # شماره‌ی پروسه ممکن است بعد از بسته شدن ربات به برنامه‌ی دیگری رسیده باشد:
            # فقط اگر واقعاً پایتون است، «ربات» حساب می‌شود (وگرنه ممکن بود برنامه‌ی دیگری بسته شود)
            buf = ctypes.create_unicode_buffer(1024)
            size = wintypes.DWORD(1024)
            if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                return "python" in os.path.basename(buf.value).lower()
            return True
        finally:
            k32.CloseHandle(h)
    try:
        os.kill(pid, 0)                                 # فقط لینوکس/مک (روی ویندوز این پروسه را می‌کشد!)
        return True
    except Exception:
        return False


def kill_pid(pid):
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
    else:
        try:
            os.kill(pid, 9)
        except Exception:
            pass


def start_robot():
    """start_robot.bat را در پنجره‌ی جدید اجرا می‌کند (مثل دابل‌کلیک)."""
    if not os.path.exists(BOT_BAT):
        raise FileNotFoundError(f"start_robot.bat کنار نگهبان نیست: {BOT_BAT}")
    if os.name == "nt":
        os.startfile(BOT_BAT)
    else:
        subprocess.Popen(["sh", BOT_BAT], cwd=HERE)


def minutes_since_sync():
    try:
        t = dt.datetime.fromisoformat(_read(LAST_SYNC))
    except Exception:
        return None
    return (dt.datetime.now() - t).total_seconds() / 60.0


def single_instance():
    if os.name != "nt":
        return True
    try:
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateMutexW.restype = wintypes.HANDLE
        k32.CreateMutexW.argtypes = (wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
        for scope in ("Global", "Local"):
            h = k32.CreateMutexW(None, False, f"{scope}\\ZoneRobotWatchdog")
            if h:
                if ctypes.get_last_error() == 183:
                    return False
                globals()["_MUTEX"] = h
                return True
    except Exception:
        pass
    return True


# ---------------- پیدا کردن دلیل از کار افتادن ربات ----------------
EVENT_NAMES = {
    "1074": "ری‌استارت/خاموش کردن ویندوز توسط یک برنامه یا کاربر (اغلب آپدیت ویندوز)",
    "6006": "ویندوز به‌طور عادی خاموش شد",
    "6008": "ویندوز ناگهانی خاموش شده بود (قطع برق، هنگ یا ری‌ست سخت VPS)",
    "41": "سیستم بدون خاموش شدن درست دوباره روشن شد",
    "1001": "صفحه‌ی آبی ویندوز (BugCheck)",
    "7002": "کاربر از ویندوز خارج شد (Sign out) — همه‌ی برنامه‌ها از جمله ربات بسته می‌شوند",
    "4647": "کاربر Sign out کرد — همه‌ی برنامه‌ها از جمله ربات بسته می‌شوند",
    "1000": "برنامه کرش کرد (Application Error)",
    "1002": "برنامه هنگ کرد و ویندوز آن را بست (Application Hang)",
}


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def last_heartbeat_ts():
    try:
        return os.path.getmtime(HEARTBEAT)
    except Exception:
        return None


def already_reported(since_ts):
    return bool(since_ts) and _read(REPORTED_FILE) == str(int(since_ts))


def mark_reported(since_ts):
    try:
        with open(REPORTED_FILE, "w", encoding="utf-8") as f:
            f.write(str(int(since_ts or 0)))
    except Exception:
        pass


def boot_time():
    """زمان روشن شدن ویندوز (برای فهمیدن ری‌استارت VPS)"""
    if os.name != "nt":
        return None
    try:
        import ctypes
        k32 = ctypes.windll.kernel32
        k32.GetTickCount64.restype = ctypes.c_ulonglong
        return time.time() - k32.GetTickCount64() / 1000.0
    except Exception:
        return None


def _events(log_name, ids, since_ts, max_n=6):
    """رویدادهای ثبت‌شده‌ی ویندوز از کمی قبل از since_ts تا الان (با wevtutil خود ویندوز)."""
    if os.name != "nt":
        return []
    ms = int(max(120, time.time() - since_ts + 300) * 1000)
    q = ("*[System[(" + " or ".join(f"EventID={i}" for i in ids) +
         f") and TimeCreated[timediff(@SystemTime) <= {ms}]]]")
    try:
        r = subprocess.run(["wevtutil", "qe", log_name, f"/q:{q}", "/f:text", "/rd:true", f"/c:{max_n}"],
                           capture_output=True, timeout=30, creationflags=0x08000000)   # بدون پنجره
    except Exception:
        return []
    raw = r.stdout or b""
    try:
        txt = raw.decode("utf-8")
    except UnicodeDecodeError:
        txt = raw.decode("mbcs", "replace")
    out, cur, in_desc = [], None, False
    for line in txt.splitlines():
        t = line.strip()
        if t.startswith("Event["):
            if cur:
                out.append(cur)
            cur, in_desc = {"date": "", "id": "", "desc": ""}, False
        elif cur is None:
            continue
        elif t.startswith("Date:"):
            cur["date"] = t[5:].strip()[:19].replace("T", " ")
        elif t.startswith("Event ID:"):
            cur["id"] = t[9:].strip()
        elif t.startswith("Description:"):
            in_desc, cur["desc"] = True, t[12:].strip()
        elif in_desc and t:
            cur["desc"] = (cur["desc"] + " " + t).strip()
    if cur:
        out.append(cur)
    return out


def diagnose(since_ts):
    """فهرست دلیل‌های احتمالی از کار افتادن ربات بعد از لحظه‌ی since_ts (آخرین ضربان)."""
    found = []
    ex = _read_json(EXIT_FILE)
    if ex and not ex.get("running") and ex.get("reason"):
        d = (ex.get("detail") or "").strip()
        found.append(f"خود ربات قبل از بسته شدن نوشت: {ex['reason']}" + (f" | {d[-300:]}" if d else ""))
    bt = boot_time()
    if bt and since_ts and bt > since_ts - 120:
        found.append(f"ویندوز (VPS) ساعت {dt.datetime.fromtimestamp(bt):%Y-%m-%d %H:%M} دوباره روشن شده — "
                     f"یعنی ری‌استارت شده و همه‌ی برنامه‌ها بسته شده‌اند.")
    for log_name, ids, keys in (("System", (1074, 6006, 6008, 41, 1001, 7002), None),
                                ("Security", (4647,), None),
                                ("Application", (1000, 1002), ("python", "terminal64", "metatrader", "cmd.exe", "conhost"))):
        for e in _events(log_name, ids, since_ts):
            if keys and not any(k in e["desc"].lower() for k in keys):
                continue
            found.append(f"رویداد ویندوز {e['id']} در {e['date']}: {EVENT_NAMES.get(e['id'], '')} | {e['desc'][:220]}")
    try:
        if since_ts and os.path.getmtime(CRASH_FILE) > since_ts - 60:
            tail = _read(CRASH_FILE)[-1500:]
            if "Fatal Python error" in tail or "fatal exception" in tail.lower():
                found.append("کرش شدید داخل پایتون یا کتابخانه‌ی متاتریدر (crash_dump.txt): " + tail[-400:])
    except Exception:
        pass
    if not found:
        found.append("ردی در ویندوز پیدا نشد → به احتمال زیاد پنجره‌ی ربات بسته شده (دکمه‌ی X، End task در "
                     "Task Manager، یا بسته شدن پنجره‌ها هنگام خروج از ریموت) یا پروسه از بیرون بسته شده.")
    return found


# ---------------- ثبت در Task Scheduler ویندوز ----------------
def install_task():
    """نگهبان را در Task Scheduler ثبت می‌کند: با ورود به ویندوز + هر ۵ دقیقه یک بار (اگر بسته شده
    باشد دوباره اجرا می‌شود)، بدون پنجره (pythonw) تا اشتباهی بسته نشود، و بدون سقف زمان اجرا."""
    from xml.sax.saxutils import escape
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.exists(pyw):
        pyw = sys.executable
    user = f"{os.environ.get('USERDOMAIN', '')}\\{os.environ.get('USERNAME', '')}".strip("\\")
    xml = f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>Zone robot watchdog - restarts the trading robot</Description></RegistrationInfo>
  <Triggers>
    <LogonTrigger><Enabled>true</Enabled><UserId>{escape(user)}</UserId></LogonTrigger>
    <TimeTrigger>
      <Repetition><Interval>PT5M</Interval><StopAtDurationEnd>false</StopAtDurationEnd></Repetition>
      <StartBoundary>2026-01-01T00:00:00</StartBoundary><Enabled>true</Enabled>
    </TimeTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author"><UserId>{escape(user)}</UserId><LogonType>InteractiveToken</LogonType><RunLevel>HighestAvailable</RunLevel></Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings><StopOnIdleEnd>false</StopOnIdleEnd><RestartOnIdle>false</RestartOnIdle></IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>7</Priority>
    <RestartOnFailure><Interval>PT1M</Interval><Count>999</Count></RestartOnFailure>
  </Settings>
  <Actions Context="Author">
    <Exec><Command>{escape(pyw)}</Command><Arguments>"{escape(os.path.abspath(__file__))}"</Arguments><WorkingDirectory>{escape(HERE)}</WorkingDirectory></Exec>
  </Actions>
</Task>
"""
    xml_path = os.path.join(LOGS, "watchdog_task.xml")
    os.makedirs(LOGS, exist_ok=True)
    with open(xml_path, "w", encoding="utf-16") as f:
        f.write(xml)
    subprocess.run(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"], capture_output=True)
    r = subprocess.run(["schtasks", "/Create", "/TN", TASK_NAME, "/XML", xml_path, "/F"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print("❌ ثبت در Task Scheduler انجام نشد:", (r.stdout or "") + (r.stderr or ""))
        print("   روی install_autostart.bat راست‌کلیک کن و Run as administrator را بزن.")
        return 1
    subprocess.run(["schtasks", "/Run", "/TN", TASK_NAME], capture_output=True)
    print("✅ نگهبان ثبت شد و همین الان (بدون پنجره) اجرا شد.")
    print("   - با هر ورود به ویندوز و هر ۵ دقیقه یک بار چک می‌شود؛ اگر بسته شده باشد دوباره اجرا می‌شود.")
    print("   - گزارش‌هایش در بله و در فایل logs\\نگهبان.txt است.")
    print(f"   - برای حذف:  schtasks /Delete /TN {TASK_NAME} /F")
    return 0


# ---------------- حلقه‌ی اصلی ----------------
def main():
    if not single_instance():
        print("⛔ یک نگهبان دیگر در حال اجراست — این یکی بسته می‌شود.")
        return EXIT_NO_RESTART
    log("========== نگهبان شروع به کار کرد ==========")
    down_since = None          # از کی ربات بی‌ضربان است
    last_start = 0.0           # آخرین تلاش برای راه‌اندازی
    last_remind = 0.0
    stop_noted = False
    sync_alerted = False

    while True:
        try:
            now = time.time()
            if os.path.exists(STOP_FLAG):
                if not stop_noted:
                    stop_noted = True
                    log("ربات عمداً خاموش شده (Ctrl+C یا stop_robot.bat) — روشنش نمی‌کنم تا خودت اجرایش کنی.")
                time.sleep(CHECK_SECONDS)
                continue
            stop_noted = False

            age, status = heartbeat_info()
            pid = robot_pid()
            alive = pid_alive(pid)

            healthy = age is not None and age < (HUNG_MINUTES if alive else DEAD_MINUTES)
            if healthy:
                if down_since is not None:
                    log(f"✅ ربات برگشت (آخرین ضربان {age:.1f} دقیقه پیش).", bale=True)
                    down_since = None
                # بازار باز و ربات سالم، ولی همگام‌سازی ۴ساعته انجام نشده؟
                ms = minutes_since_sync()
                market_open = ("تعطیل" not in status)
                if ms is not None and market_open and ms > SYNC_ALERT_HOURS * 60:
                    if not sync_alerted:
                        sync_alerted = True
                        log(f"⚠️ ربات روشن است ولی {ms / 60:.1f} ساعت است همگام‌سازی (بررسی کندل ۴ساعته) "
                            f"انجام نداده — لاگ ربات را چک کن. وضعیت: {status}", bale=True)
                else:
                    sync_alerted = False
                time.sleep(CHECK_SECONDS)
                continue

            # ربات مشکل دارد
            age_txt = "نامعلوم" if age is None else f"{age:.0f} دقیقه"
            if down_since is None:
                down_since = now
                last_remind = now
                since = last_heartbeat_ts() or (now - 3600)
                if alive:
                    why = ["پروسه‌ی ربات زنده است ولی جواب نمی‌دهد (گیر کرده) — بسته و دوباره اجرا می‌شود."]
                else:
                    why = diagnose(since)
                if not already_reported(since):
                    mark_reported(since)
                    log(f"⚠️ ربات از کار افتاده — {age_txt} است ضربانی نزده (پروسه زنده؟ {alive}). "
                        f"دارم دوباره روشنش می‌کنم.\nدلیل احتمالی:\n- " + "\n- ".join(why), bale=True)
                else:
                    log(f"⚠️ ربات هنوز خاموش است ({age_txt} بی‌ضربان) — دلیلش قبلاً گزارش شده؛ دوباره روشنش می‌کنم.")
            elif now - last_remind > REMIND_MINUTES * 60:
                last_remind = now
                log(f"⚠️ ربات هنوز برنگشته ({age_txt} بی‌ضربان) — دارم تلاش می‌کنم.", bale=True)

            if now - last_start < RESTART_WAIT_MINUTES * 60:
                time.sleep(CHECK_SECONDS)
                continue
            last_start = now
            if alive:
                log(f"ربات زنده است ولی گیر کرده (پروسه {pid}) — بسته می‌شود تا start_robot.bat دوباره اجرایش کند.")
                kill_pid(pid)
                time.sleep(20)
                if not pid_alive(pid) and (heartbeat_info()[0] or 99) >= DEAD_MINUTES:
                    # اگر پنجره‌ی start_robot.bat هم بسته شده باشد، کسی ربات را بالا نمی‌آورد
                    time.sleep(15)
                    if not pid_alive(robot_pid()):
                        start_robot()
                        log("start_robot.bat اجرا شد.")
            else:
                start_robot()
                log("ربات خاموش بود — start_robot.bat اجرا شد.")
            time.sleep(CHECK_SECONDS)
        except KeyboardInterrupt:
            log("نگهبان دستی متوقف شد.")
            return EXIT_NO_RESTART
        except Exception as e:
            log(f"❌ خطای نگهبان: {e}")
            try:
                time.sleep(CHECK_SECONDS)
            except KeyboardInterrupt:
                return EXIT_NO_RESTART


if __name__ == "__main__":
    if "--install" in sys.argv:
        code = install_task()
        if os.environ.get("WATCHDOG_FROM_BAT") != "1":
            try:
                input("\nبرای بستن Enter بزن...")
            except Exception:
                pass
        sys.exit(code)
    sys.exit(main() or 0)
