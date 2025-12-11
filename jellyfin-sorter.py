#!/usr/bin/env python3
import os
import re
import shutil
import logging
import json
import urllib.request
import urllib.parse
import datetime
from xml.sax.saxutils import escape
from typing import Optional, Tuple, Dict, List

CONFIG_PATH = "/opt/jellyfin-sorter/config.json"


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


CFG = load_config()

BASE = CFG["base_path"].rstrip("/")

paths_cfg = CFG.get("paths", {})
LOG_FILE = os.path.join(BASE, paths_cfg.get("log_file", "logs/jellyfin-sorter.log"))
KP_CACHE_FILE = os.path.join(BASE, paths_cfg.get("kp_cache", "logs/kp_cache.json"))
KP_USAGE_FILE = os.path.join(BASE, paths_cfg.get("kp_usage", "logs/kp_usage.json"))

kp_cfg = CFG.get("kinopoisk", {})
# Собираем список всех ключей, которые не пустые
KP_API_KEYS = [
    k.strip()
    for k in [
        kp_cfg.get("api_key", ""),
        kp_cfg.get("api_key2", ""),
    ]
    if k and k.strip()
]

KP_DAILY_LIMIT = 500  # лимит на один ключ в сутки

# === КОНФИГ КАТЕГОРИЙ ИЗ CONFIG.JSON ===
CATEGORY_CONFIG: Dict[str, Dict[str, str]] = {}
for name, c in CFG.get("categories", {}).items():
    cat: Dict[str, str] = {}

    data_rel = c.get("data")
    if data_rel:
        cat["data"] = os.path.join(BASE, data_rel.lstrip("/"))

    movies_rel = c.get("movies")
    if movies_rel:
        cat["movies"] = os.path.join(BASE, movies_rel.lstrip("/"))

    shows_rel = c.get("shows")
    if shows_rel:
        cat["shows"] = os.path.join(BASE, shows_rel.lstrip("/"))

    vr_rel = c.get("vr")
    if vr_rel:
        cat["vr"] = os.path.join(BASE, vr_rel.lstrip("/"))

    if cat:
        CATEGORY_CONFIG[name] = cat

# Текущие активные пути (переопределяются в main() при обходе категорий)
DATA_DIR = ""
MOVIES_DIR = ""
SHOWS_DIR = ""
CURRENT_CATEGORY = ""
ADULT_MOVIES_DIR = ""
ADULT_VR_DIR = ""

# Поиск по названию
KP_SEARCH_URL = (
    "https://kinopoiskapiunofficial.tech/api/v2.1/films/search-by-keyword"
    "?keyword={keyword}&page=1"
)

# Детали фильма/сериала по ID
KP_DETAILS_URL = "https://kinopoiskapiunofficial.tech/api/v2.2/films/{kp_id}"

# Сезоны сериала
KP_SEASONS_URL = "https://kinopoiskapiunofficial.tech/api/v2.2/films/{kp_id}/seasons"

# Кадры (STILL) для фильма/сериала
KP_IMAGES_URL = (
    "https://kinopoiskapiunofficial.tech/api/v2.2/films/{kp_id}/images?type=STILL&page=1"
)

# Персоны (актёры/режиссёры и т.п.)
KP_STAFF_URL = "https://kinopoiskapiunofficial.tech/api/v1/staff?filmId={kp_id}"

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

EPISODE_RE = re.compile(r"[Ss](\d{1,2})[ ._-]*[Ee](\d{1,2})")

# S01 / Season 1 в названии
SEASON_TOKEN_RE = re.compile(r"(?i)(?:\bseason\s*\d{1,2}\b|\bs0?\d{1,2}\b)")

# ручные маппинги проблемных названий → нормальное русское
MANUAL_TITLE_MAP: Dict[str, str] = {
    "obnal'shchik": "Обнальщик",
    "obnalshchik": "Обнальщик",
    "obnalschik": "Обнальщик",
}

# выкидываем мусор из названий перед запросом в KP
GARBAGE_RE = re.compile(
    r"(?i)\b("
    # качества
    r"hdrip|bdrip|dvdrip|tvrip|camrip|webrip|web[- ]?dl|blu[- ]?ray|bluray|bdremux|remux|ts|r5|scr|dvdscr|hdtv|satrip|dtheat|hdts|tc|hcam|bdmux|4k|uhd|8k|1080p|720p|2160p|4320p|sd|md|ld|ed|fullhd|fhd|uhd|hdr|dolby|vision|atmos|dvs|imax|uhdrip|dcp"
    r"|x264|x265|h\.?264|h\.?265|av1|hevc"
    r"|mp3|aac|flac|dts|truehd|ac3|5\.1|7\.1"
    # стандартный торрент-мусор
    r"|rip|enc|repack|proper|unrated|extended|collector'?s|dc|dir'?s.?cut|theatrical|remastered"
    r"|hybrid|mux|untouched"
    # переводчики/дубляжники
    r"|multi|multilang|russian|rus|eng|en|sub|subs|dub|duo|vo|avi|mp4|mkv"
    r"|line|mic|clean|org|original|voice|newvoice|dublado|subbed"
    # релиз-группы
    r"|new[- ]?team|hdclub|ntb|rarbg|yts|evo|fgt|amzn|nf|dsnp|hmax|hulu|webdl|xvid|qq|cmct|btn|ettv|tzk|exkinoray|kubik|kube|ton"
    # технические хвосты
    r"|hdr10|hdr10\+|dolby[- ]?vision|dolby[- ]?atmos|dv|da|bt2020|hlg"
    r"|sdh|hdrip|web|bd|bdmux"
    # локальный мусор
    r"|новинка|new|trailer|sample"
    r")\b"
)
YEAR_RE = re.compile(r"\(?\b(19|20)\d{2}\b\)?")
BRACKETS_RE = re.compile(r"\[[^\]]*\]")
KP_IN_NAME_RE = re.compile(r"\[kp\d+\]", re.IGNORECASE)

