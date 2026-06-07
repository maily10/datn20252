# 📊 Tổng Quan Workspace: `crawler`

> Hệ thống hoàn chỉnh xử lý tin tức tài chính Việt Nam — từ thu thập → NLP → phân tích cảm xúc → visualization.

---

## 🏗️ Kiến Trúc Tổng Quan

```
┌─────────────────────────────────────────────────────────────────────┐
│ Nguồn Tin Tức Tài Chính                                             │
│ vneconomy.vn | baodautu.vn | thoibaotaichinh.vn | thitruongtaichinh.vn │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                    ┌──────▼──────────┐
                    │ stocknewscrawl  │  (Web Crawler)
                    │ 5 workers       │  Threading + BS4
                    └──────┬──────────┘
                           │
                    ┌──────▼────────────────┐
                    │   news_content.csv    │
                    └──────┬────────────────┘
                           │
           ┌───────────────┼───────────────┐
           │               │               │
    ┌──────▼────────┐  ┌───▼──────────┐  ┌──▼──────────────┐
    │ Pho_bert_test │  │ Sentiment_   │  │ Volume_precedes │
    │ Gemini 5x vote│  │ analyst      │  │ _price          │
    │ PhoBERT FT    │  │ Translate    │  │ EDA + ML        │
    └──────┬────────┘  │ L-M Dict     │  │ HAR + RF + LGBM │
           │           └──────┬───────┘  └────────┬────────┘
           └──────────────────┼───────────────────┘
                              │
              ┌───────────────▼───────────┐
              │   uiweb Dashboard         │
              │   React 18 + Chart.js     │
              └───────────────────────────┘
```

---

## 📁 Các Module Chi Tiết

### 1. `stocknewscrawl/` — Web Crawler Chính

**Mục đích**: Crawl 4 nguồn tin tức tài chính, trích xuất URL → tải content → lưu CSV.

```
stocknewscrawl/
├── main.py                      # Entry point
├── crawl_all_sites.py           # Chạy cả 4 crawler cùng lúc
├── crawl_content.py             # Tải HTML + phân tích nội dung
├── crawler_config.yml           # Config: site, workers, pages
├── crawler/                     # Lớp trích xuất URL
│   ├── base_crawler.py          # Abstract + threading
│   ├── vneconomy.py
│   ├── baodautu.py
│   ├── thoibaotaichinh.py
│   ├── thitruongtaichinh.py
│   └── factory.py
├── content_crawler/             # Lớp trích xuất nội dung
│   ├── base_content_crawler.py
│   ├── vneconomy_content.py
│   ├── baodautu_content.py
│   ├── thoibaotaichinh_content.py
│   ├── thitruongtaichinh_content.py
│   ├── content_utils.py
│   └── factory.py
├── logger/
│   ├── log.py
│   └── logger_config.yml
├── result/
│   └── urls/                    # URL listing per site/category
└── vnstocknewsdata/
    └── news_content.csv         # ⭐ Output chính
```

**Cấu hình** (`crawler_config.yml`):
```yaml
num_workers: 5        # Concurrent threads
total_pages: 200      # Pages/category (~20 articles/page)
```

**Schema `news_content.csv`**:
| Cột | Mô tả |
|-----|-------|
| `news_id` | MD5 hash của URL |
| `title` | Tiêu đề bài |
| `summary` | Tóm tắt |
| `content` | Nội dung đầy đủ |
| `image_url` | Thumbnail |
| `source` | Tên nguồn |
| `published_at` | Ngày đăng |
| `created_at` | Thời điểm crawl |

**Lệnh chạy**:
```bash
python crawl_all_sites.py                              # Tất cả 4 site
python crawl_content.py --cutoff-date 2026-04-13       # Theo ngày cắt
```

---

### 2. `Pho_bert_test/` — PhoBERT Fine-tune Pipeline

**Mục đích**: Tạo dataset cảm xúc chất lượng cao thông qua **Gemini voting** → fine-tune **PhoBERT** cho phân loại cảm xúc tiếng Việt.

```
Pho_bert_test/
├── .env                         # GOOGLE_API_KEY (Gemini)
├── main.py                      # Orchestrator chính
├── gpt_preprocessor.py          # Gọi Gemini 5x/bài + voting
├── data_loader.py               # Load CSV → articles
├── phobert_finetune.py          # Fine-tune model + WeightedTrainer
├── merge_data.py                # Merge JSONL → all_train.jsonl
├── phobert_colab.ipynb          # Notebook cho Google Colab (T4 GPU)
├── requirements.txt
├── PROJECT_OVERVIEW.md          # Tài liệu chi tiết module này
├── data/
│   ├── all_train.jsonl          # 559 records tổng hợp
│   └── train_YYYYMMDD_HHMM.jsonl  # Daily checkpoints
└── phobert_finetuned/
    └── best_model/              # Best checkpoint
```

