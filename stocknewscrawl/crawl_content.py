"""
crawl_content.py
================
Đọc tất cả URL từ result/urls/*.txt, crawl nội dung từng bài báo,
rồi xuất 2 file CSV vào thư mục vnstocknewsdata/:

  news_links.csv   → id, url, title, source, published_at, published_date, status, created_at
  news_content.csv → news_id, content, summary, image_url, created_at

Cách dùng:
  python crawl_content.py [--urls-dir result/urls] [--output-dir vnstocknewsdata]
                          [--workers 5] [--limit 0]
                          [--start-date 2025-01-01] [--end-date ""]

  --urls-dir   : thư mục chứa các file .txt URL (mặc định: result/urls)
  --output-dir : thư mục xuất CSV (mặc định: vnstocknewsdata)
  --workers    : số luồng song song (mặc định: 5)
  --limit      : giới hạn số URL mỗi file (0 = không giới hạn, dùng khi test)
  --start-date : ngày sớm nhất (YYYY-MM-DD). Mặc định: 2025-01-01.
                 Bài có published_date < start_date sẽ bị bỏ.
  --end-date   : ngày muộn nhất (YYYY-MM-DD). Mặc định "" (= không giới hạn).
                 Bài có published_date > end_date sẽ bị bỏ.
"""

import argparse
import csv
import concurrent.futures
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from tqdm import tqdm

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from content_crawler.factory import get_content_crawler
from content_crawler.content_utils import check_article

