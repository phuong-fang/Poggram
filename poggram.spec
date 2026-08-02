# PyInstaller spec for the portable Windows build.
#
#   .venv\Scripts\pyinstaller poggram.spec --noconfirm
#
# Produces dist/Poggram/ - a folder you can copy anywhere. data/ is created
# next to Poggram.exe on first run (see store._app_dir), so moving the folder
# moves the vault index, session and cache with it.
#
# onedir, not onefile: onefile re-extracts the whole bundle to %TEMP% on every
# launch, which is slow with Telethon + Pillow + WebView2 in tow, and it makes
# "portable" ambiguous - the exe would live in one place and its unpacked guts
# in another.
#
# WebView2 is assumed present (it ships with Windows 11). Without it pywebview
# raises on start rather than silently falling back to an engine that can't
# render this UI - see the gui="edgechromium" argument in app.py.

import json
import os
import subprocess

block_cipher = None
here = os.path.abspath(os.getcwd())


def _build_stamp():
    """Bakes the git build number into the bundle - a packaged app has no .git
    to ask at runtime (see version.py)."""
    def git(*args):
        try:
            out = subprocess.run(["git", "-C", here, *args], capture_output=True, text=True, timeout=5)
            return out.stdout.strip() if out.returncode == 0 else None
        except Exception:
            return None

    stamp = {"build": git("rev-list", "--count", "HEAD"),
             "commit": git("rev-parse", "--short", "HEAD"),
             "date": git("log", "-1", "--format=%cs")}
    path = os.path.join(here, "build_stamp.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(stamp, f)
    return path


stamp_path = _build_stamp()

a = Analysis(
    ["app.py"],
    pathex=[here],
    binaries=[],
    datas=[
        ("templates", "templates"),
        ("static", "static"),
        (stamp_path, "."),
    ],
    # Imported dynamically, so PyInstaller's static analysis can't see them:
    #   keyring.backends.Windows - holds the session encryption key; without it
    #     the app can't decrypt an existing session and forces a re-login.
    #   pystray._win32 - selected at runtime by platform.
    #   pillow_avif - registers itself as a Pillow plugin on import.
    # win32timezone was listed here and removed: pywin32 isn't installed at
    # all (keyring reaches the Windows vault through the pywin32-ctypes shim
    # instead), so PyInstaller only reported "Hidden import not found".
    hiddenimports=[
        "keyring.backends.Windows",
        "keyring.backends.chainer",
        "keyring.backends.fail",
        "pystray._win32",
        "pillow_avif",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Test-only and dev-only weight that would otherwise be dragged in.
    excludes=["pytest", "_pytest", "tkinter", "matplotlib", "numpy"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Poggram",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    # No console: the app logs to data/poggram.log and offers "Open log file"
    # in Settings and the tray. A console window can't be hidden reliably once
    # it exists - Windows Terminal as the console host makes GetConsoleWindow
    # return a proxy - so the fix is to never create one.
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(here, "static", "poggram.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Poggram",
)
