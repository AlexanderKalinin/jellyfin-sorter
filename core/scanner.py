import os
import logging
import re
from typing import List
from .fs_utils import is_video

EPISODE_RE = re.compile(r"[Ss](\d{1,2})[ ._-]*[Ee](\d{1,2})")
SAMPLE_RE = re.compile(r"(?i)\b(sample|trailer)\b")
MIN_SAMPLE_SIZE = 200 * 1024 * 1024  # 200 MB


def scan_videos(pack_path: str) -> List[str]:
    # сюда переносишь свою scan_videos
    ...


def detect_series(videos: List[str]) -> bool:
    # сюда переносишь свою detect_series
    return ...
