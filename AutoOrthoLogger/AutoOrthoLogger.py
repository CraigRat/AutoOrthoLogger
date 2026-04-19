import psutil
import socket
import struct
import time
import os
import sys
import select
import platform

# =================================================================
# CONFIGURATION
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

class LogTailer:
    """Handles continuous tailing and log rotation detection."""
    def __init__(self, path, prefix):
        self.path = path
        self.prefix = prefix
        self.handle = None
        self.last_inode = None
        self._open_file(seek_to_end=True) # Always seek to end on first run

    def _open_file(self, seek_to_end=False):
        if os.path.exists(self.path):
            try:
                self.handle = open(self.path, "r", errors='ignore')
                if seek_to_end:
                    self.handle.seek(0, os.SEEK_END)
                # Store the unique file ID (inode)
                self.last_inode = os.stat(self.path).st_ino
                return True
            except Exception as e:
                write_log("SYSTEM", f"Error opening {self.prefix}: {e}")
        return False

    def check_rotation(self):
        """Checks if the file has been rotated or recreated."""
        if not os.path.exists(self.path):
            return
        
        try:
            current_inode = os.stat(self.path).st_ino
            if current_inode != self.last_inode:
                write_log("SYSTEM", f"Detected log rotation for {self.prefix}. Following new file.")
                if self.handle:
                    self.handle.close()
                # When rotated, we want to read from the START of the new file
                self._open_file(seek_to_end=False)
        except Exception:
            pass

    def read_lines(self):
        if self.handle:
            return self.handle.readlines()
        return []

def get_detailed_os():
    try:
        os_info = {}
        if os.path.exists("/etc/os-release"):
            with open("/etc/os-release") as f:
                for line in f:
                    if "=" in line:
                        k, v = line.rstrip().replace('"', '').split("=", 1)
                        os_info[k] = v
        details = (f"OS: {os_info.get('PRETTY_NAME', 'Linux')}\n"
                   f"Kernel: {platform.release()}\n"
                   f"Python: {sys.version.split()[0]}")
        return details
    except Exception as e: return f"OS Info Error: {e}"

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
        with open(PATHS["SCENERY_INI"], "r") as ini: f.write(ini.read())
    f.write("\n[SCENERY_CONFIG_END]\n\n" + "="*80 + "\n\n")

# --- MAIN LOGGER LOGIC ---
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(("0.0.0.0", UDP_PORT))
sock.setblocking(False)

# Use our new class for both logs
tailers = [
    LogTailer(PATHS["XP_LOG"], "XP_FILE"),
    LogTailer(PATHS["AO_LOG"], "AO_FILE")
]

def get_mem(target):
    for proc in psutil.process_iter(['exe', 'cmdline', 'memory_info']):
        try:
            p_exe = proc.info['exe'] or ""
            p_cmd = " ".join(proc.info['cmdline'] or [])
            if target.lower() in p_exe.lower() or target.lower() in p_cmd.lower():
                return proc.info['memory_info'].rss / 1024 / 1024
        except (psutil.NoSuchProcess, psutil.AccessDenied): continue
    return 0

print(f"Logger ready. Only capturing NEW log entries. Type a note for markers.")
last_heartbeat = 0
last_rotation_check = 0

try:
    while True:
        # 1. User Marker Input
        if select.select([sys.stdin], [], [], 0)[0]:
            input_text = sys.stdin.readline().strip()
            msg = input_text if input_text else "MANUAL CHECKPOINT"
            write_log("USER_MARKER", f"ACTION: {msg}")

        # 2. Check for Log Rotation (Every 2 seconds)
        now = time.time()
        if now - last_rotation_check >= 2:
            for t in tailers:
                t.check_rotation()
            last_rotation_check = now

        # 3. Tail Logs
        for t in tailers:
            for line in t.read_lines():
                write_log(t.prefix, line)

        # 4. Heartbeat (Every 5s)
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
            except BlockingIOError: pass

            stats = f"POS: {lat:.5f},{lon:.5f} | ALT: {alt:.1f}m | MEM: XP {xp_mb:.1f}MB, AO {ao_mb:.1f}MB, SYS_U {sys_p}%, SYS_F {100.0-sys_p}%"
            write_log("HEARTBEAT", stats)
            last_heartbeat = now

        time.sleep(0.1)

except KeyboardInterrupt:
    print("\nShutting down.")
finally:
    for t in tailers:
        if t.handle: t.handle.close()
