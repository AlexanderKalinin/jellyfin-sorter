#!/usr/bin/env python3
import os
import time
import subprocess
from typing import Dict, List

# === RPC НАСТРОЙКА ===

TRANSMISSION_REMOTE = "/usr/bin/transmission-remote"

RPC_HOST = "192.168.100.6"
RPC_PORT = "9091"
RPC_USER = ""   # оставить пустым, если нет авторизации
RPC_PASS = ""

POLL_INTERVAL = 5  # секунды


# === БАЗОВЫЕ ПАПКИ — МЕНЯТЬ ТОЛЬКО ЭТО ===

BASE = "/mnt/WD/torrent"  # ← если перенесёшь на новый диск — меняешь только тут

WATCH_BASE    = os.path.join(BASE, "watch")
DOWNLOAD_BASE = os.path.join(BASE, "data")


# === ОПИСАНИЕ КАТЕГОРИЙ ===

CONFIG = {
    "main": {
        "watch":    os.path.join(WATCH_BASE, "main"),
        "download": os.path.join(DOWNLOAD_BASE, "main"),
    },
    "kids": {
        "watch":    os.path.join(WATCH_BASE, "kids"),
        "download": os.path.join(DOWNLOAD_BASE, "kids"),
    },
    "adult": {
        "watch":    os.path.join(WATCH_BASE, "adult"),
        "download": os.path.join(DOWNLOAD_BASE, "adult"),
    },
}


# === ФУНКЦИИ ===

def build_remote_cmd() -> List[str]:
    cmd = [TRANSMISSION_REMOTE, f"{RPC_HOST}:{RPC_PORT}"]
    if RPC_USER and RPC_PASS:
        cmd += ["-n", f"{RPC_USER}:{RPC_PASS}"]
    return cmd


def add_torrent(torrent_path: str, download_dir: str) -> bool:
    cmd = build_remote_cmd() + ["-w", download_dir, "-a", torrent_path]

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except FileNotFoundError:
        print(f"[ERROR] transmission-remote not found: {TRANSMISSION_REMOTE}")
        return False

    if result.returncode != 0:
        print(f"[ERROR] add failed: {torrent_path}")
        print("stderr:", result.stderr.strip())
        return False

    out = (result.stdout or "").lower()
    if "success" in out or "added" in out:
        print(f"[OK] added: {torrent_path} → {download_dir}")
        return True

    # Transmission иногда молчит, но rc=0 — считаем успехом
    print(f"[WARN] unknown response: {out.strip()}")
    return True


def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


def process_category(name: str, cfg: Dict[str, str]):
    watch_dir = cfg["watch"]
    download_dir = cfg["download"]

    ensure_dir(watch_dir)
    ensure_dir(download_dir)

    try:
        entries = sorted(os.listdir(watch_dir))
    except FileNotFoundError:
        return

    for entry in entries:

        # Удаляем macOS мусорные файлы
        if entry.startswith("._") or entry.startswith("."):
            garbage = os.path.join(watch_dir, entry)
            try:
                os.remove(garbage)
                print(f"[INFO] removed garbage: {garbage}")
            except:
                pass
            continue

        if not entry.lower().endswith(".torrent"):
            continue

        src = os.path.join(watch_dir, entry)

        if not os.path.isfile(src):
            continue

        print(f"[INFO] category={name} file={src}")

        ok = add_torrent(src, download_dir)

        # Удаляем .torrent после успешного добавления
        if ok:
            try:
                os.remove(src)
                print(f"[INFO] removed: {src}")
            except OSError as e:
                print(f"[WARN] cannot remove {src}: {e}")


def main():
    print("[START] torrent watcher")
    print(f"RPC: {RPC_HOST}:{RPC_PORT}")

    for cat, cfg in CONFIG.items():
        print(f"  category {cat}: {cfg['watch']} → {cfg['download']}")

    while True:
        for cat, cfg in CONFIG.items():
            process_category(cat, cfg)
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
