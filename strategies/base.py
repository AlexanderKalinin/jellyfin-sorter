import os
import logging
from abc import ABC, abstractmethod

from core.config import CategoryPaths
from core.scanner import scan_videos, detect_series
from core.title_cleaner import clean_title_for_kp, extract_year_from_name
from core.kinopoisk import (
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
from core.scanner import EPISODE_RE


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
        # сюда переносишь твою handle_series_pack, заменяя глобальные пути на self.paths
        ...

    def handle_movie(self, pack_path, kp_code, kp_info, videos):
        # сюда переносишь твою handle_movie_pack, заменяя MOVIES_DIR на self.paths.movies
        ...
