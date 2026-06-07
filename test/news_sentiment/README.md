# news_sentiment — Gắn mã & chấm sentiment cho tin tức (Mốc 2)

Module xử lý tin tức cho đồ án *"Đánh giá tương quan thay đổi giá chứng khoán với tin tức"*,
thực hiện 2 bước của Nội dung 2:

1. **Gắn mã** — mỗi tin nói về (các) mã VN30 nào.
2. **Sentiment** — chấm điểm cực tính cho mỗi tin bằng *Hướng A: hybrid PhoBERT + từ điển tài chính*.

📄 **Báo cáo chi tiết sentiment (method, triển khai, kết quả chứng minh):
[HUONG_A_HYBRID_SENTIMENT.md](HUONG_A_HYBRID_SENTIMENT.md)**

## Cấu trúc

```
news_sentiment/
├── config/
│   ├── vn30_companies.yml      # từ điển 30 mã VN30 (gắn mã)
│   └── finance_lexicon.yml     # ★ từ điển tài chính 122 cụm (sentiment)
├── lib/
│   ├── ticker_tagger.py        # gắn mã — rule-based
│   ├── sentiment_scorer.py     # wrapper PhoBERT
│   ├── finance_lexicon.py      # đọc & chấm lexicon (+ phủ định)
│   └── hybrid_scorer.py        # ★ fusion: s(t) = (1−α)·model + α·tanh(k·net)
├── data/
│   ├── raw_data.xlsx           # nguồn gold (CafeF 1005)
│   └── gold_cafef.csv          # gold đã chuẩn hoá
├── output/
│   ├── method_config.json      # tham số method đã tinh chỉnh
│   ├── eval_results.csv        # dự đoán trên test (proof số liệu)
│   ├── news_stock_mapping.csv  # quan hệ tin ↔ mã
│   └── news_sentiment_hybrid.csv  # sentiment toàn corpus
├── prepare_gold.py             # tạo gold_cafef.csv
├── evaluate.py                 # ★ tinh chỉnh & đánh giá method trên gold
├── run_tag.py                  # gắn mã toàn corpus
└── run_sentiment.py            # chấm sentiment toàn corpus (có --hybrid)
```

## Đầu vào

Đọc từ `../../stocknewscrawl/vnstocknewsdata/`:
- `news_links.csv`   (id, title, source, published_at, ...)
- `news_content.csv` (news_id, content, summary, ...)

## Cách chạy

```bash
cd test/news_sentiment

# (1) Gắn mã VN30
python run_tag.py                  # toàn bộ; --limit N để test

# (2a) Tinh chỉnh & đánh giá Hướng A trên gold set (một lần)
python prepare_gold.py             # gold_cafef.csv từ raw_data.xlsx
python evaluate.py                 # → method_config.json + eval_results.csv

# (2b) Chấm sentiment toàn corpus
python run_sentiment.py --hybrid   # dùng tham số trong method_config.json
python run_sentiment.py            # (model thuần, không khuyến nghị — chỉ để đối chứng)
```

## Tóm tắt kết quả

| | Polarity (pos/neg) | 3 lớp đầy đủ |
|---|---|---|
| PhoBERT thuần | 81.5% acc / F1 0.767 | 59.3% acc / F1 0.545 |
| **Hybrid (Hướng A)** | **87.2% acc / F1 0.827** | 64.6% acc / F1 0.583 |

Polarity là **mục tiêu vận hành** (Tetlock 2007; Loughran-McDonald 2011 — sentiment tài chính
mang tính HƯỚNG); 3 lớp báo cáo song song cho minh bạch. Chi tiết tại
[HUONG_A_HYBRID_SENTIMENT.md](HUONG_A_HYBRID_SENTIMENT.md).

## Đầu ra (thư mục `output/`)

**`news_stock_mapping.csv`** — quan hệ nhiều-nhiều tin ↔ mã:
| Cột | Mô tả |
|---|---|
| `news_id` | khoá tin |
| `symbol` | mã VN30, hoặc `MARKET` nếu là tin thị trường chung |

**`news_sentiment_hybrid.csv`** — sentiment mỗi tin (Hướng A):
| Cột | Mô tả |
|---|---|
| `news_id` | khoá tin |
| `score` | **`s(t) ∈ [−1, 1]`** — output method (dùng cho Mốc 4) |
| `polarity` | view nhị phân (`positive`/`negative` theo dấu) |
| `label_3cls` | view 3 lớp qua ngưỡng τ |
| `model_score`, `lex_net` | thành phần (debug/giải thích) |
| `prob_negative/neutral/positive` | xác suất 3 lớp của model |

## Bước tiếp theo (Mốc 4 — tương quan)

Join 2 file trên theo `news_id` → tổng hợp `(symbol, ngày)`:
`mean_sentiment = mean(score)`, `n_news`. Sau đó đối chiếu với điểm thay đổi giá (PELT) bằng
coverage / tỷ lệ khớp hướng / hệ số tương quan. **Dùng thẳng `score` liên tục, không rời rạc hoá**.