**Pipeline**:
```
news_content.csv
    ↓ data_loader.py
articles = [{news_id, summary, content}, ...]
    ↓ gpt_preprocessor.py (Gemini 3 Flash)
[5 lần/bài, temperature=0.3]
  → Tóm tắt ≤ 400 token
  → Nhãn: tich_cuc | trung_tinh | tieu_cuc
  → confidence (0.0–1.0)
  → Metadata: keywords, entities, impact_level
    ↓ Voting majority → quality flag
  HIGH (consistency≥0.8 & confidence≥0.6) → Training data
  MEDIUM (consistency≥0.6) → Dùng cẩn thận
  LOW → Bỏ qua
    ↓ phobert_finetune.py
train_YYYYMMDD.jsonl → 90% train / 10% val
Fine-tune vinai/phobert-base-v2
  - MAX_LENGTH=256, EarlyStoppingCallback(patience=2)
  - WeightedTrainer (CrossEntropyLoss với class weights)
    ↓
phobert_best_model/
```

**Nhãn**:
| Giá trị | Tên | Ý nghĩa |
|---------|-----|---------|
| 0 | `tieu_cuc` | Tin xấu, thua lỗ, rủi ro |
| 1 | `trung_tinh` | Thông tin trung lập |
| 2 | `tich_cuc` | Tin tốt, tăng trưởng |

**Thống kê data** (`all_train.jsonl`):
- 559 records: 504 train / 55 val
- `tich_cuc`: 320 | `tieu_cuc`: 111 | `trung_tinh`: 73

**Lệnh chạy**:
```bash
python main.py                             # Xử lý tất cả
python main.py --limit 5                   # Test 5 bài
python main.py --only-finetune             # Chỉ fine-tune
python main.py --only-finetune --data-file data/all_train.jsonl
python main.py --limit 20 --finetune --epochs 6 --batch-size 16
```

---

### 3. `phobert_best_model/` — Model Artifact

**Mục đích**: Best checkpoint từ fine-tuning, sẵn sàng deploy.

```
phobert_best_model/
├── model.safetensors       # Trọng số model
├── config.json             # Cấu hình (vocab_size, num_labels=3)
├── tokenizer_config.json
├── vocab.txt               # PhoBERT vocabulary
├── bpe.codes               # BPE encoding
└── training_args.bin       # Metadata training
```

Format Hugging Face — tương thích `transformers`:
```python
from transformers import AutoModelForSequenceClassification, AutoTokenizer
model = AutoModelForSequenceClassification.from_pretrained("path/to/phobert_best_model")
```

---

### 4. `Sentiment_analyst/` — Phân Tích Cảm Xúc (L-M Dictionary)

**Mục đích**: Phân tích cảm xúc dựa trên **Loughran-McDonald financial dictionary** (25 năm tài liệu tài chính).

```
Sentiment_analyst/
├── Loughran-McDonald_MasterDictionary_1993-2025.csv  # ⭐ Bộ từ điển
├── Translator/
│   ├── translate_news.py         # Dịch CSV Việt → Anh
│   └── output/
│       └── news_content_en.csv
├── Preprocessing_content/
│   ├── preprocess.py             # Tokenize + lọc stop-words
│   └── output/
│       └── news_content_preprocessed.csv
└── Sentiment_scoring/
    ├── sentiment_analysis.py     # Apply L-M dict → scores
    └── output/
        └── sentiment_results.csv
```

**Pipeline**:
```
news_content.csv (Tiếng Việt)
    ↓ translate_news.py (Google Translate)
news_content_en.csv (Tiếng Anh)
    ↓ preprocess.py
  - Tokenize
  - Loại NLTK stop-words (a, the, is, ...)
  - GIỮ LẠI term tài chính (profit, loss, revenue, gdp, ...)
    ↓ sentiment_analysis.py
  Từng từ → đếm Negative / Positive / Uncertain / Litigious
    ↓
sentiment_results.csv
  Fields: content_id, negative_count, positive_count,
          uncertain_count, litigious_count, sentiment_score
```

**L-M Dictionary Categories**:
- **Negative**: Loss, Cost, Risk, Decline, Collapse, ...
- **Positive**: Profit, Growth, Gain, Asset, ...
- **Uncertain**: May, Could, Might, ...
- **Litigious**: Legal, Regulatory, Compliance, ...

