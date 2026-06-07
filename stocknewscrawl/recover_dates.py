"""
recover_dates.py
================
Khôi phục published_at / published_date cho các bài đã crawl nhưng BỊ RỖNG ngày
(do bug thứ tự gọi extract_best_content trước khi đọc date — đã fix trong
content_crawler/*). Re-fetch lại trang từng bài, trích ngày bằng content crawler
đã sửa, rồi cập nhật news_links.csv IN-PLACE (ghi atomic qua file .tmp).

Mặc định chỉ xử lý 2 nguồn từng lỗi: Báo Đầu Tư + Thời Báo Tài Chính Việt Nam.

Cách dùng:
  python recover_dates.py                      # khôi phục mọi bài rỗng ngày của 2 nguồn
  python recover_dates.py --workers 8
  python recover_dates.py --limit 50           # test nhanh 50 bài
"""

import argparse
import concurrent.futures
import os
import sys
import time
from pathlib import Path
from threading import Lock

import pandas as pd
from tqdm import tqdm

# Windows console mặc định cp1252 → ép UTF-8 để in tiếng Việt không lỗi
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from content_crawler.factory import get_content_crawler

LINKS_CSV = ROOT / "vnstocknewsdata" / "news_links.csv"
TARGET_SOURCES = {"Báo Đầu Tư", "Thời Báo Tài Chính Việt Nam"}


def fetch_date(url: str, retries: int = 2) -> tuple[str, str]:
    """Re-fetch 1 bài, trả (published_at, published_date). ("","") nếu fail.
    Retry tối đa `retries` lần (baodautu.vn hay timeout khi tải đồng thời)."""
    crawler = get_content_crawler(url)
    if crawler is None:
        return "", ""
    for attempt in range(retries + 1):
        try:
            art = crawler.extract_article(url)
            if art and art.get("published_date"):
                return art.get("published_at", "") or "", art.get("published_date", "") or ""
        except Exception:
            pass
        if attempt < retries:
            time.sleep(0.6 * (attempt + 1))  # backoff nhẹ giữa các lần thử
    return "", ""


def main(workers: int, limit: int):
    if not LINKS_CSV.exists():
        print(f"[ERROR] không thấy {LINKS_CSV}")
        sys.exit(1)

    df = pd.read_csv(LINKS_CSV, dtype=str).fillna("")
    print(f"Tổng news_links: {len(df)}")

    # Các dòng cần khôi phục: thuộc 2 nguồn + published_at rỗng
    mask = df["source"].isin(TARGET_SOURCES) & (df["published_at"].str.strip() == "")
    todo_idx = df.index[mask].tolist()
    if limit:
        todo_idx = todo_idx[:limit]
    print(f"Cần khôi phục ngày: {len(todo_idx)} bài "
          f"({', '.join(sorted(TARGET_SOURCES))})")
    if not todo_idx:
        print("Không có gì để làm.")
        return

    lock = Lock()
    ok = [0]
    fail = [0]

    def work(idx):
        url = df.at[idx, "url"]
        pub_at, pub_date = fetch_date(url)
        with lock:
            if pub_date:
                df.at[idx, "published_at"] = pub_at
                df.at[idx, "published_date"] = pub_date
                ok[0] += 1
            else:
                fail[0] += 1

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        list(tqdm(ex.map(work, todo_idx), total=len(todo_idx), desc="Recover dates"))

    print(f"\nKhôi phục OK : {ok[0]}")
    print(f"Vẫn fail     : {fail[0]}")

    # Ghi atomic: tmp → replace, tránh hỏng file nếu gián đoạn
    tmp = LINKS_CSV.with_suffix(".csv.tmp")
    df.to_csv(tmp, index=False)
    os.replace(tmp, LINKS_CSV)
    print(f"Đã cập nhật {LINKS_CSV}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Khôi phục ngày cho bài bị rỗng (Báo Đầu Tư + Thời Báo TC)")
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--limit", type=int, default=0, help="0 = tất cả; >0 để test")
    args = p.parse_args()
    main(args.workers, args.limit)
