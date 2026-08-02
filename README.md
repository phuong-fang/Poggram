<div align="center">

<img src="static/poggram.png" width="96" alt="">

# Poggram

**A desktop file explorer whose storage is a private Telegram channel.**

Virtual folders, live search, streaming playback and drag-and-drop — over an
archive supergroup the app creates for itself and is the only thing that
writes to.

</div>

<img src="preview/UI%20Grid%20view%20Expand%20Side%20bar%20160px.png" alt="Grid view">

## What it is

Your files physically live in Telegram, as messages in a private supergroup.
Poggram is the local index and UI that makes them findable: a folder tree,
search, thumbnails, versioning and a Trash — none of which Telegram itself
offers over a chat.

Nothing is stored on a third-party server. The app talks to Telegram directly
as your own account, and the index lives in a local SQLite database beside it.

## Features

- **File-explorer UI** — folder tree, breadcrumbs, grid and list views,
  multi-select, context menus, drag-and-drop upload, Trash with restore.
- **Streaming, not downloading** — video and audio play with range requests
  served straight from Telegram, so a 4 GB file starts instantly.
- **Search** — scoped to the open folder and its subfolders, live as you type.
- **Versioning** — upload over an existing file and keep its history.
- **Folder sync** — watch a local folder and upload new files automatically.
- **Resumable transfers** — pause, continue, and survive a restart mid-upload.
- **App-data backup** — the index itself is backed up into the archive, so a
  new machine can rebuild from Telegram alone.
- **Runs in the tray** — closing the window keeps transfers and sync going.

## Preview

| | |
|---|---|
| <img src="preview/UI%20List%20view%20Expand%20Side%20bar%20160px.png" alt="List view"> | <img src="preview/Image%20viewing.png" alt="Image viewer"> |
| List view | Built-in image viewer |
| <img src="preview/Video%20streaming.png" alt="Video streaming"> | <img src="preview/Upload%20process.png" alt="Transfers"> |
| Video streamed from Telegram | Transfers, with per-file progress and ETA |
| <img src="preview/UI%20Grid%20view%20Collapse%20Side%20bar%20160px.png" alt="Collapsed sidebar"> | <img src="preview/UI%20Grid%20view%20Collapse%20Side%20bar%2050px.png" alt="50px items"> |
| Collapsed sidebar | Item size down to 50px |

## Requirements

- Windows (the desktop shell uses WebView2, which ships with Windows 11)
- Python 3.13
- A Telegram account, and an `api_id` / `api_hash` from
  [my.telegram.org](https://my.telegram.org) — you create these yourself; the
  app never touches that page.

## Install

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

## Run

```
.venv\Scripts\pythonw app.py
```

Or double-click `Poggram.vbs`, which does the same without a console window.
Using `python.exe` instead of `pythonw.exe` also works and additionally opens
a console showing the log.

On first run: open **Settings**, enter your `api_id` / `api_hash`, sign in,
then create the archive supergroup. Everything else follows from there.

## Where things are kept

Everything local lives in `data/`, which is not tracked by git:

| | |
|---|---|
| `data/vault.db` | the file/folder index, settings, sync state |
| `data/telegram_vault.session.enc` | your Telegram session, encrypted |
| `data/cache/` | downloaded chunks and thumbnails |
| `data/poggram.log` | the app log (Settings → Interface → Open log file) |

**Treat the session file as a credential.** It authorises access to your
Telegram account. It is encrypted with a key held in the Windows credential
store, so copying it to another machine alone won't grant access — but it
should not be shared or committed.

## Licence

[GPL-3.0](LICENSE) © [phuong-fang](https://github.com/phuong-fang)