---

### 5. `Volume_precedes_price/` — Phân Tích Biến Động Giá

**Mục đích**: Mô hình hóa mối quan hệ giữa volume và volatility cho VN-30, kiểm chứng giả thuyết "volume precedes price".

```
Volume_precedes_price/
├── fetch_vn30_stock_price.py     # Lấy dữ liệu giá VN-30
├── eda_vn30_stock_price.ipynb    # Exploratory Data Analysis
├── model_volume_price.ipynb      # ⭐ ML modeling (28 cells)
├── vn30_stock_price.csv          # Dữ liệu OHLCV lịch sử
└── saved_models/                 # Model artifacts
```

**`model_volume_price.ipynb`** — Feature Engineering + Models:

| Feature | Loại | Mô tả |
|---------|------|-------|
| `rv_d`, `rv_w`, `rv_m` | HAR | Realized volatility 1/5/22 ngày |
| Parkinson | Volatility | `0.5 * (log(H/L))² / (4*ln2)` |
| Garman-Klass | Volatility | Phương sai GK 5 ngày |
| Amihud | Illiquidity | `|ret| / volume` trung bình |
| `volume_ma5`, `turnover` | Volume | Khối lượng giao dịch |

**Target**: `rv5_fwd` = forward realized volatility 5 ngày (không look-ahead)

**5 Models**:
1. **HAR-OLS** — Baseline tuyến tính
2. **Random Forest** — Ensemble
3. **XGBoost** — Gradient boosting
4. **LightGBM** — Fast gradient boosting
5. **Quantile RF** — Dự đoán khoảng tin cậy (10th–90th percentile)

**Validation**: `TimeSeriesSplit(n_splits=5)` — không data leakage theo thời gian

---

### 6. `TinyFinBERT/` — Knowledge Distillation (Nghiên Cứu)

**Mục đích**: Nghiên cứu **knowledge distillation** — bóp FinBERT (lớn) thành TinyBERT (nhỏ) qua data augmentation từ GPT-4o.

```
TinyFinBERT/
├── Final Evaluation of all models.ipynb
├── FineTuning_FinBERT_with_GPT4o_augmented_data.ipynb
├── Knowledge_Distillation_of_TinyBERT.ipynb
├── GPT_Predictions_1606_onPhrasebank.ipynb
├── GPT35Turbo_Create_Unlabelled_Data_BatchAPI.ipynb
├── GPT4o_filtering_GPT4o_generated_data.ipynb
├── GPT4_GenerationofNewSentences.ipynb
├── README.md                      # Hướng dẫn toàn diện (4000+ từ)
└── LICENSE
```

**Kết Quả**:
| Model | Accuracy | F1 | Kích thước |
|-------|----------|-----|------------|
| FinBERT (gốc) | 84.23% | 84.39% | 1x |
| Augmented FinBERT | 87.42% | 87.39% | 1x |
| **TinyFinBERT** | **83.30%** | **83.30%** | **7.5x nhỏ hơn** |

**Kỹ thuật áp dụng**:
1. Data Augmentation (GPT-4o → synthetic data)
2. Logit Matching (output alignment)
3. Intermediate Layer Distillation (feature transfer)
4. Discriminative Fine-tuning (learning rate khác nhau theo layer)
5. Gradual Unfreezing (tránh catastrophic forgetting)

---

### 7. `uiweb/` — Dashboard Frontend

**Mục đích**: Web UI cho dashboard — 3-column layout (Sidebar | Main | News Panel).

```
uiweb/
├── index.html
├── vite.config.js
├── package.json                   # React 18 + Vite
└── src/
    ├── App.jsx                    # Main component
    ├── main.jsx
    └── styles.css
```

**Tech Stack**: React 18, Vite, Chart.js, react-chartjs-2

**Chạy**:
```bash
cd uiweb
npm install
npm run dev      # http://localhost:5173
npm run build    # Production
```

---

### 8. `vnstockprice/` — Dữ Liệu Giá VN-30

**Mục đích**: Xây dựng lịch sử thành phần VN-30 + lọc OHLCV cho từng mã theo thời gian.

```
vnstockprice/
├── crawl_vn30_constituents.py      # Lịch sử thành phần
├── format_for_supabase.py          # Format cho Supabase DB
├── test.py
├── processed_output_v2/
│   ├── vn30_constituents.csv       # id, symbol, company_name, from_date, to_date
│   └── stock_prices.csv            # id, symbol, date, open, high, low, close, volume
└── supabase_ready/                 # Data đã format cho Supabase
```