SAMPLE_RE = re.compile(r"(?i)\b(sample|trailer)\b")

MIN_SAMPLE_SIZE = 200 * 1024 * 1024  # 200 MB

os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

print("sorter start")
logging.info("SORTER: sorter start")

import sys as _sys

DRY_RUN = "--dry-run" in _sys.argv

# === КЭШИ ===


def load_kp_cache() -> Dict[str, dict]:
    if not os.path.exists(KP_CACHE_FILE):
        return {}
    try:
        with open(KP_CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logging.warning("KP CACHE: load error: %s", e)
        return {}


def save_kp_cache(cache: Dict[str, dict]) -> None:
    if DRY_RUN:
        logging.info("KP CACHE: dry-run, not saving")
        return
    try:
        os.makedirs(os.path.dirname(KP_CACHE_FILE), exist_ok=True)
        with open(KP_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.warning("KP CACHE: save error: %s", e)


KP_CACHE: Dict[str, dict] = load_kp_cache()
STAFF_CACHE: Dict[str, List[dict]] = {}

# === УЧЁТ И РОТАЦИЯ КЛЮЧЕЙ КИНОПОИСК ===


def _load_kp_usage() -> dict:
    """
    Структура:
    {
      "date": "YYYY-MM-DD",
      "index": 0,
      "counts": [123, 45, ...]
    }
    """
    today = datetime.date.today().isoformat()
    default = {
        "date": today,
        "index": 0,
        "counts": [0] * len(KP_API_KEYS),
    }

    if not KP_API_KEYS:
        return default

    try:
        with open(KP_USAGE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return default

    if data.get("date") != today or "counts" not in data:
        data = default
    else:
        counts = data.get("counts", [])
        if len(counts) != len(KP_API_KEYS):
            counts = counts[: len(KP_API_KEYS)] + [0] * max(
                0, len(KP_API_KEYS) - len(counts)
            )
        data["counts"] = counts

    if not isinstance(data.get("index"), int) or data["index"] >= len(KP_API_KEYS):
        data["index"] = 0

    return data


def _save_kp_usage(data: dict) -> None:
    if not KP_API_KEYS:
        return
    try:
        os.makedirs(os.path.dirname(KP_USAGE_FILE), exist_ok=True)
        with open(KP_USAGE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.warning("KP_USAGE WRITE ERROR: %s", e)


def get_kp_api_key() -> Optional[str]:
    """
    Возвращает актуальный API-ключ Кинопоиска с учётом лимита.
    Если все ключи исчерпаны за сутки — вернёт None.
    """
    if not KP_API_KEYS:
        return None

    data = _load_kp_usage()
    idx = data.get("index", 0)
    counts = data.get("counts", [0] * len(KP_API_KEYS))

    if idx >= len(KP_API_KEYS):
        idx = 0

    if counts[idx] >= KP_DAILY_LIMIT:
        switched = False
        for i in range(len(KP_API_KEYS)):
            if counts[i] < KP_DAILY_LIMIT:
                idx = i
                switched = True
                break
        if not switched:
            logging.error(
                "KINOPOLISK: all API keys exhausted for today. Working from cache only."
            )
            return None

    data["index"] = idx
    _save_kp_usage(data)
    return KP_API_KEYS[idx]


def register_kp_request() -> None:
    """Увеличивает счётчик для текущего ключа. Вызывается после успешного запроса."""
    if not KP_API_KEYS:
        return

    data = _load_kp_usage()
    idx = data.get("index", 0)
    if idx >= len(KP_API_KEYS):
        idx = 0

    counts = data.get("counts", [0] * len(KP_API_KEYS))
    if len(counts) < len(KP_API_KEYS):
        counts = counts[: len(KP_API_KEYS)] + [0] * (len(KP_API_KEYS) - len(counts))

    counts[idx] += 1
    data["counts"] = counts
    _save_kp_usage(data)


# === ТРАНСЛИТ ===

APOSTROPHE_RE = re.compile(r"[’'`]")


def translit_latin_to_cyr(text: str) -> str:
    s = APOSTROPHE_RE.sub("ь", text)
    s_low = s.lower()
    res: List[str] = []
    i = 0

    while i < len(s_low):
        ch = s_low[i]
        orig = s[i]

        if not ("a" <= ch <= "z"):
            res.append(orig)
            i += 1
            continue

        if s_low.startswith("shch", i):
            res.append("щ")
            i += 4
            continue
        if s_low.startswith("sch", i):
            res.append("щ")
            i += 3
            continue
        if s_low.startswith("yo", i) or s_low.startswith("jo", i):
            res.append("ё")
            i += 2
            continue
        if s_low.startswith("yu", i):
            res.append("ю")
            i += 2
            continue
        if s_low.startswith("ya", i):
            res.append("я")
            i += 2
            continue
        if s_low.startswith("zh", i):
            res.append("ж")
            i += 2
            continue
        if s_low.startswith("kh", i):
            res.append("х")
            i += 2
            continue
        if s_low.startswith("ts", i):
            res.append("ц")
            i += 2
            continue
        if s_low.startswith("ch", i):
            res.append("ч")
            i += 2
            continue
        if s_low.startswith("sh", i):
            res.append("ш")
            i += 2
            continue
        if s_low.startswith("ye", i) or s_low.startswith("je", i):
            res.append("е")
            i += 2
            continue

        mapping = {
            "a": "а",
            "b": "б",
            "v": "в",
            "g": "г",
            "d": "д",
            "e": "е",
            "z": "з",
            "i": "и",
            "y": "й",
            "j": "й",
            "k": "к",
            "l": "л",
            "m": "м",
            "n": "н",
            "o": "о",
            "p": "п",
            "r": "р",
            "s": "с",
            "t": "т",
            "u": "у",
            "f": "ф",
            "h": "х",
            "c": "к",
            "q": "к",
            "w": "в",
            "x": "кс",
        }
        res.append(mapping.get(ch, orig))
        i += 1

    return "".join(res)


# === УТИЛИТЫ ФС ===


def is_video(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in VIDEO_EXT


def is_sub(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in SUB_EXT


def should_skip_pack(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in SKIP_PACK_EXT


def clean_title_for_kp(name: str) -> str:
    base = os.path.basename(name)
    base = os.path.splitext(base)[0]
    base = base.replace(".", " ").replace("_", " ")

    base = BRACKETS_RE.sub(" ", base)
    base = YEAR_RE.sub(" ", base)
    base = SEASON_TOKEN_RE.sub(" ", base)
    base = GARBAGE_RE.sub(" ", base)

    base = re.sub(r"\s+", " ", base)
    base = base.strip(" -_.")
    lower = base.lower()
    if lower in MANUAL_TITLE_MAP:
        return MANUAL_TITLE_MAP[lower]
    return base


def extract_year_from_name(name: str) -> Optional[int]:
    m = YEAR_RE.search(name)
    if not m:
        return None
    try:
        return int(m.group(0).strip("()"))
    except Exception:
        return None


def sanitize_fs_name(s: str) -> str:
    s = re.sub(r'[\\/:*?"<>|]', " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


# === HTTP ОБЁРТКИ ДЛЯ КИНОПОИСКА С РОТАЦИЕЙ КЛЮЧЕЙ ===


def http_json(url: str) -> Optional[dict]:
    key = get_kp_api_key()
    if not key:
        logging.warning("HTTP JSON SKIP (no KP key): %s", url)
        return None

    req = urllib.request.Request(
        url,
        headers={
            "X-API-KEY": key,
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = resp.read()
            register_kp_request()
            return json.loads(data.decode("utf-8"))
    except Exception as e:
        logging.warning("HTTP JSON ERROR: %s: %s", url, e)
        return None


def http_binary(url: str) -> Optional[bytes]:
    key = get_kp_api_key()
    if not key:
        logging.warning("HTTP BIN SKIP (no KP key): %s", url)
        return None

    req = urllib.request.Request(
        url,
        headers={
            "X-API-KEY": key,
            "Accept": "*/*",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()
            register_kp_request()
            return data
    except Exception as e:
        logging.warning("HTTP BIN ERROR: %s: %s", url, e)
        return None


def kp_fetch_details(kp_id: int) -> Optional[dict]:
    url = KP_DETAILS_URL.format(kp_id=kp_id)
    return http_json(url)


def kp_fetch_seasons(kp_id: int) -> Optional[dict]:
    url = KP_SEASONS_URL.format(kp_id=kp_id)
    return http_json(url)


def kp_fetch_stills(kp_id: int) -> List[str]:
    url = KP_IMAGES_URL.format(kp_id=kp_id)
    data = http_json(url) or {}
    items = data.get("items") or data.get("frames") or []
    urls: List[str] = []
    for it in items:
        u = it.get("previewUrl") or it.get("imageUrl")
        if isinstance(u, str):
            urls.append(u)
    return urls


def kp_fetch_staff(kp_id: int) -> List[dict]:
    key = str(kp_id)
    if key in STAFF_CACHE:
        return STAFF_CACHE[key]
    url = KP_STAFF_URL.format(kp_id=kp_id)
    data = http_json(url)
    if isinstance(data, list):
        staff = data
    else:
        staff = (data or {}).get("items") or []
    STAFF_CACHE[key] = staff
    return staff


def kp_build_credits(kp_info: Optional[dict]) -> Dict[str, object]:
    """
    Возвращает словарь:
    {
      "directors": [str],
      "writers": [str],
      "producers": [str],
      "actors": [{"name": str, "role": str}]
    }
    Если Кинопоиск не даёт персон — массивы пустые.
    """
    result: Dict[str, object] = {
        "directors": [],
        "writers": [],
        "producers": [],
        "actors": [],
    }
    if not kp_info:
        return result

    directors: List[str] = []
    writers: List[str] = []
    producers: List[str] = []
    actors: List[Dict[str, str]] = []

    # 1) Пробуем встроенный блок persons (если есть)
    persons = kp_info.get("persons") or kp_info.get("staff") or []
    for p in persons:
        name = p.get("nameRu") or p.get("nameEn") or p.get("name") or ""
        if not name:
            continue
        prof = (
            p.get("profession")
            or p.get("professionRu")
            or p.get("professionText")
            or ""
        )
        prof_u = str(prof).upper()
        role = p.get("description") or p.get("role") or ""

        if ("РЕЖИССЕР" in prof_u) or ("DIRECTOR" in prof_u):
            directors.append(str(name))
        elif ("СЦЕНАРИСТ" in prof_u) or ("WRITER" in prof_u) or ("AUTHOR" in prof_u):
            writers.append(str(name))
        elif "ПРОДЮСЕР" in prof_u or "PRODUCER" in prof_u:
            producers.append(str(name))
        elif "АКТЕР" in prof_u or "ACTOR" in prof_u:
            actors.append({"name": str(name), "role": str(role)})

    # 2) Дополняем через /staff (если доступен)
    kp_id = kp_info.get("kinopoiskId") or kp_info.get("filmId") or kp_info.get("id")
    if kp_id:
        try:
            kp_id_int = int(kp_id)
        except Exception:
            kp_id_int = None
        if kp_id_int:
            staff = kp_fetch_staff(kp_id_int)
            for p in staff:
                name = p.get("nameRu") or p.get("nameEn") or p.get("name") or ""
                if not name:
                    continue
                prof = (
                    p.get("professionKey")
                    or p.get("profession")
                    or p.get("professionText")
                    or ""
                )
                prof_u = str(prof).upper()
                role = p.get("description") or ""

                if "DIRECTOR" in prof_u:
                    directors.append(str(name))
                elif ("WRITER" in prof_u) or ("SCENAR" in prof_u) or ("AUTHOR" in prof_u):
                    writers.append(str(name))
                elif "ACTOR" in prof_u:
                    actors.append({"name": str(name), "role": str(role)})
                elif "PRODUCER" in prof_u:
                    producers.append(str(name))

    def uniq(seq):
        out = []
        seen = set()
        for x in seq:
            key = (
                json.dumps(x, ensure_ascii=False, sort_keys=True)
                if isinstance(x, dict)
                else x
            )
            if not x or key in seen:
                continue
            seen.add(key)
            out.append(x)
        return out

    result["directors"] = uniq(directors)[:3]
    result["writers"] = uniq(writers)[:5]
    result["producers"] = uniq(producers)[:5]
    result["actors"] = uniq(actors)[:15]

    return result


def kp_search(
    title: str,
    desired_type: Optional[str] = None,
    desired_year: Optional[int] = None,
) -> Tuple[Optional[str], Optional[dict]]:
    if not title:
        return None, None

    key = f"{title.strip().lower()}|{desired_type or ''}|{desired_year or ''}"
    if key in KP_CACHE:
        entry = KP_CACHE[key]
        logging.info("KP CACHE HIT: '%s' -> %s", title, entry.get("kp_code"))
        print(f"KP CACHE: '{title}' -> {entry.get('kp_code')}")
        return entry.get("kp_code"), entry.get("kp_info")

    def search_once(q_title: str) -> Tuple[Optional[str], Optional[dict]]:
        try:
            q = urllib.parse.quote(q_title)
            url = KP_SEARCH_URL.format(keyword=q)
            data = http_json(url)
            if data is None:
                return None, None
        except Exception as e:
            logging.warning("KP: error for '%s': %s", q_title, e)
            return None, None

        items = data.get("films") or data.get("items") or []
        if not items:
            return None, None

        candidates = items
        if desired_type:
            filtered = []
            for f in items:
                t = f.get("type") or ""
                if isinstance(t, dict):
                    t = t.get("nameRu") or t.get("nameEn") or ""
                if str(t).upper().startswith(desired_type.upper()):
                    filtered.append(f)
            if filtered:
                candidates = filtered

        best = None
        best_score = 10**9
        for f in candidates:
            cid = f.get("filmId") or f.get("kinopoiskId") or f.get("id")
            cyear = f.get("year")
            try:
                cyear_int = int(cyear) if cyear is not None else None
            except Exception:
                cyear_int = None

            score = 0
            if desired_year is not None:
                if cyear_int is not None:
                    score += abs(desired_year - cyear_int)
                else:
                    score += 50

            if score < best_score:
                best_score = score
                best = (cid, cyear_int)

        if not best or not best[0]:
            return None, None

        kp_id = best[0]
        try:
            kp_id_int = int(kp_id)
        except Exception:
            kp_id_int = kp_id

        details = kp_fetch_details(kp_id_int)
        kp_code_local = f"kp{kp_id}"
        logging.info("KP: '%s' -> %s", q_title, kp_code_local)
        print(f"KP: '{q_title}' -> {kp_code_local}")
        return kp_code_local, details

    kp_code, kp_info = search_once(title)
    if kp_code and kp_info:
        KP_CACHE[key] = {"kp_code": kp_code, "kp_info": kp_info}
        save_kp_cache(KP_CACHE)
        return kp_code, kp_info

    translit = translit_latin_to_cyr(title).strip()
    if translit and translit.lower() != title.strip().lower():
        key_tr = f"{translit.lower()}|{desired_type or ''}|{desired_year or ''}"
        if key_tr in KP_CACHE:
            entry = KP_CACHE[key_tr]
            logging.info(
                "KP CACHE HIT TR: '%s' -> '%s' -> %s",
                title,
                translit,
                entry.get("kp_code"),
            )
            print(
                f"KP CACHE TR: '{title}' -> '{translit}' -> {entry.get('kp_code')}"
            )
            KP_CACHE[key] = entry
            save_kp_cache(KP_CACHE)
            return entry.get("kp_code"), entry.get("kp_info")

        kp_code, kp_info = search_once(translit)
        if kp_code and kp_info:
            KP_CACHE[key_tr] = {"kp_code": kp_code, "kp_info": kp_info}
            KP_CACHE[key] = {"kp_code": kp_code, "kp_info": kp_info}
            save_kp_cache(KP_CACHE)
            return kp_code, kp_info

    logging.info("KP: no results for '%s'", title)
    return None, None


def kp_is_series(kp_info: Optional[dict]) -> bool:
    if not kp_info:
        return False
    t = kp_info.get("type") or ""
    if isinstance(t, dict):
        t = t.get("nameRu") or t.get("nameEn") or ""
    t_str = str(t).upper()
    if "SERIES" in t_str:
        return True
    if kp_info.get("serial") or kp_info.get("isSeries"):
        return True
    return False


def build_movie_basename(kp_info: Optional[dict]) -> Optional[str]:
    if not kp_info:
        return None
    title_ru = kp_info.get("nameRu") or ""
    title_orig = kp_info.get("nameOriginal") or ""
    year = kp_info.get("year")
    title = title_ru or title_orig
    if not title:
        return None
    title = sanitize_fs_name(title)
    if year:
        return f"{title} ({year})"
    return title


def build_tvshow_title(kp_info: Optional[dict], folder_name: str) -> str:
    title = None
    year = None
    if kp_info:
        title = kp_info.get("nameRu") or kp_info.get("nameOriginal") or None
        year = kp_info.get("year")
    if not title:
        title = KP_IN_NAME_RE.sub("", folder_name)
        title = clean_title_for_kp(title)
        if not title:
            title = folder_name
    title = sanitize_fs_name(title)
    if year:
        return f"{title} ({year})"
    return title


def ensure_dir(path: str) -> None:
    if DRY_RUN:
        logging.info("DRY-RUN mkdir -p %s", path)
    else:
        os.makedirs(path, exist_ok=True)


def write_file(path: str, data, binary: bool = False) -> None:
    if DRY_RUN:
        logging.info("DRY-RUN write file %s", path)
        return
    ensure_dir(os.path.dirname(path))
    if binary:
        with open(path, "wb") as f:
            f.write(data)
    else:
        with open(path, "w", encoding="utf-8") as f:
            f.write(data)


def map_age_to_mpaa(age_raw: Optional[str]) -> str:
    if not age_raw:
        return ""
    m = re.search(r"\d+", str(age_raw))
    if not m:
        return ""
    return f"{m.group(0)}+"


def write_movie_nfo(
    dest_dir: str,
    base_name: str,
    kp_code: Optional[str],
    kp_info: Optional[dict],
) -> None:
    if not kp_info or not base_name:
        return

    nfo_path = os.path.join(dest_dir, f"{base_name}.nfo")
    if os.path.exists(nfo_path) and not DRY_RUN:
        return

    title_ru = kp_info.get("nameRu") or ""
    title_orig = kp_info.get("nameOriginal") or ""
    year = kp_info.get("year") or ""
    plot = kp_info.get("description") or ""
    rating_kp = kp_info.get("ratingKinopoisk") or ""
    rating_imdb = kp_info.get("ratingImdb") or ""
    rating_critics = kp_info.get("ratingFilmCritics") or ""
    votes = kp_info.get("ratingVoteCount") or ""
    age_raw = kp_info.get("ratingAgeLimits") or ""
    mpaa = map_age_to_mpaa(age_raw)

    countries_list = [
        c.get("country", "")
        for c in (kp_info.get("countries") or [])
        if c.get("country")
    ]
    genres_list = [
        g.get("genre", "") for g in (kp_info.get("genres") or []) if g.get("genre")
    ]
    runtime = kp_info.get("filmLength") or ""
    slogan = kp_info.get("slogan") or ""

    premiere = (
        kp_info.get("premiereWorld")
        or kp_info.get("premiereRu")
        or kp_info.get("premiereDigital")
        or ""
    )

    companies = kp_info.get("companies") or []
    studios_list: List[str] = []
    for c in companies:
        name = c.get("name")
        if not name:
            continue
        studios_list.append(str(name))

    credits = kp_build_credits(kp_info)
    directors = credits.get("directors", []) or []
    writers = credits.get("writers", []) or []
    producers = credits.get("producers", []) or []
    actors = credits.get("actors", []) or []

    lines: List[str] = []
    lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    lines.append("<movie>")
    lines.append(f"  <title>{escape(str(title_ru))}</title>")
    lines.append(f"  <originaltitle>{escape(str(title_orig))}</originaltitle>")
    lines.append(f"  <year>{escape(str(year))}</year>")
    lines.append(f"  <plot>{escape(str(plot))}</plot>")
    if rating_kp:
        lines.append(f"  <rating>{escape(str(rating_kp))}</rating>")
        lines.append(
            f'  <rating name="kinopoisk">{escape(str(rating_kp))}</rating>'
        )
    if rating_imdb:
        lines.append(f'  <rating name="imdb">{escape(str(rating_imdb))}</rating>')
    if rating_critics:
        lines.append(
            f'  <rating name="filmCritics">{escape(str(rating_critics))}</rating>'
        )
    if votes:
        lines.append(f"  <votes>{escape(str(votes))}</votes>")
    lines.append(f"  <id>{escape(str(kp_code or ''))}</id>")

    for g in genres_list:
        lines.append(f"  <genre>{escape(str(g))}</genre>")
    for c in countries_list:
        lines.append(f"  <country>{escape(str(c))}</country>")

    if runtime:
        lines.append(f"  <runtime>{escape(str(runtime))}</runtime>")
    if slogan:
        lines.append(f"  <tagline>{escape(str(slogan))}</tagline>")
    if premiere:
        lines.append(f"  <premiered>{escape(str(premiere))}</premiered>")
    if mpaa:
        lines.append(f"  <mpaa>{escape(str(mpaa))}</mpaa>")

    for s in studios_list:
        lines.append(f"  <studio>{escape(str(s))}</studio>")

    for d in directors:
        lines.append(f"  <director>{escape(str(d))}</director>")
    for w in writers:
        lines.append(f"  <writer>{escape(str(w))}</writer>")
    for p in producers:
        lines.append(f"  <producer>{escape(str(p))}</producer>")

    for a in actors:
        name = escape(str(a.get("name", "")))
        role = escape(str(a.get("role", "")))
        lines.append("  <actor>")
        lines.append(f"    <name>{name}</name>")
        if role:
            lines.append(f"    <role>{role}</role>")
        lines.append("  </actor>")

    for g in genres_list:
        lines.append(f"  <tag>{escape(str(g))}</tag>")

    lines.append("</movie>")

    xml = "\n".join(lines)
    write_file(nfo_path, xml)


def write_tvshow_nfo(
    dest_root: str,
    kp_code: Optional[str],
    kp_info: Optional[dict],
) -> None:
    if not kp_info:
        return

    nfo_path = os.path.join(dest_root, "tvshow.nfo")
    if os.path.exists(nfo_path) and not DRY_RUN:
        return

    title_ru = kp_info.get("nameRu") or ""
    title_orig = kp_info.get("nameOriginal") or ""
    year = kp_info.get("year") or ""
    plot = kp_info.get("description") or ""
    rating_kp = kp_info.get("ratingKinopoisk") or ""
    rating_imdb = kp_info.get("ratingImdb") or ""
    rating_critics = kp_info.get("ratingFilmCritics") or ""
    votes = kp_info.get("ratingVoteCount") or ""
    age_raw = kp_info.get("ratingAgeLimits") or ""
    mpaa = map_age_to_mpaa(age_raw)

    countries_list = [
        c.get("country", "")
        for c in (kp_info.get("countries") or [])
        if c.get("country")
    ]
    genres_list = [
        g.get("genre", "") for g in (kp_info.get("genres") or []) if g.get("genre")
    ]
    premiere = (
        kp_info.get("premiereWorld")
        or kp_info.get("premiereRu")
        or kp_info.get("premiereDigital")
        or ""
    )

    companies = kp_info.get("companies") or []
    studios_list: List[str] = []
    for c in companies:
        name = c.get("name")
        if not name:
            continue
        studios_list.append(str(name))

    credits = kp_build_credits(kp_info)
    directors = credits.get("directors", []) or []
    writers = credits.get("writers", []) or []
    actors = credits.get("actors", []) or []

    lines: List[str] = []
    lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    lines.append("<tvshow>")
    lines.append(f"  <title>{escape(str(title_ru))}</title>")
    lines.append(f"  <originaltitle>{escape(str(title_orig))}</originaltitle>")
    lines.append(f"  <year>{escape(str(year))}</year>")
    lines.append(f"  <plot>{escape(str(plot))}</plot>")
    if rating_kp:
        lines.append(f"  <rating>{escape(str(rating_kp))}</rating>")
        lines.append(
            f'  <rating name="kinopoisk">{escape(str(rating_kp))}</rating>'
        )
    if rating_imdb:
        lines.append(f'  <rating name="imdb">{escape(str(rating_imdb))}</rating>')
    if rating_critics:
        lines.append(
            f'  <rating name="filmCritics">{escape(str(rating_critics))}</rating>'
        )
    if votes:
        lines.append(f"  <votes>{escape(str(votes))}</votes>")
    lines.append(f"  <id>{escape(str(kp_code or ''))}</id>")

    for g in genres_list:
        lines.append(f"  <genre>{escape(str(g))}</genre>")
    for c in countries_list:
        lines.append(f"  <country>{escape(str(c))}</country>")
    if premiere:
        lines.append(f"  <premiered>{escape(str(premiere))}</premiered>")
    if mpaa:
        lines.append(f"  <mpaa>{escape(str(mpaa))}</mpaa>")

    for s in studios_list:
        lines.append(f"  <studio>{escape(str(s))}</studio>")

    for d in directors:
        lines.append(f"  <director>{escape(str(d))}</director>")
    for w in writers:
        lines.append(f"  <writer>{escape(str(w))}</writer>")

    for a in actors:
        name = escape(str(a.get("name", "")))
        role = escape(str(a.get("role", "")))
        lines.append("  <actor>")
        lines.append(f"    <name>{name}</name>")
        if role:
            lines.append(f"    <role>{role}</role>")
        lines.append("  </actor>")

    for g in genres_list:
        lines.append(f"  <tag>{escape(str(g))}</tag>")

    lines.append("</tvshow>")

    xml = "\n".join(lines)
    write_file(nfo_path, xml)


def write_episode_nfo(
    video_path: str,
    season: int,
    episode: int,
    meta: Optional[Dict[str, str]],
) -> None:
    """
    Пишем NFO только если meta не пустой.
    Если Кинопоиск не дал данные по серии — NFO не создаётся,
    чтобы Jellyfin мог взять описание из своих провайдеров.
    """
    if not meta:
        return

    base = os.path.splitext(os.path.basename(video_path))[0]
    nfo_path = os.path.join(os.path.dirname(video_path), base + ".nfo")
    if os.path.exists(nfo_path) and not DRY_RUN:
        return

    title_ru = meta.get("title_ru") or ""
    title_en = meta.get("title_en") or ""
    plot = meta.get("plot") or ""
    aired = meta.get("aired") or ""

    title = title_ru or title_en

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        "<episodedetails>",
        f"  <title>{escape(str(title))}</title>",
        f"  <season>{season}</season>",
        f"  <episode>{episode}</episode>",
        f"  <plot>{escape(str(plot))}</plot>",
        f"  <aired>{escape(str(aired))}</aired>",
        "</episodedetails>",
    ]
    xml = "\n".join(lines)
    write_file(nfo_path, xml)


def download_episode_thumb(
    video_path: str,
    img_url: Optional[str],
) -> None:
    if not img_url:
        return
    base = os.path.splitext(os.path.basename(video_path))[0]
    thumb_path = os.path.join(os.path.dirname(video_path), base + ".jpg")
    if os.path.exists(thumb_path) and not DRY_RUN:
        return

    data = http_binary(img_url)
    if not data:
        return

    if DRY_RUN:
        logging.info("DRY-RUN write episode thumb %s", thumb_path)
        return

    ensure_dir(os.path.dirname(thumb_path))
    try:
        with open(thumb_path, "wb") as f:
            f.write(data)
        logging.info("EP THUMB: %s <- %s", thumb_path, img_url)
    except Exception as e:
        logging.warning("EP THUMB WRITE ERROR: %s", e)


def build_episode_index(kp_info: Optional[dict]) -> Dict[Tuple[int, int], Dict[str, str]]:
    index: Dict[Tuple[int, int], Dict[str, str]] = {}
    if not kp_info:
        return index

    kp_id = kp_info.get("kinopoiskId") or kp_info.get("filmId") or kp_info.get("id")
    if not kp_id:
        return index
    try:
        kp_id_int = int(kp_id)
    except Exception:
        return index

    seasons = kp_fetch_seasons(kp_id_int)
    if not seasons:
        return index

    items = seasons.get("items") or seasons.get("seasons") or []
    for s in items:
        s_num = s.get("number") or s.get("seasonNumber") or s.get("season")
        if not s_num:
            continue
        try:
            s_num_int = int(s_num)
        except Exception:
            continue

        eps = s.get("episodes") or []
        for e in eps:
            e_num = e.get("episodeNumber") or e.get("number") or e.get("episode")
            if not e_num:
                continue
            try:
                e_num_int = int(e_num)
            except Exception:
                continue

            title_ru = (
                e.get("nameRu")
                or e.get("name")
                or e.get("nameRuShort")
                or ""
            )
            title_en = (
                e.get("nameEn")
                or e.get("nameOriginal")
                or ""
            )
            plot = (
                e.get("synopsis")
                or e.get("description")
                or e.get("shortDescription")
                or ""
            )
            aired = e.get("releaseDate") or e.get("premiereDate") or ""

            index[(s_num_int, e_num_int)] = {
                "title_ru": str(title_ru),
                "title_en": str(title_en),
                "plot": str(plot),
                "aired": str(aired),
            }

    return index


def ensure_season_poster(show_root: str, season_dir: str) -> None:
    show_poster = os.path.join(show_root, "folder.jpg")
    season_poster = os.path.join(season_dir, "folder.jpg")
    if os.path.exists(show_poster) and not os.path.exists(season_poster):
        if DRY_RUN:
            logging.info("DRY-RUN season poster %s -> %s", show_poster, season_poster)
            return
        try:
            ensure_dir(season_dir)
            shutil.copy2(show_poster, season_poster)
            logging.info("SEASON POSTER: %s -> %s", show_poster, season_poster)
        except Exception as e:
            logging.warning("SEASON POSTER COPY ERROR: %s", e)


def move_with_subs(
    src_file: str,
    dest_dir: str,
    new_basename: Optional[str] = None,
) -> str:
    ensure_dir(dest_dir)

    src_name = os.path.basename(src_file)
    base_old, ext = os.path.splitext(src_name)

    if new_basename:
        video_name = new_basename + ext
    else:
        video_name = src_name

    dest_path = os.path.join(dest_dir, video_name)
    logging.info("MOVE: %s -> %s", src_file, dest_path)
    print(f"MOVE: {src_file} -> {dest_path}")

    if not DRY_RUN:
        shutil.move(src_file, dest_path)

        src_dir = os.path.dirname(src_file)
        try:
            entries = os.listdir(src_dir)
        except OSError:
            entries = []
        for entry in entries:
            ebase, eext = os.path.splitext(entry)
            if ebase == base_old and is_sub(entry):
                sub_src = os.path.join(src_dir, entry)
                if new_basename:
                    sub_dest_name = new_basename + eext
                else:
                    sub_dest_name = entry
                sub_dest = os.path.join(dest_dir, sub_dest_name)
                logging.info("MOVE SUB: %s -> %s", sub_src, sub_dest)
                print(f"MOVE SUB: {sub_src} -> {sub_dest}")
                shutil.move(sub_src, sub_dest)

    return dest_path


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


# === ОПРЕДЕЛЕНИЕ VR (ЭВРИСТИКА) ===


def is_vr_pack(pack_name: str, videos: List[str]) -> bool:
    """
    Простая эвристика: если в названии пака или файлов есть 'vr' или 'oculus'.
    """
    name = pack_name.lower()
    if "vr" in name or "oculus" in name:
        return True
    for v in videos:
        fn = os.path.basename(v).lower()
        if "vr" in fn or "oculus" in fn:
            return True
    return False


def handle_series_pack(
    pack_path: str,
    kp_code: Optional[str],
    kp_info: Optional[dict],
) -> None:
    pack_name = os.path.basename(pack_path)

    show_title = build_tvshow_title(kp_info, pack_name)
    dest_root = os.path.join(SHOWS_DIR, show_title)

    print(f"SERIES DIR: {pack_path} -> {dest_root}")
    logging.info("SERIES DIR: %s -> %s", pack_path, dest_root)

    ensure_dir(dest_root)
    write_tvshow_nfo(dest_root, kp_code, kp_info)

    if kp_info:
        poster_url = kp_info.get("posterUrl") or kp_info.get("posterUrlPreview")
        if isinstance(poster_url, str):
            data = http_binary(poster_url)
            if data:
                poster_path = os.path.join(dest_root, "folder.jpg")
                if not os.path.exists(poster_path) or DRY_RUN:
                    if DRY_RUN:
                        logging.info("DRY-RUN write show poster %s", poster_path)
                    else:
                        ensure_dir(os.path.dirname(poster_path))
                        try:
                            with open(poster_path, "wb") as f:
                                f.write(data)
                            logging.info("SHOW POSTER: %s <- %s", poster_path, poster_url)
                        except Exception as e:
                            logging.warning("SHOW POSTER WRITE ERROR: %s", e)

    videos = scan_videos(pack_path)

    ep_index = build_episode_index(kp_info)
    stills: List[str] = []
    if kp_info:
        kp_id = kp_info.get("kinopoiskId") or kp_info.get("filmId") or kp_info.get("id")
        try:
            kp_id_int = int(kp_id) if kp_id else None
        except Exception:
            kp_id_int = None
        if kp_id_int:
            stills = kp_fetch_stills(kp_id_int)

    videos_sorted = sorted(videos)

    for v in videos_sorted:
        fname = os.path.basename(v)
        m = EPISODE_RE.search(fname)

        if m:
            season = int(m.group(1))
            episode = int(m.group(2))
            season_dir = os.path.join(dest_root, f"Season {season:02d}")
        else:
            season = 0
            episode = None
            season_dir = os.path.join(dest_root, "Specials")
            logging.info("SERIES SPECIAL: %s -> %s", fname, season_dir)
            print(f"SERIES SPECIAL: {fname} -> {season_dir}")

        dest_video_path = move_with_subs(v, season_dir)

        ensure_season_poster(dest_root, season_dir)

        if episode is not None:
            meta = ep_index.get((season, episode))
            if not meta:
                logging.warning("EP META MISSING: %s S%02dE%02d", show_title, season, episode)
                print(f"EP META MISSING: {show_title} S{season:02d}E{episode:02d}")
            else:
                write_episode_nfo(dest_video_path, season, episode, meta)
                if stills:
                    img_url = stills[(episode - 1) % len(stills)]
                    download_episode_thumb(dest_video_path, img_url)


def handle_movie_pack(
    pack_path: str,
    kp_code: Optional[str],
    kp_info: Optional[dict],
) -> None:
    global CURRENT_CATEGORY, ADULT_MOVIES_DIR, ADULT_VR_DIR

    pack_name = os.path.basename(pack_path)
    videos = scan_videos(pack_path)

    cleaned = clean_title_for_kp(pack_name)
    movie_base = build_movie_basename(kp_info)

    if movie_base:
        dest_dir_name = movie_base
    else:
        pretty = pack_name
        if cleaned and "[" in pack_name and "kp" not in pack_name.lower():
            pretty = cleaned
        if cleaned and len(cleaned) >= 3 and not any(c.isalpha() for c in pack_name):
            pretty = cleaned
        dest_dir_name = sanitize_fs_name(pretty.strip())

    # базовый корень для фильмов
    base_root = MOVIES_DIR

    # для adult-категории пробуем отправить VR-релизы в отдельную папку
    if CURRENT_CATEGORY == "adult" and ADULT_VR_DIR:
        if is_vr_pack(pack_name, videos):
            base_root = ADULT_VR_DIR
            logging.info("VR DETECTED: %s -> adult/vr", pack_name)
            print(f"VR DETECTED: {pack_name} -> adult/vr")

    dest_dir = os.path.join(base_root, dest_dir_name)
    print(f"MOVIE DIR: {pack_path} -> {dest_dir}")
    logging.info("MOVIE DIR: %s -> %s", pack_path, dest_dir)

    ensure_dir(dest_dir)

    new_base = movie_base

    for idx, v in enumerate(sorted(videos)):
        if idx == 0 and new_base:
            move_with_subs(v, dest_dir, new_basename=new_base)
        else:
            move_with_subs(v, dest_dir)

    if new_base:
        write_movie_nfo(dest_dir, new_base, kp_code, kp_info)

    if kp_info:
        poster_url = kp_info.get("posterUrl") or kp_info.get("posterUrlPreview")
        if isinstance(poster_url, str):
            data = http_binary(poster_url)
            if data:
                poster_path = os.path.join(dest_dir, "folder.jpg")
                if not os.path.exists(poster_path) or DRY_RUN:
                    if DRY_RUN:
                        logging.info("DRY-RUN write movie poster %s", poster_path)
                    else:
                        ensure_dir(os.path.dirname(poster_path))
                        try:
                            with open(poster_path, "wb") as f:
                                f.write(data)
                            logging.info("MOVIE POSTER: %s <- %s", poster_path, poster_url)
                        except Exception as e:
                            logging.warning("MOVIE POSTER WRITE ERROR: %s", e)


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


def process_pack(path: str) -> None:
    if should_skip_pack(path):
        logging.info("SKIP PACK (image/app): %s", path)
        print(f"SKIP PACK: {path}")
        return

    videos = scan_videos(path)
    if not videos:
        logging.info("NO VIDEO in %s", path)
        print(f"NO VIDEO in {path}")
        return

    pack_name = os.path.basename(path)

    kp_title = clean_title_for_kp(pack_name)
    if not kp_title and videos:
        kp_title = clean_title_for_kp(os.path.basename(videos[0]))

    is_series_guess = detect_series(videos)

    desired_type = "TV_SERIES" if is_series_guess else "FILM"
    desired_year = extract_year_from_name(pack_name)

    if kp_title:
        kp_code, kp_info = kp_search(kp_title, desired_type, desired_year)
    else:
        kp_code, kp_info = (None, None)

    is_series = is_series_guess
    if kp_is_series(kp_info):
        is_series = True

    print(f"DECISION: {pack_name} -> {'SERIES' if is_series else 'MOVIE'}")
    logging.info("DECISION: %s -> %s", pack_name, "SERIES" if is_series else "MOVIE")

    if is_series:
        handle_series_pack(path, kp_code, kp_info)
    else:
        handle_movie_pack(path, kp_code, kp_info)


def main() -> None:
    global DATA_DIR, MOVIES_DIR, SHOWS_DIR, CURRENT_CATEGORY, ADULT_MOVIES_DIR, ADULT_VR_DIR

    for category, cfg in CATEGORY_CONFIG.items():
        DATA_DIR = cfg.get("data", "")
        MOVIES_DIR = cfg.get("movies", "")
        SHOWS_DIR = cfg.get("shows", "")
        CURRENT_CATEGORY = category
        ADULT_MOVIES_DIR = cfg.get("movies")
        ADULT_VR_DIR = cfg.get("vr")

        if not DATA_DIR or not os.path.isdir(DATA_DIR):
            logging.info("DATA_DIR does not exist for category %s: %s", category, DATA_DIR)
            print(f"SKIP CATEGORY {category}: DATA_DIR does not exist: {DATA_DIR}")
            continue

        logging.info("CATEGORY START: %s (%s)", category, DATA_DIR)
        print(f"=== CATEGORY: {category} ({DATA_DIR}) ===")

        for entry in sorted(os.listdir(DATA_DIR)):
            full = os.path.join(DATA_DIR, entry)
            print(f"PROCESS PACK: {full}")
            logging.info("PROCESS PACK: %s", full)
            try:
                process_pack(full)
            except Exception as e:
                logging.exception("ERROR processing %s: %s", full, e)
                print(f"ERROR processing {full}: {e}")

        cleanup_empty_dirs(DATA_DIR)

    logging.info("SORTER: sorter done")
    print("sorter done")


if __name__ == "__main__":
    main()
