# -*- coding: utf-8 -*-
"""نگهبان ربات — اگر ربات از کار افتاد یا گیر کرد، دوباره راه‌اندازی‌اش می‌کند و در بله خبر می‌دهد.

اجرا:  start_watchdog.bat   (یک بار هم install_autostart.bat را اجرا کن تا بعد از هر ری‌استارت
       ویندوز/VPS، نگهبان خودش بالا بیاید و ربات را هم بالا بیاورد)

چه می‌کند (هر ۱ دقیقه):
  - ربات هر ۳۰ ثانیه فایل logs/heartbeat.txt را به‌روز می‌کند. اگر این فایل کهنه شد:
      · پروسه‌ی ربات زنده ولی گیر کرده (۱۰ دقیقه بی‌ضربان) → بسته می‌شود تا start_robot.bat بالایش بیاورد
      · پروسه‌ی ربات مرده (۳ دقیقه بی‌ضربان) → start_robot.bat در پنجره‌ی جدید اجرا می‌شود
  - اگر بازار باز است و بیش از ۴ ساعت و ربع همگام‌سازی انجام نشده → هشدار در بله
  - اگر ربات عمداً خاموش شده (Ctrl+C یا stop_robot.bat) → دست نمی‌زند
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
EXIT_NO_RESTART = 3


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
                log(f"⚠️ ربات پاسخ نمی‌دهد — {age_txt} است ضربانی نزده | پروسه در حال اجرا؟ {alive}", bale=True)
                last_remind = now
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
    sys.exit(main() or 0)
