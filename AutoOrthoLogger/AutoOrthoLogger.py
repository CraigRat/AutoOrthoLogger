import psutil
import socket
import struct
import time
import os
import sys
import select
import platform

# =================================================================
# CONFIGURATION - ADJUST PATHS HERE
# =================================================================
HOME = os.path.expanduser("~")
XP_PATH = os.path.join(HOME, "X-Plane 12")

PATHS = {
    "XP_EXE": os.path.join(XP_PATH, "X-Plane-x86_64"),
    "XP_LOG": os.path.join(XP_PATH, "Log.txt"),
    "AO_LOG": os.path.join(HOME, ".autoortho-data/logs/autoortho.log"),
    "SCENERY_INI": os.path.join(XP_PATH, "Custom Scenery/scenery_packs.ini"),
    "MASTER_OUT": "xp_debug_unified.log"
}
UDP_PORT = 49003
# =================================================================

def get_detailed_os():
    try:
        os_info = {}
        if os.path.exists("/etc/os-release"):
            with open("/etc/os-release") as f:
                for line in f:
                    if "=" in line:
                        k, v = line.rstrip().replace('"', '').split("=", 1)
                        os_info[k] = v
        
        details = (
            f"OS: {os_info.get('PRETTY_NAME', 'Linux')}\n"
            f"Kernel: {platform.release()}\n"
            f"Architecture: {platform.machine()}\n"
            f"Python: {sys.version.split()[0]}"
        )
        return details
    except Exception as e:
        return f"OS Info Error: {e}"

def write_log(prefix, message):
    ts = time.strftime("%H:%M:%S")
    with open(PATHS["MASTER_OUT"], "a") as f:
        line = f"[{ts}] [{prefix}] {message.strip()}\n"
        f.write(line)
        print(line, end="\r\n")

# --- INITIALIZE HEADER ---
with open(PATHS["MASTER_OUT"], "w") as f:
    f.write("="*80 + "\n")
    f.write(f"X-PLANE DIAGNOSTIC LOG START: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    f.write("="*80 + "\n\n")
    f.write("[SYSTEM_INFO]\n" + get_detailed_os() + "\n\n")
    
    f.write("[SCENERY_CONFIG_START]\n")
    if os.path.exists(PATHS["SCENERY_INI"]):
        with open(PATHS["SCENERY_INI"], "r") as ini:
            f.write(ini.read())
    else:
        f.write(f"ERROR: {PATHS['SCENERY_INI']} not found.\n")
    f.write("\n[SCENERY_CONFIG_END]\n\n" + "="*80 + "\n\n")

# --- MAIN LOGGER LOGIC ---
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(("0.0.0.0", UDP_PORT))
sock.setblocking(False)

# Ensure files exist before opening to avoid crash
files_to_tail = {}
for key, path in [("XP_FILE", PATHS["XP_LOG"]), ("AO_FILE", PATHS["AO_LOG"])]:
    if os.path.exists(path):
        f = open(path, "r", errors='ignore')
        f.seek(0, os.SEEK_END)
        files_to_tail[key] = f
    else:
        write_log("INIT_ERR", f"Could not find log file: {path}")

def get_mem(target):
    for proc in psutil.process_iter(['exe', 'cmdline', 'memory_info']):
        try:
            p_exe = proc.info['exe'] or ""
            p_cmd = " ".join(proc.info['cmdline'] or [])
            if target.lower() in p_exe.lower() or target.lower() in p_cmd.lower():
                return proc.info['memory_info'].rss / 1024 / 1024
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return 0

print(f"Logger initialized. Type a note and hit Enter to mark the log.")
last_heartbeat = 0

try:
    while True:
        # 1. User Marker Input
        if select.select([sys.stdin], [], [], 0)[0]:
            input_text = sys.stdin.readline().strip()
            msg = input_text if input_text else "MANUAL CHECKPOINT"
            write_log("USER_MARKER", f"ACTION: {msg}")

        # 2. Tail Logs
        for prefix, f_obj in files_to_tail.items():
            lines = f_obj.readlines()
            for line in lines:
                write_log(prefix, line)

        # 3. Heartbeat
        now = time.time()
        if now - last_heartbeat >= 5:
            xp_mb = get_mem(PATHS["XP_EXE"])
            ao_mb = get_mem("autoortho")
            sys_p = psutil.virtual_memory().percent
            
            lat, lon, alt = 0.0, 0.0, 0.0
            try:
                while True:
                    data, addr = sock.recvfrom(1024)
                    if data.startswith(b'DATA') and len(data) >= 41:
                        idx = struct.unpack('<I', data[5:9])[0]
                        if idx == 20:
                            lat, lon, alt = struct.unpack('<fff', data[9:21])
            except BlockingIOError:
                pass

            stats = f"POS: {lat:.5f},{lon:.5f} | ALT: {alt:.1f}m | MEM: XP {xp_mb:.1f}MB, AO {ao_mb:.1f}MB, SYS {sys_p}%"
            write_log("HEARTBEAT", stats)
            last_heartbeat = now

        time.sleep(0.1)

except KeyboardInterrupt:
    print("\nShutting down.")
finally:
    for f in files_to_tail.values(): f.close()
