import os
import re
from typing import Dict, List, Optional

APOSTROPHE_RE = re.compile(r"[’'`]")

MANUAL_TITLE_MAP: Dict[str, str] = {
    "obnal'shchik": "Обнальщик",
    "obnalshchik": "Обнальщик",
    "obnalschik": "Обнальщик",
}

GARBAGE_RE = re.compile(
    r"(?i)\b("
    # качества
    r"hdrip|bdrip|dvdrip|tvrip|camrip|webrip|web[- ]?dl|blu[- ]?ray|bluray|bdremux|remux|ts|r5|scr|dvdscr|hdtv|satrip|dtheat|hdt"
    r"s|tc|hcam|bdmux|4k|uhd|8k|1080p|720p|2160p|4320p|sd|md|ld|ed|fullhd|fhd|uhd|hdr|dolby|vision|atmos|dvs|imax|uhdrip|dcp"
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
SEASON_TOKEN_RE = re.compile(r"(?i)(?:\bseason\s*\d{1,2}\b|\bs0?\d{1,2}\b)")


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
