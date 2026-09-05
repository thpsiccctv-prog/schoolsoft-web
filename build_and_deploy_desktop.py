import os
import sys
import subprocess
import shutil
import time

print("=== 1. STOPPING RUNNING THPSIC SCHOOLSOFT PROCESSES ===")
subprocess.run(["powershell", "-Command", "Get-Process | Where-Object { $_.ProcessName -like 'THPSIC SchoolSoft*' } | Stop-Process -Force -ErrorAction SilentlyContinue"], capture_output=True)
time.sleep(2)
print("Processes stopped.")

print("\n=== 2. RUNNING COLLECTSTATIC & BUILD ===")
os.chdir(r"E:\THPSIC-INTER-COLLEGE\01-source-code\schoolsoft_web")
python_exe = r"E:\THPSIC-INTER-COLLEGE\01-source-code\schoolsoft_web\.venv\Scripts\python.exe"

# 1. Collectstatic
print("Collecting static files...")
res = subprocess.run([python_exe, "manage.py", "collectstatic", "--noinput", "--clear"], capture_output=True, text=True)
if res.returncode != 0:
    print("Collectstatic failed:", res.stderr)
    sys.exit(1)
print("Static files collected.")

# 2. Build with PyInstaller
print("Building with PyInstaller...")
res_pyi = subprocess.run([python_exe, "-m", "PyInstaller", "--clean", "--noconfirm", "SchoolSoft.spec"], capture_output=True, text=True)
if res_pyi.returncode != 0:
    print("PyInstaller build failed:", res_pyi.stderr)
    print("PyInstaller stdout:", res_pyi.stdout[-500:])
    sys.exit(1)
print("PyInstaller build OK!")

# Copy base python dll if needed
dll = f"python{sys.version_info.major}{sys.version_info.minor}.dll"
src_dll = os.path.join(sys.base_prefix, dll)
dst_dll = os.path.join("dist", "THPSIC SchoolSoft", "_internal", dll)
if os.path.exists(src_dll) and not os.path.exists(dst_dll):
    shutil.copy2(src_dll, dst_dll)
# Copy sync helpers to dist
for helper in ["sync-desktop-to-online.bat", "export_for_sync.py", "verify_desktop_sync_db.py", "fast_load_data.py", "render-db-url-intercollege.txt", "render-db-url.txt"]:
    if os.path.exists(helper):
        shutil.copy2(helper, os.path.join("dist", "THPSIC SchoolSoft", helper))

print("\n=== 3. DEPLOYING TO 03-desktop-build-exe ===")
src_dist = r"E:\THPSIC-INTER-COLLEGE\01-source-code\schoolsoft_web\dist\THPSIC SchoolSoft"
dst_deploy = r"E:\THPSIC-INTER-COLLEGE\03-desktop-build-exe\THPSIC SchoolSoft"

if os.path.exists(src_dist):
    # Copy dist folder over deploy folder
    for root, dirs, files in os.walk(src_dist):
        rel_path = os.path.relpath(root, src_dist)
        target_dir = os.path.join(dst_deploy, rel_path)
        os.makedirs(target_dir, exist_ok=True)
        for f in files:
            src_f = os.path.join(root, f)
            dst_f = os.path.join(target_dir, f)
            try:
                shutil.copy2(src_f, dst_f)
            except Exception as e:
                print(f"Warning copying {f}: {e}")
    print(f"Deployed build successfully to: {dst_deploy}")
else:
    print(f"Error: {src_dist} not found!")

exe_path = os.path.join(dst_deploy, "THPSIC SchoolSoft.exe")
print(f"EXE Size: {os.path.getsize(exe_path):,} bytes | MTime: {time.ctime(os.path.getmtime(exe_path))}")
