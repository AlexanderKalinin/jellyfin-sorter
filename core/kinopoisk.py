import os
import json
import logging
import urllib.request
import urllib.parse
from typing import Optional, Dict, List, Tuple

from .title_cleaner import (
    translit_latin_to_cyr,
    clean_title_for_kp,
    extract_year_from_name,
    sanitize_fs_name,
)
from .config import load_config, get_paths

_cfg = load_config()
_paths = get_paths(_cfg)

KP_CACHE_FILE = _paths["kp_cache"]
KP_USAGE_FILE = _paths["kp_usage"]

kp_cfg = _cfg.get("kinopoisk", {})
KP_API_KEYS = [
    k.strip() for k in [
        kp_cfg.get("api_key", ""),
        kp_cfg.get("api_key2", "")
    ] if k and k.strip()
]

KP_DAILY_LIMIT = 500

# тут: загрузка кэша, функция выбора текущего ключа,
# http_json / http_binary, kp_search, kp_fetch_* и т.д.
...
