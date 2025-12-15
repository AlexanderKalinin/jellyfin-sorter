import json
import logging
import os
import urllib.parse
import urllib.request
from typing import Dict, List, Optional, Tuple

from .config import get_paths, load_config
from .title_cleaner import (
    clean_title_for_kp,
    extract_year_from_name,
    sanitize_fs_name,
    translit_latin_to_cyr,
)

_cfg = load_config()
_paths = get_paths(_cfg)

KP_CACHE_FILE = _paths["kp_cache"]
KP_USAGE_FILE = _paths["kp_usage"]

kp_cfg = _cfg.get("kinopoisk", {})
KP_API_KEYS = [
    k.strip() for k in [kp_cfg.get("api_key", ""), kp_cfg.get("api_key2", "")] if k and k.strip()
]

KP_DAILY_LIMIT = 500

KP_SEARCH_URL = (
    "https://kinopoiskapiunofficial.tech/api/v2.1/films/search-by-keyword"
    "?keyword={keyword}&page=1"
)
KP_DETAILS_URL = "https://kinopoiskapiunofficial.tech/api/v2.2/films/{kp_id}"
KP_SEASONS_URL = "https://kinopoiskapiunofficial.tech/api/v2.2/films/{kp_id}/seasons"
KP_IMAGES_URL = (
    "https://kinopoiskapiunofficial.tech/api/v2.2/films/{kp_id}/images?type=STILL&page=1"
)
KP_STAFF_URL = "https://kinopoiskapiunofficial.tech/api/v1/staff?filmId={kp_id}"


# === КЭШИ ===

def load_kp_cache() -> Dict[str, dict]:
    if os.path.exists(KP_CACHE_FILE):
        try:
            with open(KP_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            logging.warning("KP cache corrupted, recreating")
    return {}


def save_kp_cache(cache: Dict[str, dict]) -> None:
    os.makedirs(os.path.dirname(KP_CACHE_FILE), exist_ok=True)
    with open(KP_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def _load_kp_usage() -> dict:
    if os.path.exists(KP_USAGE_FILE):
        try:
            with open(KP_USAGE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            logging.warning("KP usage corrupted, recreating")
    return {}


def _save_kp_usage(data: dict) -> None:
    os.makedirs(os.path.dirname(KP_USAGE_FILE), exist_ok=True)
    with open(KP_USAGE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_kp_api_key() -> Optional[str]:
    if not KP_API_KEYS:
        return None

    data = _load_kp_usage()
    counts = data.get("counts", [0] * len(KP_API_KEYS))
    if len(counts) < len(KP_API_KEYS):
        counts = counts[: len(KP_API_KEYS)] + [0] * (len(KP_API_KEYS) - len(counts))

    for i, count in enumerate(counts):
        if count < KP_DAILY_LIMIT:
            data["index"] = i
            _save_kp_usage(data)
            return KP_API_KEYS[i]

    idx = data.get("index", 0)
    if idx >= len(KP_API_KEYS):
        idx = 0
    data["index"] = idx
    _save_kp_usage(data)
    return KP_API_KEYS[idx]


def register_kp_request() -> None:
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


# === HTTP ОБЁРТКИ ===


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


# === FETCH ===


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


STAFF_CACHE: Dict[str, list] = {}


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
                elif "PRODUCER" in prof_u:
                    producers.append(str(name))
                elif "ACTOR" in prof_u:
                    actors.append({"name": str(name), "role": str(role)})

    result["directors"] = directors
    result["writers"] = writers
    result["producers"] = producers
    result["actors"] = actors
    return result


# === ПОИСК ===


KP_CACHE: Dict[str, dict] = load_kp_cache()


# cache key = (title|type|year)
def kp_search(title: str, desired_type: str = "FILM", desired_year: Optional[int] = None) -> Tuple[Optional[str], Optional[dict]]:
    if not title:
        return None, None

    def cache_key(name: str) -> str:
        return f"{name}|{desired_type}|{desired_year or ''}"

    def search_once(query: str) -> Tuple[Optional[str], Optional[dict]]:
        url = KP_SEARCH_URL.format(keyword=urllib.parse.quote(query))
        data = http_json(url)
        if not data:
            return None, None
        films = data.get("films") or data.get("items") or []
        for f in films:
            t = f.get("type") or ""
            if isinstance(t, dict):
                t = t.get("nameRu") or t.get("nameEn") or ""
            t_upper = str(t).upper()
            if desired_type and desired_type not in t_upper:
                continue

            name_ru = f.get("nameRu") or ""
            name_orig = f.get("nameEn") or f.get("nameOriginal") or ""
            year = f.get("year")
            if desired_year and year and str(year) != str(desired_year):
                continue

            kp_code = str(f.get("filmId") or f.get("kinopoiskId") or f.get("id") or "")
            if not kp_code:
                continue
            info = kp_fetch_details(int(kp_code))
            if info:
                return kp_code, info
        return None, None

    key = cache_key(title)
    if key in KP_CACHE:
        entry = KP_CACHE[key]
        return entry.get("kp_code"), entry.get("kp_info")

    kp_code, kp_info = search_once(title)
    if kp_code and kp_info:
        KP_CACHE[key] = {"kp_code": kp_code, "kp_info": kp_info}
        save_kp_cache(KP_CACHE)
        return kp_code, kp_info

    translit = translit_latin_to_cyr(title)
    if translit.lower() != title.lower():
        key_tr = cache_key(translit)
        if key_tr in KP_CACHE:
            entry = KP_CACHE[key_tr]
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


# === УТИЛИТЫ ===


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
        from .title_cleaner import KP_IN_NAME_RE

        title = KP_IN_NAME_RE.sub("", folder_name)
        title = clean_title_for_kp(title)
        if not title:
            title = folder_name
    title = sanitize_fs_name(title)
    if year:
        return f"{title} ({year})"
    return title


def build_episode_index(kp_info: Optional[dict]) -> Dict[Tuple[int, int], Dict[str, str]]:
    result: Dict[Tuple[int, int], Dict[str, str]] = {}
    if not kp_info:
        return result

    kp_id = kp_info.get("kinopoiskId") or kp_info.get("filmId") or kp_info.get("id")
    if not kp_id:
        return result
    try:
        kp_id_int = int(kp_id)
    except Exception:
        return result

    seasons = kp_fetch_seasons(kp_id_int) or {}
    items = seasons.get("items") or seasons.get("seasons") or []

    for season in items:
        s_num = season.get("number") or season.get("seasonNumber")
        episodes = season.get("episodes") or []
        if s_num is None:
            s_num = season.get("seasonNumber")
        if s_num is None:
            continue
        try:
            s_num_int = int(s_num)
        except Exception:
            continue

        for ep in episodes:
            e_num = ep.get("episodeNumber") or ep.get("number")
            if e_num is None:
                continue
            try:
                e_num_int = int(e_num)
            except Exception:
                continue

            ep_info: Dict[str, str] = {}
            title_ru = ep.get("nameRu") or ""
            title_en = ep.get("nameEn") or ep.get("name") or ""
            release_date = ep.get("releaseDate") or ep.get("airDate") or ""
            if title_ru:
                ep_info["title_ru"] = str(title_ru)
            if title_en:
                ep_info["title_en"] = str(title_en)
            if release_date:
                ep_info["date"] = str(release_date)

            if ep_info:
                result[(s_num_int, e_num_int)] = ep_info

    return result
