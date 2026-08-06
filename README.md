<div align="center">

<img src="static/poggram.png" width="96" alt="">

# Poggram

**A file explorer for Telegram.**

Virtual folders, live search, streaming playback and drag-and-drop.

</div>

<img src="preview/UI%20Grid%20view%20Expand%20Side%20bar%20160px.png" alt="Grid view">

## What it is

Your files live in Telegram, as messages in a supergroup.
Poggram is the local index and interface to manage them: folder tree,
search, thumbnails, files versioning and Trash.

The app talks to Telegram directly as your own account, and the index lives in a local SQLite database beside it.

## Features

- **File-explorer UI** — folder tree, breadcrumbs, grid and list views,
  multi-select, context menus, drag-and-drop upload, Trash with restore.
- **Streaming** — video/audio play with range requests served from Telegram.
- **Large upload/download** — Large file get split to multiple chunk at upload. 16GB file can be split to 8 smaller 2GB files (Or 4 smaller 4GB files with premium). Download simply merge the file back to it original state.
- **Search** — scoped to the open folder and its subfolders, search in realtime without slowdown.
- **Versioning** — upload over an existing file and keep its history.
- **Folder sync** — watch a local folder and upload new files automatically.
- **Resumable transfers** — pause, continue, and survive a restart mid-upload.
- **App-data backup** — the index itself is backed up into the archive, so a
  new machine can rebuild from Telegram alone.
- **Hide to tray** — closing the window keeps transfers and sync going.

## Preview

| | |
|---|---|
| <img src="preview/UI%20List%20view%20Expand%20Side%20bar%20160px.png" alt="List view"> | <img src="preview/Image%20viewing.png" alt="Image viewer"> |
| List view | Built-in image viewer |
| <img src="preview/Video%20streaming.png" alt="Video streaming"> | <img src="preview/Upload%20process.png" alt="Transfers"> |
| Video streamed from Telegram | Transfers, with per-file progress and ETA |
| <img src="preview/UI%20Grid%20view%20Collapse%20Side%20bar%20160px.png" alt="Collapsed sidebar"> | <img src="preview/UI%20Grid%20view%20Collapse%20Side%20bar%2050px.png" alt="50px items"> |
| Collapsed sidebar | Item size down to 50px |

## Quick start

### 1. Get your Telegram API keys

Poggram talks to Telegram **as your own account**, which needs a personal
`api_id` and `api_hash`. You create these yourself, once — the app never sees
your Telegram password and never visits this page for you.

1. Go to **[my.telegram.org](https://my.telegram.org/auth)** and log in with
   your phone number (Telegram sends the code to the app, not by SMS).
2. Open **API development tools**.
3. Fill in the short form — **App title** and **Short name** are all that
   matter, anything sensible will do. Platform: Desktop.
4. Copy the **`api_id`** (a number) and **`api_hash`** (a long string).

Keep them to yourself: together they identify your app to Telegram.

### 2. Install and run

Requirements: **Windows** (the UI runs on WebView2, which ships with
Windows 11) and **Python 3.13**.

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\pythonw app.py
```

Or double-click `Poggram.vbs`, which does the same with no console window.
Using `python.exe` instead opens a console showing the log, which is handy if
something goes wrong.

### 3. Sign in

Open **Settings** in the app, then:

1. Paste your **API ID** and **API hash**, enter your **phone number**, and
   press **Connect**.
2. Telegram sends you a login code — enter it and press **Submit code**.
3. If you have two-step verification on, enter that password too.

### 4. Create the archive

Still in Settings, press **Create supergroup**. Poggram makes a private
Telegram group that it writes to — this is where your files live.

That is the whole setup. Drag files or folders into the window to upload;
double-click to open, stream or download them.

> **Note:** everything is stored in your own Telegram account. Poggram runs entirely on your machine and there is no server in between.

## Telegram's terms apply

Poggram is a client for your own account, so [Telegram's ToS](https://telegram.org/tos) apply.

## Where things are kept

Everything local lives in `data/`:

| | |
|---|---|
| `data/vault.db` | the file/folder index, settings, sync state |
| `data/telegram_vault.session.enc` | your Telegram session, encrypted |
| `data/cache/` | downloaded chunks and thumbnails |
| `data/poggram.log` | the app log (Settings → Interface → Open log file) |

**Treat the session file as a credential.** It authorises access to your
Telegram account and should not be share regardless of encryption.
