"""
run_sentiment.py — Entrypoint bước (2): CHẤM SENTIMENT pos/neg/neutral cho tin.

Đọc news_links.csv (title) + news_content.csv (summary) → chấm sắc thái bằng
mô hình sentiment tiếng Việt → xuất news_sentiment.csv.
Dùng title + summary (đủ bắt sắc thái, nhanh hơn full content).

Hỗ trợ resume: bỏ qua news_id đã có trong news_sentiment.csv.

Cách dùng:
  python run_sentiment.py --limit 200         # test nhanh
  python run_sentiment.py --batch-size 32
  python run_sentiment.py --model 5CD-AI/Vietnamese-Sentiment-visobert
"""
import argparse
import sys
from pathlib import Path

import pandas as pd
from tqdm import tqdm

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from lib.sentiment_scorer import SentimentScorer

CRAWLER_ROOT = ROOT.parents[1]
NEWS_DIR = CRAWLER_ROOT / "stocknewscrawl" / "vnstocknewsdata"
OUT_DIR = ROOT / "output"


def main(limit: int, batch_size: int, model: str,
         hybrid: bool = False, alpha: float | None = None,
         tau: float | None = None, k: float | None = None):
    links = pd.read_csv(NEWS_DIR / "news_links.csv", dtype=str).fillna("")
    content = pd.read_csv(NEWS_DIR / "news_content.csv", dtype=str).fillna("")
    df = links.merge(content[["news_id", "summary"]],
                     left_on="id", right_on="news_id", how="left").fillna("")
    df["text"] = (df["title"] + ". " + df["summary"]).str.strip()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / ("news_sentiment_hybrid.csv" if hybrid else "news_sentiment.csv")

    # Resume: bỏ news_id đã chấm
    done = set()
    if out_path.exists():
        done = set(pd.read_csv(out_path, dtype=str)["news_id"])
        print(f"[Resume] đã có {len(done)} bài, bỏ qua.")
    df = df[~df["id"].isin(done)]
    if limit:
        df = df.head(limit)
    print(f"Số bài cần chấm: {len(df)}")
    if df.empty:
        print("Không có gì để làm.")
        return

    # Hybrid (Hướng A): nạp tham số method từ evaluate.py (method_config.json)
    if hybrid:
        import json

        from lib.hybrid_scorer import HybridSentimentScorer
        cfg_path = OUT_DIR / "method_config.json"
        cfg = json.loads(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}
        a = alpha if alpha is not None else cfg.get("alpha", 0.6)
        kk = k if k is not None else cfg.get("k", 1.0)
        t = tau if tau is not None else cfg.get("tau_for_3cls_view", 0.05)
        print(f"[Hybrid] α={a}, k={kk}, τ(view 3 lớp)={t}")
        scorer = HybridSentimentScorer(model_name=model, alpha=a, k=kk, tau=t)
        header = ("news_id,score,polarity,label_3cls,model_score,lex_net,"
                  "prob_negative,prob_neutral,prob_positive\n")
    else:
        scorer = SentimentScorer(model_name=model)
        header = "news_id,label,score,prob_negative,prob_neutral,prob_positive\n"

    texts = df["text"].tolist()
    ids = df["id"].tolist()
    write_header = not out_path.exists()
    with open(out_path, "a", encoding="utf-8", newline="") as f:
        if write_header:
            f.write(header)
        for start in tqdm(range(0, len(texts), batch_size), desc="Sentiment"):
            batch = texts[start:start + batch_size]
            bids = ids[start:start + batch_size]
            res = scorer.score_batch(batch, batch_size=batch_size)
            for nid, r in zip(bids, res):
                if hybrid:
                    f.write(f"{nid},{r.score},{r.polarity},{r.label_3cls},{r.model_score},{r.lex_net},"
                            f"{r.probs['negative']},{r.probs['neutral']},{r.probs['positive']}\n")
                else:
                    f.write(f"{nid},{r.label},{r.score},"
                            f"{r.probs['negative']},{r.probs['neutral']},{r.probs['positive']}\n")
            f.flush()

    final = pd.read_csv(out_path)
    print(f"\nĐã ghi {len(final)} bài → {out_path}")
    if hybrid:
        print("Phân bố polarity (chính):")
        print(final["polarity"].value_counts().to_string())
        print("Phân bố label_3cls (view):")
        print(final["label_3cls"].value_counts().to_string())
    else:
        print("Phân bố nhãn:")
        print(final["label"].value_counts().to_string())


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Chấm sentiment cho tin tức")
    p.add_argument("--limit", type=int, default=0, help="0 = tất cả; >0 để test")
    p.add_argument("--batch-size", type=int, default=16)
    p.add_argument("--model", default="wonrax/phobert-base-vietnamese-sentiment")
    p.add_argument("--hybrid", action="store_true",
                   help="Hướng A: lai ghép model + từ điển tài chính (dùng config tối ưu)")
    p.add_argument("--alpha", type=float, default=None, help="ghi đè α (mặc định lấy từ config)")
    p.add_argument("--tau", type=float, default=None, help="ghi đè τ")
    p.add_argument("--k", type=float, default=None, help="ghi đè k")
    args = p.parse_args()
    main(args.limit, args.batch_size, args.model,
         hybrid=args.hybrid, alpha=args.alpha, tau=args.tau, k=args.k)
