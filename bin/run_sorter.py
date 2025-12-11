#!/usr/bin/env python3
import os
import sys
import logging

# === починка импорта core/* и strategies/* ===
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from core.config import load_config, get_categories, get_paths
from core.logging_setup import setup_logging
import core.fs_utils as fs_utils
from strategies.main_strategy import MainStrategy
from strategies.kids_strategy import KidsStrategy
from strategies.adult_strategy import AdultStrategy

STRATEGY_MAP = {
    "main": MainStrategy,
    "kids": KidsStrategy,
    "adult": AdultStrategy,
}


def main():
    cfg = load_config()
    paths_cfg = get_paths(cfg)
    log_file = paths_cfg["log_file"]

    setup_logging(log_file)

    dry_run = "--dry-run" in sys.argv
    fs_utils.DRY_RUN = dry_run  # чтобы move/cleanup тоже работали в dry-run

    print("sorter start")
    logging.info("SORTER: sorter start")

    categories = get_categories(cfg)

    for name, cat_paths in categories.items():
        strat_cls = STRATEGY_MAP.get(name, MainStrategy)
        strategy = strat_cls(cat_paths, dry_run=dry_run)

        data_dir = cat_paths.data
        if not os.path.isdir(data_dir):
            logging.info("SKIP CATEGORY %s: no data dir %s", name, data_dir)
            print(f"SKIP CATEGORY {name}: no data dir {data_dir}")
            continue

        print(f"=== CATEGORY: {name} ({data_dir}) ===")
        logging.info("CATEGORY START: %s (%s)", name, data_dir)

        for entry in sorted(os.listdir(data_dir)):
            full = os.path.join(data_dir, entry)
            print(f"PROCESS PACK: {full}")
            logging.info("PROCESS PACK: %s", full)
            try:
                strategy.process_pack(full)
            except Exception as e:
                logging.exception("ERROR processing %s: %s", full, e)
                print(f"ERROR processing {full}: {e}")

        fs_utils.cleanup_empty_dirs(data_dir)

    logging.info("SORTER DONE")
    print("sorter done")


if __name__ == "__main__":
    main()
