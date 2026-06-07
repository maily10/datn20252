import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from logger import log
from utils.utils import get_config
from crawler.factory import get_crawler


def _load_done_urls() -> set:
    done = set()
    csv_path = ROOT / "vnstocknewsdata" / "news_links.csv"
    if not csv_path.exists():
        return done
    with open(csv_path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            url = (row.get("url") or "").strip()
            if url:
                done.add(url)
    return done


def main(config_fpath: str):
    config = get_config(config_fpath)
    log.setup_logging(
        log_dir=config["output_dpath"],
        config_fpath=config["logger_fpath"],
    )
    logger = log.get_logger(__name__)
    logger.info(f"Starting crawl with config: {config}")

    config["done_urls"] = _load_done_urls()
    if config["done_urls"]:
        logger.info(f"[Resume] {len(config['done_urls'])} URL da co, se bo qua")

    crawler = get_crawler(**config)
    crawler.start_crawling()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Stock News URL Crawler — collects article URLs from Vietnamese financial news sites"
    )
    parser.add_argument(
        "--config",
        default="crawler_config.yml",
        dest="config_fpath",
        help="path to YAML config file (default: crawler_config.yml)",
    )
    args = parser.parse_args()
    main(**vars(args))
