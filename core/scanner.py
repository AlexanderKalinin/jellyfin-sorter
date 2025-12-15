import logging
import os
import re
from typing import List

from .fs_utils import is_video

EPISODE_RE = re.compile(r"[Ss](\d{1,2})[ ._-]*[Ee](\d{1,2})")
SAMPLE_RE = re.compile(r"(?i)\b(sample|trailer)\b")
MIN_SAMPLE_SIZE = 200 * 1024 * 1024  # 200 MB


def scan_videos(pack_path: str) -> List[str]:
    videos: List[str] = []
    if os.path.isfile(pack_path):
        if is_video(pack_path):
            videos.append(pack_path)
    else:
        for root, dirs, files in os.walk(pack_path):
            for f in files:
                full = os.path.join(root, f)
                if not is_video(full):
                    continue
                if SAMPLE_RE.search(f):
                    try:
                        size = os.path.getsize(full)
                    except OSError:
                        size = 0
                    if size < MIN_SAMPLE_SIZE:
                        logging.info("SKIP SAMPLE: %s (%d bytes)", full, size)
                        continue
                videos.append(full)
    logging.info("SCAN_VIDEOS: %s -> %d files", pack_path, len(videos))
    print(f"SCAN_VIDEOS: {pack_path} -> {len(videos)} video file(s)")
    return videos


def detect_series(videos: List[str]) -> bool:
    episodes = 0
    for v in videos:
        if EPISODE_RE.search(os.path.basename(v)):
            episodes += 1
    return episodes >= 2