# ──────────────────────────────────────────────
# CSV column definitions
# ──────────────────────────────────────────────
NEWS_LINKS_COLS = [
    "id", "url", "title", "source",
    "published_at", "published_date", "status", "created_at"
]
NEWS_CONTENT_COLS = [
    "news_id", "content", "summary", "image_url", "created_at"
]


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def _load_done_urls(links_csv: Path) -> set:
    """Load already-crawled URLs from existing CSV to support resuming."""
    done = set()
    if links_csv.exists():
        with open(links_csv, encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                done.add(row.get("url", "").strip())
    return done


def _check_date_range(published_date: str, start_date: str, end_date: str) -> bool:
    """
    Trả về True nếu published_date nằm trong [start_date, end_date].
    Cả 2 đầu là YYYY-MM-DD; "" = không giới hạn ở phía đó.
    Bài thiếu ngày → cho phép (nhượng bộ).
    """
    if not published_date:
        return True
    d = str(published_date).strip()[:10]
    if start_date and d < start_date:
        return False
    if end_date and d > end_date:
        return False
    return True


def _load_urls_from_dir(urls_dir: Path, limit: int = 0) -> list:
    """Read all .txt files in urls_dir and return unique URL list."""
    all_urls = []
    seen = set()
    for txt_file in sorted(urls_dir.glob("*.txt")):
        count = 0
        with open(txt_file, encoding="utf-8") as f:
            for line in f:
                url = line.strip()
                if url and url not in seen:
                    all_urls.append(url)
                    seen.add(url)
                    count += 1
                    if limit and count >= limit:
                        break
        print(f"  Loaded {count} URLs from {txt_file.name}")
    return all_urls


# ──────────────────────────────────────────────
# Core crawl
# ──────────────────────────────────────────────

def crawl_one(url: str, news_id: int):
    """Crawl a single URL. Returns (links_row dict, content_row dict) or None."""
    crawler = get_content_crawler(url)
    if crawler is None:
        return None  # unsupported domain

    try:
        article = crawler.extract_article(url)
    except Exception:
        return None

    if article is None:
        return None

    now = _now_iso()

    links_row = {
        "id":             news_id,
        "url":            url,
        "title":          article.get("title", ""),
        "source":         article.get("source", ""),
        "published_at":   article.get("published_at", ""),
        "published_date": article.get("published_date", ""),
        "status":         "published",
        "created_at":     now,
    }
    content_row = {
        "news_id":    news_id,
        "content":    article.get("content", ""),
        "summary":    article.get("summary", ""),
        "image_url":  article.get("image_url", ""),
        "created_at": now,
    }
    return links_row, content_row


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────

def main(urls_dir: str, output_dir: str, workers: int, limit: int,
         start_date: str, end_date: str):
    urls_path = ROOT / urls_dir
    out_path  = ROOT / output_dir

    if not urls_path.exists():
        print(f"[ERROR] URLs directory not found: {urls_path}")
        sys.exit(1)

    out_path.mkdir(parents=True, exist_ok=True)
    links_csv   = out_path / "news_links.csv"
    content_csv = out_path / "news_content.csv"

    # ── Load existing data for resume support ──
    done_urls = _load_done_urls(links_csv)
    if done_urls:
        print(f"[Resume] {len(done_urls)} URLs already crawled, skipping them.")

    if start_date or end_date:
        lo = start_date or "(unbounded)"
        hi = end_date or "(no upper bound)"
        print(f"[Filter] Chi giu bai co published_date trong [{lo} .. {hi}].")

    # Determine starting ID
    start_id = len(done_urls) + 1

    # ── Load URLs ──
    print(f"\nLoading URLs from: {urls_path}")
    all_urls = _load_urls_from_dir(urls_path, limit)
    # Filter out already done
    pending = [u for u in all_urls if u not in done_urls]
    print(f"\nTotal URLs found : {len(all_urls)}")
    print(f"Already crawled  : {len(done_urls)}")
    print(f"Pending          : {len(pending)}\n")

    if not pending:
        print("Nothing to crawl. Exiting.")
        return

    # ── Open CSV files (append mode if resuming) ──
    write_header_links   = not links_csv.exists()
    write_header_content = not content_csv.exists()

    links_file   = open(links_csv,   "a", encoding="utf-8", newline="")
    content_file = open(content_csv, "a", encoding="utf-8", newline="")
    links_writer   = csv.DictWriter(links_file,   fieldnames=NEWS_LINKS_COLS,   extrasaction="ignore")
    content_writer = csv.DictWriter(content_file, fieldnames=NEWS_CONTENT_COLS, extrasaction="ignore")

    if write_header_links:
        links_writer.writeheader()
    if write_header_content:
        content_writer.writeheader()

    # Thread-safe write lock
    write_lock = Lock()
    id_counter = [start_id]   # mutable ref for counter inside closure
    success_count = [0]
    fail_count = [0]
    skip_old_count = [0]  # bai cu hon start_date
    skip_new_count = [0]  # bai moi hon end_date

    def process(url):
        nid = None
        with write_lock:
            nid = id_counter[0]
            id_counter[0] += 1

        result = crawl_one(url, nid)
        time.sleep(0.2)  # polite delay

        with write_lock:
            if result is None:
                fail_count[0] += 1
                return False
            links_row, content_row = result

            # ── Bo loc theo range [start_date, end_date] ──
            pub_date = (links_row.get("published_date", "") or "").strip()[:10]
            if not _check_date_range(pub_date, start_date, end_date):
                if start_date and pub_date and pub_date < start_date:
                    skip_old_count[0] += 1
                else:
                    skip_new_count[0] += 1
                return False

            links_writer.writerow(links_row)
            content_writer.writerow(content_row)
            links_file.flush()
            content_file.flush()
            success_count[0] += 1
            return True

    # ── Multi-threaded crawl ──
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        list(tqdm(executor.map(process, pending), total=len(pending), desc="Crawling articles"))

    links_file.close()
    content_file.close()

    print(f"\n{'='*60}")
    print(f"  Done!")
    print(f"  Success      : {success_count[0]}")
    print(f"  Failed       : {fail_count[0]}")
    print(f"  Skip (cu)    : {skip_old_count[0]}  (published_date < {start_date or 'N/A'})")
    print(f"  Skip (moi)   : {skip_new_count[0]}  (published_date > {end_date   or 'N/A'})")
    print(f"\n  Output files:")
    print(f"    {links_csv}")
    print(f"    {content_csv}")
    print(f"{'='*60}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Crawl article content from URLs and export to Supabase-ready CSVs"
    )
    parser.add_argument("--urls-dir",    default="result/urls",      help="Folder containing URL .txt files")
    parser.add_argument("--output-dir",  default="vnstocknewsdata",  help="Output folder for CSV files")
    parser.add_argument("--workers",     type=int, default=5,         help="Number of parallel threads")
    parser.add_argument("--limit",       type=int, default=0,         help="Max URLs per file (0=unlimited, use for testing)")
    parser.add_argument(
        "--start-date",
        default="2025-01-01",
        dest="start_date",
        help="Ngay som nhat (YYYY-MM-DD). Mac dinh: 2025-01-01. De '' de bo gioi han duoi.",
    )
    parser.add_argument(
        "--end-date",
        default="",
        dest="end_date",
        help="Ngay muon nhat (YYYY-MM-DD). Mac dinh '' (khong gioi han tren).",
    )
    args = parser.parse_args()
    main(args.urls_dir, args.output_dir, args.workers, args.limit,
         args.start_date, args.end_date)
