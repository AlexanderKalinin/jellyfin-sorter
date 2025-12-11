import os
import json
from dataclasses import dataclass
from typing import Dict, Any

CONFIG_PATH = "/opt/jellyfin-sorter/config.json"


@dataclass
class CategoryPaths:
    name: str
    data: str
    movies: str
    shows: str
    vr: str | None = None


def load_config() -> Dict[str, Any]:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def get_base(cfg: Dict[str, Any]) -> str:
    return cfg.get("base_path", "/mnt/WD").rstrip("/")


def get_paths(cfg: Dict[str, Any]) -> Dict[str, str]:
    base = get_base(cfg)
    p = cfg.get("paths", {})
    return {
        "log_file": os.path.join(base, p.get("log_file", "logs/jellyfin-sorter.log")),
        "kp_cache": os.path.join(base, p.get("kp_cache", "logs/kp_cache.json")),
        "kp_usage": os.path.join(base, p.get("kp_usage", "logs/kp_usage.json")),
    }


def get_categories(cfg: Dict[str, Any]) -> Dict[str, CategoryPaths]:
    base = get_base(cfg)
    out: Dict[str, CategoryPaths] = {}
    cats = cfg.get("categories", {})
    for name, c in cats.items():
        def full(rel: str | None) -> str | None:
            if not rel:
                return None
            return os.path.join(base, rel.lstrip("/"))

        out[name] = CategoryPaths(
            name=name,
            data=full(c["data"]),
            movies=full(c["movies"]),
            shows=full(c["shows"]),
            vr=full(c.get("vr")),
        )
    return out
