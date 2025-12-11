import os
import logging
from .base import DefaultCategoryStrategy
from core.scanner import scan_videos
from core.title_cleaner import (
    clean_title_for_kp,
    sanitize_fs_name,
)
from core.kinopoisk import build_movie_basename
from core.fs_utils import move_with_subs

def is_vr_pack(pack_name: str, videos: list[str]) -> bool:
    name = pack_name.lower()
    if "vr" in name or "oculus" in name:
        return True
    for v in videos:
        fn = os.path.basename(v).lower()
        if "vr" in fn or "oculus" in fn:
            return True
    return False


class AdultStrategy(DefaultCategoryStrategy):
    def handle_movie(self, pack_path, kp_code, kp_info, videos):
        pack_name = os.path.basename(pack_path)
        videos = scan_videos(pack_path)

        vr = is_vr_pack(pack_name, videos)
        base_root = self.paths.vr if vr and self.paths.vr else self.paths.movies

        cleaned = clean_title_for_kp(pack_name)
        movie_base = build_movie_basename(kp_info)

        if movie_base:
            dest_dir_name = movie_base
        else:
            pretty = pack_name
            if cleaned:
                pretty = cleaned
            dest_dir_name = sanitize_fs_name(pretty.strip())

        dest_dir = os.path.join(base_root, dest_dir_name)
        logging.info("MOVIE DIR: %s -> %s", pack_path, dest_dir)
        print(f"MOVIE DIR: {pack_path} -> {dest_dir}")

        # перенос файлов (твоя логика из handle_movie_pack)
        ...