---

### 9. `VNNewsCrawler/` — Crawler Tin Tức Chung

**Mục đích**: Crawler bổ sung cho các nguồn tin tức lớn (không chuyên tài chính).

```
VNNewsCrawler/
├── VNNewsCrawler.py               # Entry point
├── crawler_config.yml
├── requirements.txt
├── urls.txt                       # Danh sách URL seed
├── crawler/
│   ├── base_crawler.py
│   ├── dantri.py                  # dantri.com.vn
│   ├── vietnamnet.py              # vietnamnet.vn
│   ├── vnexpress.py               # vnexpress.net
│   └── factory.py
├── logger/
│   ├── log.py
│   └── logger_config.yml
└── utils/
    ├── bs4_utils.py
    └── utils.py
```

**Nguồn**: dantri.com.vn, vietnamnet.vn, vnexpress.net

---

### 10. `google-translate-api/` — Translation Utility

**Mục đích**: Thư viện dịch máy miễn phí, không giới hạn API calls (reverse-engineered Google Translate).

```
google-translate-api/
├── index.js           # API chính
├── languages.js       # Danh sách ngôn ngữ
├── test.js
└── package.json       # google-translate-api@2.3.0 (Node.js)
```

Dùng bởi `Sentiment_analyst/Translator/translate_news.py` để dịch Việt → Anh.

---

### 11. `vnstock-agent-guide/` — Tài Liệu AI Agent

**Mục đích**: Tài liệu toàn diện cho AI agents (Claude, Gemini, Copilot, Cursor, Windsurf) sử dụng hệ sinh thái **vnstock**.

```
vnstock-agent-guide/
├── README.md
├── AGENTS.md          # Windsurf IDE
├── CLAUDE.md          # Claude Code
├── CHANGELOG.md
├── context7.json
├── demo/
│   └── vnstock_agent_guide_quickstart.ipynb
├── docs/
│   ├── vnstock/
│   ├── vnstock_ta/          # Technical Analysis
│   ├── vnstock_news/        # News module
│   └── vnstock_pipeline/
├── .agents/rules/GEMINI.md
├── .cursor/rules/instructions.md
└── .github/copilot-instructions.md
```

**Thư viện được tài liệu hóa**:
| Thư viện | Mục đích |
|---------|---------|
| `vnstock` | API dữ liệu miễn phí |
| `vnstock_data` | Macro, Insights, Screener |
| `vnstock_ta` | Technical Analysis |
| `vnstock_news` | News + Sentiment |
| `vnstock_pipeline` | Production pipelines |

---

## 🔧 Technology Stack

| Layer | Công nghệ |
|-------|-----------|
| **Web Crawling** | requests, BeautifulSoup4, lxml, ThreadPoolExecutor |
| **Data Pipeline** | pandas, numpy |
| **NLP Models** | PhoBERT (vinai/phobert-base-v2), FinBERT, Transformers |
| **LLM** | Google Gemini 3 Flash (`gemini-3-flash-preview`) |
| **ML** | PyTorch, scikit-learn, XGBoost, LightGBM |
| **Translation** | Google Translate API (Node.js) |
| **Frontend** | React 18, Vite, Chart.js |
| **Config** | YAML |
| **GPU Training** | Google Colab (T4/A100) |
| **Database** | Supabase (PostgreSQL) |
| **Logging** | Python logging + YAML config |

---

## 📋 Tổng Kết

| Module | Trạng Thái | Mô Tả ngắn |
|--------|-----------|------------|
| `stocknewscrawl/` | ✅ Hoạt động | Crawl 4 nguồn tài chính VN |
| `Pho_bert_test/` | ✅ Hoạt động | Gemini voting + PhoBERT fine-tune |
| `phobert_best_model/` | ✅ Built | Model artifact đã train |
| `Sentiment_analyst/` | ✅ Hoạt động | L-M dictionary pipeline |
| `Volume_precedes_price/` | ✅ Hoàn thiện | Volatility forecasting (rv5_fwd) |
| `TinyFinBERT/` | ✅ Reference | Knowledge distillation research |
| `uiweb/` | 🔧 Mock UI | Dashboard (cần kết nối backend) |
| `vnstockprice/` | ✅ Hoàn thiện | VN-30 OHLCV data processing |
| `VNNewsCrawler/` | ✅ Hoạt động | Crawler thêm (dantri, vnexpress) |
| `google-translate-api/` | ✅ Dependency | Utility dịch thuật |
| `vnstock-agent-guide/` | ✅ Reference | Tài liệu vnstock cho AI agents |
