import logging
import os
import shutil
from typing import List

DRY_RUN = False  # будет переопределяться снаружи (bin/run_sorter.py)

VIDEO_EXT = {
    ".mkv",
    ".mp4",
    ".avi",
    ".mov",
    ".m4v",
    ".wmv",
    ".flv",
    ".ts",
    ".m2ts",
    ".mpeg",
    ".mpg",
    ".webm",
    ".3gp",
}
SUB_EXT = {
    ".srt",
    ".ass",
    ".ssa",
    ".vtt",
    ".sub",
    ".idx",
    ".sup",
    ".pgs",
    ".txt",
    ".lrc",
    ".dfxp",
    ".ttml",
    ".xml",
}
SKIP_PACK_EXT = {
    ".iso",
    ".img",
    ".dmg",
    ".exe",
    ".msi",
    ".apk",
    ".bin",
    ".cue",
    ".nrg",
    ".toast",
    ".rar",
    ".zip",
    ".7z",
    ".tar",
    ".gz",
    ".psar",
    ".pak",
    ".bat",
    ".cmd",
    ".sh",
    ".pkg",
    ".deb",
    ".rpm",
}


def is_video(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in VIDEO_EXT


def is_sub(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in SUB_EXT


def should_skip_pack(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in SKIP_PACK_EXT


def ensure_dir(path: str) -> None:
    if DRY_RUN:
        logging.info("DRY-RUN mkdir -p %s", path)
    else:
        os.makedirs(path, exist_ok=True)


def move_with_subs(src_file: str, dest_dir: str, new_basename: str | None = None) -> str:
    ensure_dir(dest_dir)

    fname = os.path.basename(src_file)
    name_no_ext, ext = os.path.splitext(fname)

    if new_basename:
        dest_name = new_basename + ext
    else:
        dest_name = fname
    dest_path = os.path.join(dest_dir, dest_name)

    if DRY_RUN:
        logging.info("DRY-RUN MOVE %s -> %s", src_file, dest_path)
    else:
        logging.info("MOVE %s -> %s", src_file, dest_path)
        shutil.move(src_file, dest_path)

    # переносим сабы с тем же basename
    src_dir = os.path.dirname(src_file)
    for entry in os.listdir(src_dir):
        epath = os.path.join(src_dir, entry)
        if not os.path.isfile(epath):
            continue
        base, eext = os.path.splitext(entry)
        if base != name_no_ext:
            continue
        if not is_sub(entry):
            continue

        sub_src = epath
        if new_basename:
            sub_dest_name = new_basename + eext
        else:
            sub_dest_name = entry
        sub_dest = os.path.join(dest_dir, sub_dest_name)

        if DRY_RUN:
            logging.info("DRY-RUN MOVE SUB %s -> %s", sub_src, sub_dest)
        else:
            logging.info("MOVE SUB: %s -> %s", sub_src, sub_dest)
            print(f"MOVE SUB: {sub_src} -> {sub_dest}")
            shutil.move(sub_src, sub_dest)

    return dest_path


def cleanup_empty_dirs(root_dir: str) -> None:
    root_abs = os.path.abspath(root_dir)
    for current, dirs, files in os.walk(root_dir, topdown=False):
        for f in list(files):
            full_path = os.path.join(current, f)
            ext = os.path.splitext(f)[1].lower()

            if f.endswith(".part"):
                if DRY_RUN:
                    logging.info("DRY-RUN REMOVE PART %s", full_path)
                else:
                    try:
                        logging.info("CLEANUP: REMOVE PART %s", full_path)
                        os.remove(full_path)
                    except OSError as e:
                        logging.warning("CLEANUP: error removing %s: %s", full_path, e)
            elif ext in {".nfo", ".xml", ".jpg", ".jpeg", ".png"}:
                if DRY_RUN:
                    logging.info("DRY-RUN REMOVE META %s", full_path)
                else:
                    try:
                        logging.info("CLEANUP: REMOVE META %s", full_path)
                        os.remove(full_path)
                    except OSError as e:
                        logging.warning("CLEANUP: error removing %s: %s", full_path, e)

        try:
            entries = os.listdir(current)
        except OSError:
            continue

        if not entries and os.path.abspath(current) != root_abs:
            if DRY_RUN:
                logging.info("DRY-RUN RMDIR %s", current)
            else:
                try:
                    logging.info("CLEANUP: RMDIR %s", current)
                    os.rmdir(current)
                except OSError as e:
                    logging.warning("CLEANUP: error removing %s: %s", current, e)
