"""
run_tag.py — Entrypoint bước (1): GẮN MÃ cổ phiếu VN30 cho từng tin.

Đọc news_links.csv + news_content.csv → với mỗi bài tìm mã VN30 được nhắc tới
→ xuất news_stock_mapping.csv (news_id, symbol).
Bài không khớp mã nào → 1 dòng symbol = "MARKET" (tin thị trường chung).

Cách dùng:
  python run_tag.py
  python run_tag.py --limit 500          # test nhanh
"""
import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from lib.ticker_tagger import TickerTagger

CRAWLER_ROOT = ROOT.parents[1]                       # test/news_sentiment → crawler/
NEWS_DIR = CRAWLER_ROOT / "stocknewscrawl" / "vnstocknewsdata"
OUT_DIR = ROOT / "output"
MARKET = "MARKET"


def main(limit: int):
    links = pd.read_csv(NEWS_DIR / "news_links.csv", dtype=str).fillna("")
    content = pd.read_csv(NEWS_DIR / "news_content.csv", dtype=str).fillna("")
    df = links.merge(content[["news_id", "summary", "content"]],
                     left_on="id", right_on="news_id", how="left").fillna("")
    if limit:
        df = df.head(limit)
    print(f"Số bài xử lý: {len(df)}")

    tagger = TickerTagger.from_config()

    rows = []
    n_tagged = n_market = 0
    for r in df.itertuples():
        text = f"{r.title}\n{r.summary}\n{r.content}"
        syms = tagger.tag(text)
        nid = r.id
        if syms:
            n_tagged += 1
            for s in syms:
                rows.append({"news_id": nid, "symbol": s})
        else:
            n_market += 1
            rows.append({"news_id": nid, "symbol": MARKET})

    out = pd.DataFrame(rows)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "news_stock_mapping.csv"
    out.to_csv(out_path, index=False, encoding="utf-8")

    print(f"\nBài gắn được mã: {n_tagged} | tin thị trường chung (MARKET): {n_market}")
    print(f"Tổng liên kết (news_id, symbol): {len(out)}")
    print(f"Đã ghi: {out_path}")
    print("\nTop mã được nhắc nhiều nhất:")
    print(out[out["symbol"] != MARKET]["symbol"].value_counts().head(10).to_string())


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Gắn mã VN30 cho tin tức")
    p.add_argument("--limit", type=int, default=0, help="0 = tất cả; >0 để test")
    args = p.parse_args()
    main(args.limit)
