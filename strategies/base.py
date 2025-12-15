import os
import logging
from abc import ABC, abstractmethod

from core.config import CategoryPaths
from core.scanner import EPISODE_RE, detect_series, scan_videos
from core.title_cleaner import clean_title_for_kp, extract_year_from_name
from core.kinopoisk import (
    http_binary,
    kp_search,
    kp_is_series,
    build_tvshow_title,
    build_movie_basename,
    build_episode_index,
    kp_fetch_stills,
)
from core.fs_utils import ensure_dir, move_with_subs
from core.nfo_writer import (
    write_movie_nfo,
    write_tvshow_nfo,
    write_episode_nfo,
)
from core.posters import (
    ensure_season_poster,
    download_episode_thumb,
)
import core.fs_utils as fs_utils


class CategoryStrategy(ABC):
    def __init__(self, paths: CategoryPaths, dry_run: bool = False):
        self.paths = paths
        self.dry_run = dry_run

    @abstractmethod
    def process_pack(self, pack_path: str) -> None:
        ...


class DefaultCategoryStrategy(CategoryStrategy):
    def process_pack(self, pack_path: str) -> None:
        pack_name = os.path.basename(pack_path)
        videos = scan_videos(pack_path)
        if not videos:
            logging.info("NO VIDEO in %s", pack_path)
            print(f"NO VIDEO in {pack_path}")
            return

        kp_title = clean_title_for_kp(pack_name) or clean_title_for_kp(os.path.basename(videos[0]))
        desired_year = extract_year_from_name(pack_name)
        guessed_series = detect_series(videos)

        desired_type = "TV_SERIES" if guessed_series else "FILM"
        kp_code, kp_info = (kp_search(kp_title, desired_type, desired_year) if kp_title else (None, None))

        is_series = self.classify(pack_name, videos, kp_info)
        logging.info("DECISION: %s -> %s", pack_name, "SERIES" if is_series else "MOVIE")
        print(f"DECISION: {pack_name} -> {'SERIES' if is_series else 'MOVIE'}")

        if is_series:
            self.handle_series(pack_path, kp_code, kp_info, videos)
        else:
            self.handle_movie(pack_path, kp_code, kp_info, videos)

    def classify(self, pack_name, videos, kp_info) -> bool:
        guessed = detect_series(videos)
        if kp_is_series(kp_info):
            return True
        return guessed

    def handle_series(self, pack_path, kp_code, kp_info, videos):
        pack_name = os.path.basename(pack_path)

        show_title = build_tvshow_title(kp_info, pack_name)
        dest_root = os.path.join(self.paths.shows, show_title)

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
                    if not os.path.exists(poster_path) or fs_utils.DRY_RUN:
                        if fs_utils.DRY_RUN:
                            logging.info("DRY-RUN write show poster %s", poster_path)
                        else:
                            ensure_dir(os.path.dirname(poster_path))
                            try:
                                with open(poster_path, "wb") as f:
                                    f.write(data)
                                logging.info("SHOW POSTER: %s <- %s", poster_path, poster_url)
                            except Exception as e:
                                logging.warning("SHOW POSTER WRITE ERROR: %s", e)

        videos_sorted = sorted(videos)
        ep_index = build_episode_index(kp_info)
        stills: list[str] = []
        if kp_info:
            kp_id = kp_info.get("kinopoiskId") or kp_info.get("filmId") or kp_info.get("id")
            try:
                kp_id_int = int(kp_id) if kp_id else None
            except Exception:
                kp_id_int = None
            if kp_id_int:
                stills = kp_fetch_stills(kp_id_int)

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

    def handle_movie(self, pack_path, kp_code, kp_info, videos):
        pack_name = os.path.basename(pack_path)
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
            dest_dir_name = clean_title_for_kp(pretty.strip())

        dest_dir = os.path.join(self.paths.movies, dest_dir_name)
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
                    if not os.path.exists(poster_path) or fs_utils.DRY_RUN:
                        if fs_utils.DRY_RUN:
                            logging.info("DRY-RUN write movie poster %s", poster_path)
                        else:
                            ensure_dir(os.path.dirname(poster_path))
                            try:
                                with open(poster_path, "wb") as f:
                                    f.write(data)
                                logging.info("MOVIE POSTER: %s <- %s", poster_path, poster_url)
                            except Exception as e:
                                logging.warning("MOVIE POSTER WRITE ERROR: %s", e)
