"""
collect_sitemap_vn30.py
=======================
Thu thập URL bài viết Báo Đầu Tư từ SITEMAP THEO THÁNG (baodautu.vn có sitemap
2013→2026, dùng để lấy bài lịch sử mà phân trang chuyên mục bị chặn không tới).

Chỉ giữ bài có slug nhắc tới mã / tên thương hiệu VN30 → đúng trọng tâm thesis,
giảm mạnh số bài phải crawl (sitemap chứa MỌI chủ đề).

Dedup theo news_links.csv hiện có. Xuất URL ra result/urls_sitemap/baodautu_vn30.txt
để bước sau dùng crawl_content.py --urls-dir result/urls_sitemap.

Cách dùng:
  python collect_sitemap_vn30.py                       # 2022-01 → 2026-05
  python collect_sitemap_vn30.py --from 2022-01 --to 2026-05 --workers 6
"""

import argparse
import concurrent.futures
import re
import sys
from pathlib import Path

import requests

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent
LINKS_CSV = ROOT / "vnstocknewsdata" / "news_links.csv"
OUT_DIR = ROOT / "result" / "urls_sitemap"
SITEMAP_INDEX = "https://baodautu.vn/sitemap.xml"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

# ── Bộ từ điển VN30 (cố định) — ticker + slug thương hiệu thường gặp trên báo ──
VN30_TICKERS = [
    "ACB", "BCM", "BID", "BVH", "CTG", "FPT", "GAS", "GVR", "HDB", "HPG",
    "LPB", "MBB", "MSN", "MWG", "PLX", "SAB", "SHB", "SSB", "SSI", "STB",
    "TCB", "TPB", "VCB", "VHM", "VIB", "VIC", "VJC", "VNM", "VPB", "VRE",
]

# slug thương hiệu (ASCII, lowercase, đã bỏ dấu) — match dạng substring trong slug
VN30_BRAND_SLUGS = [
    "acb", "becamex", "bidv", "bao-viet", "vietinbank", "fpt",
    "pv-gas", "petrovietnam-gas", "cao-su-viet-nam", "hdbank", "hoa-phat",
    "lpbank", "lienvietpostbank", "mbbank", "ngan-hang-quan-doi", "masan",
    "the-gioi-di-dong", "mobile-world", "dien-may-xanh", "bach-hoa-xanh",
    "petrolimex", "sabeco", "bia-sai-gon", "seabank", "sacombank",
    "techcombank", "tpbank", "tien-phong-bank", "vietcombank",
    "vinhomes", "vingroup", "vietjet", "vinamilk", "vpbank", "vincom-retail",
    "vincom",
]
# Lưu ý: bỏ "cong-thuong"/"ngoai-thuong" vì khớp nhầm "Bộ Công Thương"/"Đại học Ngoại Thương".

# ticker dạng token (tách theo "-") — chỉ match khi đứng riêng để tránh false positive
TICKER_TOKENS = {t.lower() for t in VN30_TICKERS}


def slug_of(url: str) -> str:
    """Lấy phần slug cuối của URL baodautu, vd .../chung-khoan-x-d123.html → 'chung-khoan-x-d123'."""
    m = re.search(r"/([^/]+?)\.html$", url)
    return (m.group(1) if m else url).lower()


def is_vn30(url: str) -> bool:
    slug = slug_of(url)
    tokens = set(slug.split("-"))
    if tokens & TICKER_TOKENS:           # có token == ticker (fpt, hpg, vcb…)
        return True
    return any(b in slug for b in VN30_BRAND_SLUGS)   # hoặc chứa slug thương hiệu


def list_month_sitemaps(date_from: str, date_to: str) -> list[str]:
    """Đọc sitemap index, trả các sitemap tháng news-YYYY-M nằm trong khoảng [from, to]."""
    r = requests.get(SITEMAP_INDEX, timeout=20, headers=HEADERS)
    locs = re.findall(r"<loc>\s*(.*?)\s*</loc>", r.text, re.S)
    out = []
    for l in locs:
        m = re.search(r"news-(\d{4})-(\d{1,2})", l)
        if not m:
            continue
        ym = f"{int(m.group(1)):04d}-{int(m.group(2)):02d}"
        if date_from <= ym <= date_to:
            out.append((ym, l.strip()))
    return sorted(out)


def fetch_month_urls(sm_url: str) -> list[str]:
    """Lấy URL bài (.html) trong 1 sitemap tháng."""
    try:
        r = requests.get(sm_url, timeout=30, headers=HEADERS)
        locs = re.findall(r"<loc>\s*(.*?)\s*</loc>", r.text, re.S)
        return [u.strip() for u in locs if u.strip().endswith(".html")]
    except Exception:
        return []


def load_done_urls() -> set:
    done = set()
    if LINKS_CSV.exists():
        import csv
        with open(LINKS_CSV, encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                u = (row.get("url") or "").strip()
                if u:
                    done.add(u)
    return done


def main(date_from: str, date_to: str, workers: int):
    print(f"Khoảng tháng: {date_from} → {date_to}")
    months = list_month_sitemaps(date_from, date_to)
    print(f"Sitemap tháng phù hợp: {len(months)}")
    if not months:
        print("Không có sitemap tháng nào trong khoảng. Dừng.")
        return

    done = load_done_urls()
    print(f"URL đã có (dedup): {len(done)}")

    all_vn30 = []
    seen = set()
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        results = ex.map(lambda mu: (mu[0], fetch_month_urls(mu[1])), months)
        for ym, urls in results:
            vn30 = [u for u in urls if is_vn30(u)]
            new = [u for u in vn30 if u not in done and u not in seen]
            for u in new:
                seen.add(u)
            all_vn30.extend(new)
            print(f"  {ym}: {len(urls):4d} bài | VN30: {len(vn30):3d} | mới (sau dedup): {len(new):3d}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_file = OUT_DIR / "baodautu_vn30.txt"
    out_file.write_text("\n".join(all_vn30), encoding="utf-8")

    print(f"\nTổng URL VN30 mới cần crawl: {len(all_vn30)}")
    print(f"Đã ghi: {out_file}")
    print(f"\nBước tiếp:")
    print(f"  python crawl_content.py --urls-dir result/urls_sitemap --start-date {date_from[:4]}-01-01 --workers 4")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Thu thập URL VN30 từ sitemap baodautu")
    p.add_argument("--from", dest="date_from", default="2022-01", help="YYYY-MM")
    p.add_argument("--to", dest="date_to", default="2026-05", help="YYYY-MM")
    p.add_argument("--workers", type=int, default=6)
    args = p.parse_args()
    main(args.date_from, args.date_to, args.workers)
