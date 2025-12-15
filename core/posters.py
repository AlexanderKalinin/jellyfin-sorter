import logging
import os

from . import fs_utils
from .kinopoisk import http_binary


def download_episode_thumb(dest_video_path: str, img_url: str) -> None:
    data = http_binary(img_url)
    if not data:
        return

    folder = os.path.dirname(dest_video_path)
    base = os.path.splitext(os.path.basename(dest_video_path))[0]
    img_path = os.path.join(folder, f"{base}-thumb.jpg")

    if os.path.exists(img_path) and not fs_utils.DRY_RUN:
        return

    fs_utils.ensure_dir(os.path.dirname(img_path))
    if fs_utils.DRY_RUN:
        logging.info("DRY-RUN write thumb %s", img_path)
        return

    try:
        with open(img_path, "wb") as f:
            f.write(data)
        logging.info("EP THUMB: %s <- %s", img_path, img_url)
    except Exception as e:
        logging.warning("EP THUMB WRITE ERROR: %s", e)


def ensure_season_poster(show_root: str, season_dir: str) -> None:
    folder_poster = os.path.join(show_root, "folder.jpg")
    if not os.path.exists(folder_poster):
        return

    season_poster = os.path.join(season_dir, "folder.jpg")
    if os.path.exists(season_poster) and not fs_utils.DRY_RUN:
        return

    fs_utils.ensure_dir(season_dir)
    if fs_utils.DRY_RUN:
        logging.info("DRY-RUN copy season poster %s -> %s", folder_poster, season_poster)
        return

    try:
        with open(folder_poster, "rb") as src:
            data = src.read()
        with open(season_poster, "wb") as dst:
            dst.write(data)
        logging.info("SEASON POSTER: %s <- base poster", season_poster)
    except Exception as e:
        logging.warning("SEASON POSTER ERROR: %s", e)
