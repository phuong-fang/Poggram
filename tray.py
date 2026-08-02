import logging
import os
import sys
import threading

import store

logger = logging.getLogger(__name__)

_icon = None
_icon_lock = threading.Lock()
_on_quit = None
_window = None

_ASSET_DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
ICON_PATH = os.path.join(_ASSET_DIR, "static", "poggram.ico")
_ICON_PNG_PATH = os.path.join(_ASSET_DIR, "static", "poggram.png")

def _build_image():

    from PIL import Image, ImageDraw

    for path in (ICON_PATH, _ICON_PNG_PATH):
        try:
            with Image.open(path) as source:

                if getattr(source, "ico", None) is not None:
                    return source.ico.getimage((64, 64)).convert("RGBA")
                return source.convert("RGBA").resize((64, 64), Image.LANCZOS)
        except Exception:
            logger.debug("Tray: couldn't load icon from %s", path, exc_info=True)

    logger.warning("Tray: icon asset unavailable - falling back to the drawn placeholder")
    size = 64
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle([4, 4, size - 5, size - 5], radius=12, fill=(59, 130, 246, 255))
    draw.rounded_rectangle([18, 18, size - 19, size - 19], radius=6, fill=(226, 236, 255, 255))
    return image

def is_active():

    with _icon_lock:
        return _icon is not None

def show_window():

    if _window is None:
        return
    try:
        _window.restore()
    except Exception:
        logger.debug("Tray: restore() failed", exc_info=True)
    try:
        _window.show()
    except Exception:
        logger.exception("Tray: failed to show the window")

def hide_window():
    if _window is None:
        return
    try:
        _window.hide()
    except Exception:
        logger.exception("Tray: failed to hide the window")

def _open_log(_icon, _item):

    try:
        path = os.path.join(store.DATA_DIR, "poggram.log")
        if os.path.isfile(path):
            os.startfile(path)
    except Exception:
        logger.exception("Tray: failed to open the log file")

def _quit_clicked(icon, _item):

    try:
        icon.visible = False
        icon.stop()
    except Exception:
        logger.debug("Tray: stopping the icon failed", exc_info=True)
    with _icon_lock:
        globals()["_icon"] = None
    if _on_quit:
        try:
            _on_quit()
        except Exception:
            logger.exception("Tray: quit handler failed")

def start(window, on_quit):

    global _icon, _on_quit, _window
    _window = window
    _on_quit = on_quit
    try:
        import pystray
    except Exception:
        logger.info("Tray: pystray unavailable - closing the window will quit as before")
        return False
    try:
        menu = pystray.Menu(

            pystray.MenuItem("Show Poggram", lambda icon, item: show_window(), default=True),

            pystray.MenuItem("Open log file", _open_log),
            pystray.MenuItem("Quit", _quit_clicked),
        )
        icon = pystray.Icon("poggram", _build_image(), "Poggram", menu)

        threading.Thread(target=icon.run, name="tray-icon", daemon=True).start()
    except Exception:
        logger.exception("Tray: failed to start - closing the window will quit as before")
        return False
    with _icon_lock:
        _icon = icon
    logger.info("Tray: icon started - closing the window parks the app instead of quitting")
    return True

def stop():

    global _icon
    with _icon_lock:
        icon, _icon = _icon, None
    if icon is None:
        return
    try:
        icon.visible = False
        icon.stop()
    except Exception:
        logger.debug("Tray: stop() failed", exc_info=True)
