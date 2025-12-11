import os
import shutil
import logging
from typing import List
from . import video_exts, sub_exts, skip_pack_exts  # либо захардкодить тут

DRY_RUN = False  # значение будет переопределяться снаружи, если хочешь

VIDEO_EXT = {
    ".mkv", ".mp4", ".avi", ".mov", ".m4v",
    ".wmv", ".flv", ".ts", ".m2ts",
    ".mpeg", ".mpg", ".webm", ".3gp"
}
SUB_EXT = {
    ".srt", ".ass", ".ssa", ".vtt", ".sub", ".idx",
    ".sup", ".pgs", ".txt", ".lrc",
    ".dfxp", ".ttml", ".xml"
}
SKIP_PACK_EXT = {
    ".iso", ".img", ".dmg", ".exe", ".msi", ".apk",
    ".bin", ".cue", ".nrg", ".toast",
    ".rar", ".zip", ".7z", ".tar", ".gz",
    ".psar", ".pak",
    ".bat", ".cmd", ".sh",
    ".pkg", ".deb", ".rpm"
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


def move_with_subs(src_file: str,
                   dest_dir: str,
                   new_basename: str | None = None) -> str:
    # сюда просто копипастишь свою текущую реализацию move_with_subs
    ...


def cleanup_empty_dirs(root_dir: str) -> None:
    # сюда копипастишь свою cleanup_empty_dirs
    ...
