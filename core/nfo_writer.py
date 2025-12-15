import os
import re
from typing import Dict, Optional
from xml.sax.saxutils import escape

from . import fs_utils
from .kinopoisk import kp_build_credits


def write_file(path: str, data, binary: bool = False) -> None:
    if fs_utils.DRY_RUN:
        import logging

        logging.info("DRY-RUN write file %s", path)
        return
    fs_utils.ensure_dir(os.path.dirname(path))
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


def write_movie_nfo(dest_dir: str, base_name: str, kp_code: Optional[str], kp_info: Optional[dict]) -> None:
    if not kp_info or not base_name:
        return

    nfo_path = os.path.join(dest_dir, f"{base_name}.nfo")
    if os.path.exists(nfo_path) and not fs_utils.DRY_RUN:
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
        c.get("country", "") for c in (kp_info.get("countries") or []) if c.get("country")
    ]
    genres_list = [g.get("genre", "") for g in (kp_info.get("genres") or []) if g.get("genre")]
    runtime = kp_info.get("filmLength") or ""
    slogan = kp_info.get("slogan") or ""
    premiere = (
        kp_info.get("premiereWorld") or kp_info.get("premiereRu") or kp_info.get("premiereDigital") or ""
    )

    companies = kp_info.get("companies") or []
    studios_list: list[str] = []
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

    lines: list[str] = []
    lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    lines.append("<movie>")
    lines.append(f"  <title>{escape(str(title_ru))}</title>")
    lines.append(f"  <originaltitle>{escape(str(title_orig))}</originaltitle>")
    lines.append(f"  <year>{escape(str(year))}</year>")
    lines.append(f"  <plot>{escape(str(plot))}</plot>")
    if rating_kp:
        lines.append(f"  <rating>{escape(str(rating_kp))}</rating>")
        lines.append(f'  <rating name="kinopoisk">{escape(str(rating_kp))}</rating>')
    if rating_imdb:
        lines.append(f'  <rating name="imdb">{escape(str(rating_imdb))}</rating>')
    if rating_critics:
        lines.append(f'  <rating name="filmCritics">{escape(str(rating_critics))}</rating>')
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


def write_tvshow_nfo(dest_root: str, kp_code: Optional[str], kp_info: Optional[dict]) -> None:
    if not kp_info:
        return

    nfo_path = os.path.join(dest_root, "tvshow.nfo")
    if os.path.exists(nfo_path) and not fs_utils.DRY_RUN:
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
        c.get("country", "") for c in (kp_info.get("countries") or []) if c.get("country")
    ]
    genres_list = [g.get("genre", "") for g in (kp_info.get("genres") or []) if g.get("genre")]
    premiere = kp_info.get("premiereWorld") or kp_info.get("premiereRu") or kp_info.get("premiereDigital") or ""

    companies = kp_info.get("companies") or []
    studios_list: list[str] = []
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

    lines: list[str] = []
    lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    lines.append("<tvshow>")
    lines.append(f"  <title>{escape(str(title_ru))}</title>")
    lines.append(f"  <originaltitle>{escape(str(title_orig))}</originaltitle>")
    lines.append(f"  <year>{escape(str(year))}</year>")
    lines.append(f"  <plot>{escape(str(plot))}</plot>")
    if rating_kp:
        lines.append(f"  <rating>{escape(str(rating_kp))}</rating>")
        lines.append(f'  <rating name="kinopoisk">{escape(str(rating_kp))}</rating>')
    if rating_imdb:
        lines.append(f'  <rating name="imdb">{escape(str(rating_imdb))}</rating>')
    if rating_critics:
        lines.append(f'  <rating name="filmCritics">{escape(str(rating_critics))}</rating>')
    if votes:
        lines.append(f"  <votes>{escape(str(votes))}</votes>")
    lines.append(f"  <id>{escape(str(kp_code or ''))}</id>")

    for g in genres_list:
        lines.append(f"  <genre>{escape(str(g))}</genre>")
    for c in countries_list:
        lines.append(f"  <country>{escape(str(c))}</country>")

    if mpaa:
        lines.append(f"  <mpaa>{escape(str(mpaa))}</mpaa>")
    if premiere:
        lines.append(f"  <premiered>{escape(str(premiere))}</premiered>")

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

    lines.append("</tvshow>")

    xml = "\n".join(lines)
    write_file(nfo_path, xml)


def write_episode_nfo(dest_video_path: str, season: int, episode: int, meta: Dict[str, str]) -> None:
    folder = os.path.dirname(dest_video_path)
    base = os.path.splitext(os.path.basename(dest_video_path))[0]
    nfo_path = os.path.join(folder, f"{base}.nfo")

    if os.path.exists(nfo_path) and not fs_utils.DRY_RUN:
        return

    title_ru = meta.get("title_ru", "")
    title_en = meta.get("title_en", "")
    date = meta.get("date", "")

    lines: list[str] = []
    lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    lines.append("<episodedetails>")
    lines.append(f"  <season>{season}</season>")
    lines.append(f"  <episode>{episode}</episode>")
    if title_ru:
        lines.append(f"  <title>{escape(str(title_ru))}</title>")
    elif title_en:
        lines.append(f"  <title>{escape(str(title_en))}</title>")
    if title_en:
        lines.append(f"  <originaltitle>{escape(str(title_en))}</originaltitle>")
    if date:
        lines.append(f"  <aired>{escape(str(date))}</aired>")
    lines.append("</episodedetails>")

    xml = "\n".join(lines)
    write_file(nfo_path, xml)
