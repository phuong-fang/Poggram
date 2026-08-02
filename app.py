import json
import logging
import os
import socket
import threading
import time
import uuid

from flask import Flask, render_template, request
from flask.wrappers import Request as FlaskRequest

import shared
import store
import sync_engine
import telegram_client
import tray

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

def _install_file_logging():
    try:
        from logging.handlers import RotatingFileHandler

        os.makedirs(store.DATA_DIR, exist_ok=True)
        handler = RotatingFileHandler(
            os.path.join(store.DATA_DIR, "poggram.log"),
            maxBytes=2_000_000, backupCount=3, encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s"))
        logging.getLogger().addHandler(handler)
    except Exception:

        logger.exception("Could not start file logging")

_install_file_logging()

logging.getLogger("telethon").setLevel(logging.WARNING)
logging.getLogger("telethon.client.updates").setLevel(logging.WARNING)
logging.getLogger("telethon.network.mtprotosender").setLevel(logging.WARNING)

logging.getLogger("telethon.client.users").setLevel(logging.INFO)

logging.getLogger("werkzeug").setLevel(logging.WARNING)

class VaultRequest(FlaskRequest):

    def _get_file_stream(self, total_content_length, content_type, filename=None, content_length=None):
        if not filename:
            return super()._get_file_stream(total_content_length, content_type, filename, content_length)
        try:
            path, handle = shared.new_upload_temp_file()
        except Exception:
            logger.exception("Upload staging: could not open a temp file in DATA_DIR, using the default")
            return super()._get_file_stream(total_content_length, content_type, filename, content_length)

        paths = getattr(self, "vault_upload_paths", None)
        if paths is None:
            paths = self.vault_upload_paths = []

        paths.append((path, handle))
        return handle

app = Flask(__name__, static_folder="static", template_folder="templates")
app.request_class = VaultRequest

@app.teardown_request
def _cleanup_unclaimed_uploads(exc):

    paths = getattr(request, "vault_upload_paths", None)
    if not paths:
        return
    for path, handle in paths:
        try:
            handle.close()
        except Exception:
            pass
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            logger.exception(f"Upload staging: could not remove unclaimed temp file {path}")

def apply_max_upload_request_size(value=None):

    if value is None:
        value = store.load_settings().get("max_upload_request_bytes")
    try:
        value = int(value)
    except (TypeError, ValueError):
        value = 64_000_000_000
    app.config["MAX_CONTENT_LENGTH"] = value if value > 0 else None
    return app.config["MAX_CONTENT_LENGTH"]

apply_max_upload_request_size()

telegram_client.start()

_window = None

@app.route("/")
def index():

    try:
        asset_version = int(max(
            os.path.getmtime(os.path.join(app.static_folder, "app.js")),
            os.path.getmtime(os.path.join(app.static_folder, "style.css")),
        ))
    except OSError:
        asset_version = 0
    return render_template("index.html", asset_version=asset_version)

@app.after_request
def _disable_caching(response):

    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

sync_engine.init(shared.start_background_upload)

def _on_native_drop(event):

    try:
        files = ((event or {}).get("dataTransfer") or {}).get("files") or []
        if not files:
            return

        folder_id = None
        if _window is not None:
            try:
                folder_id = _window.evaluate_js("window.currentFolderId")
            except Exception:
                logger.exception("Native drop: failed to read window.currentFolderId")
                folder_id = None
        if folder_id is not None:
            folder = next((f for f in store.load_folders() if f["id"] == folder_id), None)
            if folder is None or folder["deleted"]:
                logger.warning(f"Native drop: folder_id={folder_id} not found or deleted, falling back to root")
                folder_id = None
        else:

            logger.debug("Native drop: current folder is root (Home)")

        pending_uploads = []
        for file in files:

            path = file.get("pywebviewFullPath")
            if not path or not os.path.isfile(path):

                continue
            filename = file.get("name") or os.path.basename(path)
            pending_uploads.append({
                "id": str(uuid.uuid4()), "file_path": path, "filename": filename, "folder_id": folder_id,
            })
        if not pending_uploads:
            return

        store.save_queued_uploads(pending_uploads)
        if _window is not None:
            _window.evaluate_js(f"startQueuedNativeDrop({json.dumps(pending_uploads)})")
    except Exception:
        logger.exception("Native drop handler failed")

def _wire_native_drop(window):

    try:
        window.dom.document.on("drop", _on_native_drop)
    except Exception:
        logger.exception("Failed to wire native drop handler")

def _port_is_free(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) != 0

def _pick_port(candidates):
    for p in candidates:
        if _port_is_free(p):
            return p
    return candidates[0]

def _run_flask(port):

    debug = os.environ.get("POGGRAM_DEBUG") == "1"
    app.run(host="127.0.0.1", port=port, threaded=True, debug=debug, use_reloader=False)

def _set_windows_taskbar_identity():

    if os.name != "nt":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Poggram.Poggram")
    except Exception:
        logger.debug("Could not set the Windows AppUserModelID", exc_info=True)

def _force_window_icon():

    if os.name != "nt":
        return
    try:
        import ctypes

        user32 = ctypes.windll.user32
        hwnd = user32.FindWindowW(None, "Poggram")
        if not hwnd:
            logger.debug("Window icon: no window titled 'Poggram' found yet")
            return
        IMAGE_ICON, LR_LOADFROMFILE, LR_DEFAULTSIZE = 1, 0x0010, 0x0040
        WM_SETICON, ICON_SMALL, ICON_BIG = 0x0080, 0, 1
        for which, size in ((ICON_SMALL, 16), (ICON_BIG, 32)):
            handle = user32.LoadImageW(
                None, tray.ICON_PATH, IMAGE_ICON, size, size, LR_LOADFROMFILE | LR_DEFAULTSIZE
            )
            if handle:
                user32.SendMessageW(hwnd, WM_SETICON, which, handle)
            else:
                logger.debug("Window icon: LoadImageW returned nothing for %dpx", size)
    except Exception:
        logger.debug("Could not force the native window icon", exc_info=True)

def _on_app_closing():

    if tray.is_active() and store.load_settings().get("close_to_tray", True):
        tray.hide_window()
        return False

    tray.stop()
    shared.snapshot_now_blocking()
    sync_engine.shutdown()
    telegram_client.shutdown()

def main():
    global _window
    shared.window = _window
    port = _pick_port([5190, 5191, 5192, 5193])
    thread = threading.Thread(target=_run_flask, args=(port,), daemon=True)
    thread.start()

    import store
    store.migrate_from_json()

    try:
        import webview
    except ImportError:
        print(f"pywebview not installed - running as a plain web server at http://127.0.0.1:{port}/")
        thread.join()
        return

    _set_windows_taskbar_identity()
    window = webview.create_window(
        "Poggram", f"http://127.0.0.1:{port}/?_launch={int(time.time())}", width=1280, height=860, min_size=(560, 640)
    )
    _window = window
    shared.window = _window
    window.events.closing += _on_app_closing
    window.events.loaded += _wire_native_drop

    window.events.loaded += _force_window_icon

    def _really_quit():
        tray.stop()
        try:
            window.destroy()
        except Exception:
            logger.exception("Tray quit: failed to destroy the window")

    tray.start(window, _really_quit)

    webview.start(gui="edgechromium", debug=False, icon=tray.ICON_PATH)

import routes_folders
import routes_files
import routes_uploads
import routes_streaming
import routes_settings
import routes_telegram
import routes_backup
import routes_sync
import routes_transfers

routes_folders.register(app)
routes_files.register(app)
routes_uploads.register(app)
routes_streaming.register(app)
routes_settings.register(app)
routes_telegram.register(app)
routes_backup.register(app)
routes_sync.register(app)
routes_transfers.register(app)

if __name__ == "__main__":
    main()
