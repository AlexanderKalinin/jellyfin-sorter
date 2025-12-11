import os
import re
from typing import Optional, Dict, List

APOSTROPHE_RE = re.compile(r"[’'`]")
# MANUAL_TITLE_MAP, GARBAGE_RE, YEAR_RE, BRACKETS_RE, KP_IN_NAME_RE – копипастой


def translit_latin_to_cyr(text: str) -> str:
    # сюда переносишь свою реализацию
    ...


def clean_title_for_kp(name: str) -> str:
    # твой текущий код clean_title_for_kp
    ...


def extract_year_from_name(name: str) -> Optional[int]:
    # твой текущий extract_year_from_name
    ...


def sanitize_fs_name(s: str) -> str:
    # твой sanitize_fs_name
    ...
