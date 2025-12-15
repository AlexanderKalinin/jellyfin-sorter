import logging
import os

import core.fs_utils as fs_utils
from core.fs_utils import ensure_dir, move_with_subs
from core.kinopoisk import build_movie_basename, http_binary
from core.nfo_writer import write_movie_nfo
from core.scanner import scan_videos
from core.title_cleaner import clean_title_for_kp, sanitize_fs_name
from .base import DefaultCategoryStrategy

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
            if cleaned and "[" in pack_name and "kp" not in pack_name.lower():
                pretty = cleaned
            if cleaned and len(cleaned) >= 3 and not any(c.isalpha() for c in pack_name):
                pretty = cleaned
            dest_dir_name = sanitize_fs_name(pretty.strip())

        dest_dir = os.path.join(base_root, dest_dir_name)
        logging.info("MOVIE DIR: %s -> %s", pack_path, dest_dir)
        print(f"MOVIE DIR: {pack_path} -> {dest_dir}")

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
