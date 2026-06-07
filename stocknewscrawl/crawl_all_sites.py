"""
crawl_all_sites.py
==================
Chạy URL crawler cho TẤT CẢ 4 nguồn báo một lần.

Mỗi site được lưu vào thư mục tạm riêng (result/{site}/urls/) để tránh
ghi đè nhau khi nhiều site có category cùng tên (vd: Thi_truong.txt),
sau đó toàn bộ URL được gộp vào result/urls/ với prefix tên site.

Cách dùng:
  python crawl_all_sites.py                          # crawl 4 site
  python crawl_all_sites.py --sites vneconomy        # chỉ 1 site
  python crawl_all_sites.py --config crawler_config.yml --sites vneconomy baodautu
"""

import argparse
import csv
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from logger import log
from utils.utils import get_config, create_dir
from crawler.factory import get_crawler

ALL_SITES = ["vneconomy", "baodautu", "thoibaotaichinh", "thitruongtaichinh"]


def _load_done_urls() -> set:
    """Đọc news_links.csv hiện có để bỏ qua URL đã crawl ngay từ bước thu thập."""
    done = set()
    csv_path = ROOT / "vnstocknewsdata" / "news_links.csv"
    if not csv_path.exists():
        return done
    with open(csv_path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            url = (row.get("url") or "").strip()
            if url:
                done.add(url)
    return done


def run_site(site: str, base_config: dict, done_urls: set) -> int:
    """
    Chạy URL crawler cho 1 site.
    URLs tạm lưu ở result/{site}/urls/
    Sau đó merge vào result/urls/{site}_{category}.txt
    Trả về số URL duy nhất tìm được.
    """
    site_config = base_config.copy()
    site_config["webname"] = site
    site_config["output_dpath"] = f"result/{site}"
    site_config["done_urls"] = done_urls

    print(f"\n{'='*55}")
    print(f"  Dang crawl URLs: {site}  (total_pages={site_config['total_pages']})")
    print(f"{'='*55}")

    try:
        crawler = get_crawler(**site_config)
        crawler.start_crawling()
    except Exception as e:
        print(f"  [ERROR] {site} crawler failed: {e}")
        return 0

    # Merge per-site URLs vào result/urls/ với tên {site}_{category}.txt
    src_dir = ROOT / f"result/{site}/urls"
    dst_dir = ROOT / "result/urls"
    dst_dir.mkdir(parents=True, exist_ok=True)

    merged = 0
    total_urls = 0
    if src_dir.exists():
        for txt_file in sorted(src_dir.glob("*.txt")):
            dst_file = dst_dir / f"{site}_{txt_file.name}"
            shutil.copy2(txt_file, dst_file)
            # Đếm URL trong file
            with open(dst_file, encoding="utf-8") as f:
                count = sum(1 for line in f if line.strip())
            total_urls += count
            merged += 1
            print(f"  Merged: {txt_file.name} ({count} URLs) → {dst_file.name}")

    print(f"  [{site}] Tong: {total_urls} URLs tu {merged} categories")
    return total_urls


def count_unique_urls(urls_dir: Path) -> int:
    """Đếm tổng URL duy nhất trong toàn bộ thư mục urls/."""
    seen = set()
    for f in sorted(urls_dir.glob("*.txt")):
        with open(f, encoding="utf-8") as fp:
            for line in fp:
                url = line.strip()
                if url:
                    seen.add(url)
    return len(seen)


def main(config_fpath: str, sites: list):
    config = get_config(config_fpath)

    # Setup logging (dùng thư mục result gốc)
    log.setup_logging(
        log_dir=config["output_dpath"],
        config_fpath=config["logger_fpath"],
    )

    done_urls = _load_done_urls()
    if done_urls:
        print(f"[Resume] Da co {len(done_urls)} URL trong news_links.csv, se bo qua khi thu thap.")

    site_totals = {}
    for site in sites:
        n = run_site(site, config, done_urls)
        site_totals[site] = n

    # Tổng kết
    urls_dir = ROOT / "result/urls"
    total_unique = count_unique_urls(urls_dir)

    print(f"\n{'='*55}")
    print(f"  HOAN THANH CRAWL URLS")
    print(f"{'='*55}")
    for site, n in site_totals.items():
        print(f"  {site:<25}: {n:>6} URLs")
    print(f"  {'─'*35}")
    print(f"  {'Tong URLs duy nhat':<25}: {total_unique:>6}")
    print(f"\n  Tat ca URLs luu tai: result/urls/")
    print(f"\n  Buoc tiep theo:")
    print(f"    python crawl_content.py --start-date 2025-01-01")
    print(f"{'='*55}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Crawl URLs tu tat ca cac site tin tuc tai chinh Viet Nam"
    )
    parser.add_argument(
        "--config",
        default="crawler_config.yml",
        dest="config_fpath",
        help="duong dan toi file config YAML (mac dinh: crawler_config.yml)",
    )
    parser.add_argument(
        "--sites",
        nargs="+",
        default=ALL_SITES,
        choices=ALL_SITES,
        metavar="SITE",
        help=f"danh sach site can crawl (mac dinh: tat ca). Chon tu: {ALL_SITES}",
    )
    args = parser.parse_args()
    main(args.config_fpath, args.sites)
