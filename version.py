import json
import logging
import os
import sys
import subprocess

logger = logging.getLogger(__name__)

VERSION = "0.1.2"

_REPO_DIR = os.path.dirname(os.path.abspath(__file__))
_cached = None

_STAMP_FILE = "build_stamp.json"

def _bundled_stamp():
    base = getattr(sys, "_MEIPASS", _REPO_DIR)
    path = os.path.join(base, _STAMP_FILE)
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def _git(*args):

    try:
        result = subprocess.run(
            ["git", "-C", _REPO_DIR, *args],
            capture_output=True, text=True, timeout=3,

            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None

def describe():

    global _cached
    if _cached is not None:
        return _cached

    stamp = _bundled_stamp()
    if stamp:

        commits, commit, date = stamp.get("build"), stamp.get("commit"), stamp.get("date")
    else:
        commits = _git("rev-list", "--count", "HEAD")
        commit = _git("rev-parse", "--short", "HEAD")
        date = _git("log", "-1", "--format=%cs")
    commits = str(commits) if commits is not None else None

    info = {
        "version": VERSION,
        "build": int(commits) if commits and commits.isdigit() else None,
        "commit": commit,
        "date": date,
    }

    parts = [VERSION]
    detail = []
    if info["build"] is not None:
        detail.append(f"build {info['build']}")
    if info["commit"]:
        detail.append(info["commit"])
    if detail:
        parts.append(f"({' · '.join(detail)})")
    info["full"] = " ".join(parts)

    _cached = info
    return info
