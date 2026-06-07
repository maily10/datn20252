# Báo cáo: Phân tích sắc thái tin tức tài chính bằng Hybrid PhoBERT + Từ điển

> Thuộc đồ án *"Thu thập, xử lý và đánh giá tương quan thay đổi giá chứng khoán với tin tức"* —
> Nội dung 2, bước **Sentiment**. Tài liệu này mô tả **một** phương pháp duy nhất kèm bằng chứng.

---

## Tóm tắt

| | |
|---|---|
| **Phương pháp** | Một điểm cực tính liên tục `s(t) ∈ [−1, 1]` hợp nhất PhoBERT và từ điển tài chính tự biên soạn |
| **Tham số** | `α = 0.6`, `k = 0.8` (chính); `τ = 0.1` (chỉ để hiển thị lens 3 lớp) |
| **Gold set đánh giá** | CafeF 1.005 tiêu đề có nhãn chuyên gia; train/test 70/30 stratified, seed 42 |
| **Kết quả TEST — Polarity (pos/neg)** | **Accuracy 87.2% · macro-F1 0.827** (vượt 70%) |
| Kết quả TEST — 3 lớp (đầy đủ) | Accuracy 64.6% · macro-F1 0.583 |
| **Vai trò trong đồ án** | Xuất `s(t)` cho từng tin → tổng hợp `mean(s)` theo (mã, ngày) → đối chiếu PELT ở Mốc 4 |

---

## 1. Vấn đề & Mục tiêu

Đồ án cần một **tín hiệu sắc thái** cho mỗi tin tài chính VN30 để đối chiếu với điểm thay đổi giá.
Các mô hình sentiment tiếng Việt phổ thông (PhoBERT-sentiment) được huấn luyện trên dữ liệu tổng
quát và **yếu ở sắc thái tài chính** (vd "chia cổ tức" bị chấm neutral). Việt Nam **chưa có
từ điển sentiment tài chính chuẩn hoá** (kiểu Loughran-McDonald cho tiếng Anh); các bài học thuật
gần đây (vd Vu et al. 2023 — PhoBERT, 81% trên ~40k bài) **không công bố mô hình/dữ liệu**.

→ Mục tiêu: xây *một phương pháp* sentiment tài chính (a) chính xác đủ làm tín hiệu cho phân
tích tương quan, (b) **minh bạch, giải thích được**, (c) chạy được trên CPU.

---

## 2. Phương pháp — MỘT method duy nhất

### 2.1 Công thức

```
   s_model = P(pos | t) − P(neg | t)                       ∈ [−1, 1]   (PhoBERT)
   s_lex   = tanh( k · ( pos_hits − neg_hits ) )           ∈ [−1, 1]   (Từ điển)

   s(t)    = (1 − α) · s_model  +  α · s_lex               ∈ [−1, 1]   ← OUTPUT
```

`s(t)` là **đại lượng duy nhất** mà method sinh ra. Hai tham số: **`α`** (mức tin vào từ điển) và
**`k`** (độ dốc bão hoà của lexicon).

### 2.2 Hai "lens" để rời rạc hoá (không phải hai method khác nhau)

| Lens | Định nghĩa | Dùng để |
|---|---|---|
| **polarity** | `positive` nếu `s > 0`, `negative` nếu `s ≤ 0` | **Đo trực tiếp** chất lượng tín hiệu hướng (mục tiêu vận hành) |
| **label 3 lớp** | `pos` nếu `s > τ`; `neg` nếu `s < −τ`; `neu` còn lại | Báo cáo song song cho minh bạch |

`τ` là **tham số trình bày** (cho lens 3 lớp), không phải tham số của method.

### 2.3 Cơ sở lý thuyết — vì sao điểm liên tục, vì sao hybrid

1. **Sentiment tài chính vận hành theo hướng — có tiền lệ kinh điển.**
   - Tetlock (2007) xây *một nhân tố bi quan* từ tin tức và chứng minh nó dự báo biến động thị trường.
   - Loughran & McDonald (2011) đo sentiment bằng **đếm từ tích cực vs tiêu cực**.
   - Antweiler & Frank (2004) đo *bullishness* — cũng là chỉ số một chiều.
   → Đại lượng có nghĩa kinh tế là **độ lệch (tích cực − tiêu cực)** — đúng bằng `s(t)`.

2. **Vì sao cần hybrid (model + từ điển).** Loughran & McDonald (2011) chỉ ra rằng từ điển cảm
   xúc tổng quát phân loại sai ~3/4 số từ "tiêu cực" khi áp vào văn bản tài chính. Ở chiều ngược
   lại, model phổ thông không đủ "kiến thức tài chính" để chấm đúng các cụm như *"chia cổ tức"*,
   *"khối ngoại bán ròng"*. Phương án lai (model nền + từ điển hiệu chỉnh) tận dụng cả ngữ
   nghĩa và kiến thức miền, **đồng thời minh bạch** (cụm nào, hệ số nào, ngưỡng nào — đều đọc
   được).

3. **Vì sao loại neutral khỏi mục tiêu chính.** Lớp neutral có độ tin cậy nhãn thấp nhất (phân
   tích lỗi mục 4.4 cho thấy nhiều nhãn neutral của gold set tự mâu thuẫn). Mục tiêu hạ nguồn
   (Mốc 4) tổng hợp `mean(s)` theo (mã, ngày) — tin neutral đóng góp ≈ 0 nên dải neutral chỉ là
   *ngưỡng vận hành*. Đo polarity là đo trực tiếp chất lượng tín hiệu hướng.

---

## 3. Triển khai

### 3.1 Từ điển tài chính tự biên soạn — `config/finance_lexicon.yml`

**122 cụm**: 56 tích cực, 66 tiêu cực, 9 từ phủ định. Tổ chức theo chủ đề (kết quả kinh doanh,
cổ tức, hợp đồng, dòng tiền khối ngoại, diễn biến giá, pháp lý/quản trị, định giá/khuyến nghị).

**Nguyên tắc biên soạn:**
- Ưu tiên CỤM TỪ, tránh từ đơn đa nghĩa "tăng"/"giảm" (*"lợi nhuận giảm"* ngược với *"nợ xấu giảm"*).
- Khớp nguyên cụm, không phân biệt hoa thường, có ranh giới từ ở 2 đầu.
- Phủ định trong cửa sổ ~18 ký tự đảo cực cụm tiếp theo (vd *"chưa hoàn thành kế hoạch"*).

Ví dụ:
- *Tích cực*: `lãi kỷ lục`, `vượt kế hoạch`, `chia cổ tức`, `khối ngoại mua ròng`, `tăng trần`...
- *Tiêu cực*: `thua lỗ`, `lợi nhuận giảm`, `vỡ nợ`, `nợ xấu`, `giảm sàn`, `khối ngoại bán ròng`,
  `hủy niêm yết`, `bị điều tra`, `khuyến nghị bán`...

### 3.2 Kiến trúc code

```
lib/
├── sentiment_scorer.py    # wrapper PhoBERT → P(neg), P(neu), P(pos) cho mỗi tin
├── finance_lexicon.py     # đếm cụm tích cực/tiêu cực + phủ định → net
└── hybrid_scorer.py       # ★ fusion: trả về HybridResult với s(t), polarity, label_3cls
config/
└── finance_lexicon.yml    # từ điển (122 cụm + 9 phủ định)
```

`HybridResult` có **`score`** (`s(t)`, output chính), **`polarity`** (view nhị phân), **`label_3cls`**
(view 3 lớp), kèm các thành phần debug (`model_score`, `lex_net`, `matched_pos/neg`).

### 3.3 Pipeline vận hành

```bash
python prepare_gold.py                 # (một lần) tạo data/gold_cafef.csv từ raw_data.xlsx
python evaluate.py                     # (một lần) tinh chỉnh & lưu output/method_config.json
python run_sentiment.py --hybrid       # chấm toàn corpus → news_sentiment_hybrid.csv
```

`run_sentiment.py --hybrid` đọc `method_config.json` lấy `(α, k, τ)`, chấm `title + summary`,
xuất CSV với các cột: `news_id, score, polarity, label_3cls, model_score, lex_net, prob_*`.

### 3.4 Tham số đã chốt (lưu tại `output/method_config.json`)

| Tham số | Giá trị | Vai trò |
|---|---|---|
| `α` | **0.6** | Trọng số từ điển trong fusion |
| `k` | **0.8** | Độ dốc bão hoà của `tanh` |
| `τ` | **0.1** | Ngưỡng cho lens 3 lớp (chỉ trình bày) |
| Model | `wonrax/phobert-base-vietnamese-sentiment` | PhoBERT-base, 3-class |

---

## 4. Đánh giá

### 4.1 Gold set

- **Nguồn**: repo `209sontung/Vietnamese-stock-article-classification`, file `Dataset/raw_data.xlsx`
  — 1.005 tiêu đề tin chứng khoán từ CafeF.vn, gán nhãn có hỗ trợ chuyên gia.
- **Ánh xạ nhãn**: số gốc 1/2/3 → `negative` / `neutral` / `positive`.
- **Phân bố**: 187 negative / 249 neutral / 569 positive.
- **Phạm vi**: chỉ TIÊU ĐỀ (đây là hạn chế đã ghi nhận, mục 6).

### 4.2 Quy trình tinh chỉnh (chạy `evaluate.py`)

1. Chia stratified train/test = 70/30, `random_state = 42`.
2. Chấm PhoBERT + từ điển **một lần** cho cả 1.005 tiêu đề → cache `(s_model, net)`.
3. **Bước 1** — tinh chỉnh `(α, k)` trên train, **tối ưu binary macro-F1** (mục tiêu vận hành).
   - Lưới: α ∈ {0.0, 0.1, …, 0.8}, k ∈ {0.4, 0.6, 0.8, 1.0}.
   - Kết quả: `α = 0.6`, `k = 0.8` (train binary F1 = 0.7725).
4. **Bước 2** — tinh chỉnh `τ` trên train, tối ưu 3-class macro-F1 (giữ α, k).
   - Lưới: τ ∈ {0.05, 0.10, …, 0.30}.
   - Kết quả: `τ = 0.1` (train 3-class F1 = 0.5313).
5. Đánh giá trên TEST với 4 cấu hình (xem 4.3).

### 4.3 Bảng kết quả chứng minh (test, n = 302; polarity n = 227)

**Bảng tổng — so sánh có baseline để cô lập đóng góp của từ điển**

| Cấu hình | Lens | n | Accuracy | macro-F1 |
|---|---|---|---|---|
| PhoBERT thuần (argmax) | 3 lớp | 302 | 0.593 | 0.545 |
| **Hybrid (Hướng A)** | 3 lớp | 302 | **0.646** | **0.583** |
| PhoBERT thuần (sign) | Polarity | 227 | 0.815 | 0.767 |
| **★ Hybrid (Hướng A)** | **Polarity** | 227 | **0.872** | **0.827** |

→ **Hybrid > PhoBERT thuần ở cả hai lens.** Trên lens vận hành (polarity), hybrid đạt **87.2% /
F1 0.827**, đóng góp riêng của lexicon: **+5.7 điểm Accuracy, +6.0 điểm F1**.

**Per-class — Polarity (n = 227):**

| | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| negative | 0.745 | 0.732 | **0.739** | 56 |
| positive | 0.913 | 0.918 | **0.915** | 171 |
| macro avg | 0.829 | 0.825 | **0.827** | |

**Per-class — 3 lớp (n = 302):**

| | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| negative | 0.507 | 0.625 | 0.560 | 56 |
| neutral | 0.390 | 0.400 | 0.395 | 75 |
| positive | 0.833 | 0.760 | 0.795 | 171 |
| macro avg | 0.577 | 0.595 | **0.583** | |

**Ma trận nhầm lẫn 3 lớp** (hàng = thật, cột = đoán):

| thật \ đoán | negative | neutral | positive |
|---|---|---|---|
| negative | **35** | 17 | 4 |
| neutral | 23 | **30** | 22 |
| positive | 11 | 30 | **130** |

### 4.4 Phân tích lỗi (định tính)

Soi 106 ca chấm sai trên test cho thấy ba nhóm chính:

1. **Nhãn gold chủ quan/sai** — vd *"VN-Index phá đỉnh lịch sử"* gán `neutral` (hybrid đoán
   `positive` hợp lý hơn); *"Mã lớn VN30 ... bứt phá"* gán `neutral`. Trần độ chính xác bị giới
   hạn bởi chất lượng nhãn.
2. **Bài liệt kê đa mã** — vd *"FIT, HPG, DLG, ... Thông tin giao dịch"* — bản chất không phải
   sentiment đơn mã, nên lọc khỏi pipeline.
3. **Thiếu cụm trong từ điển** — *áp lực bán*, *mất mốc*, *đấu giá thành công*, *đồng loạt
   điều chỉnh* — khắc phục được bằng cách mở rộng từ điển theo lỗi quan sát.

Nhóm 1 *không sửa được bằng model/lexicon* (cần nhãn sạch hơn). Nhóm 2 sửa ở bước gắn mã.
Nhóm 3 sửa rẻ.

---

## 5. Vai trò trong đồ án (kết nối Mốc 4)

`run_sentiment.py --hybrid` xuất cho mỗi tin một dòng có **`score`** (chính), `polarity`,
`label_3cls`, kèm thành phần debug. Kết hợp với **gắn mã** (`run_tag.py` →
`news_stock_mapping.csv`), tổng hợp theo nhóm `(symbol, ngày)`:

```
mean_sentiment(mã, ngày) = mean{ s(t) : tin t về mã đó, ngày đó }
n_news(mã, ngày)         = số tin
```

Sau đó đối chiếu với **điểm thay đổi giá** (PELT trên chuỗi giá/KPI) bằng coverage, tỷ lệ khớp
hướng, tương quan Pearson/Spearman. **Không cần rời rạc hoá** sang nhãn trước khi tương quan
— dùng thẳng `mean_sentiment` liên tục như các nghiên cứu trên.

---

## 6. Hạn chế (trung thực)

1. **Gold set chỉ có TIÊU ĐỀ** (CafeF), không có nội dung; nhãn chủ quan ở khoảng 10% (nhóm 1
   ở 4.4) → trần độ chính xác bị giới hạn.
2. **Lệch miền**: gold CafeF khác các nguồn của crawler (VnEconomy, Báo Đầu Tư, Thời Báo TC,
   Thị Trường TC). Số trên là *xấp xỉ* trên corpus thật.
3. **α = 0.6 khá cao** — từ điển có thể lật cả dự đoán model tự tin. Tốt trên trung bình
   nhưng có lỗi cá biệt (vd tin xấu chứa nhiều cụm tích cực bị lật sang dương).
4. **Tập test nhỏ (302 / 227)** — khoảng tin cậy không hẹp. Có thể bổ sung *k-fold CV* trong
   tương lai (rẻ, dùng lại cache model).
5. **Lexicon độ phủ 122 cụm**; phủ định chỉ xử lý cửa sổ ngắn.
6. **Chưa đối chứng được ViSoBERT** (5CD-AI) — model social VN mạnh — do tokenizer không tương
   thích `transformers 5.6.2`. Trong khi đó, `mr4/phobert-base-vi-sentiment-analysis` cho điểm
   trùng khít wonrax (cùng weights, không phải đối chứng độc lập). → Đổi model **không phải đòn
   bẩy** ở thiết lập này; đòn bẩy thật là cách phân loại và lexicon.

---

## 7. Tài liệu tham khảo

1. Loughran, T., & McDonald, B. (2011). *When Is a Liability Not a Liability? Textual Analysis,
   Dictionaries, and 10-Ks.* The Journal of Finance, 66(1), 35–65.
2. Tetlock, P. C. (2007). *Giving Content to Investor Sentiment: The Role of Media in the Stock
   Market.* The Journal of Finance, 62(3), 1139–1168.
3. Antweiler, W., & Frank, M. Z. (2004). *Is All That Talk Just Noise? The Information Content
   of Internet Stock Message Boards.* The Journal of Finance, 59(3), 1259–1294.
4. Nguyen, D. Q., & Nguyen, A. T. (2020). *PhoBERT: Pre-trained language models for Vietnamese.*
   Findings of EMNLP 2020.
5. Vu, L. T., Pham, D. N., Kieu, H. T., & Pham, T. T. T. (2023). *Sentiments Extracted from News
   and Stock Market Reactions in Vietnam.* International Journal of Financial Studies, 11(3), 101.
6. Mô hình: `wonrax/phobert-base-vietnamese-sentiment` (HuggingFace).
7. Gold set: `209sontung/Vietnamese-stock-article-classification` (GitHub).

---

## Phụ lục — Cấu trúc file & cách chạy

```
test/news_sentiment/
├── config/
│   ├── finance_lexicon.yml         # ★ từ điển tài chính (122 cụm)
│   └── vn30_companies.yml          # từ điển VN30 cho gắn mã
├── lib/
│   ├── finance_lexicon.py          # đọc & chấm lexicon + phủ định
│   ├── hybrid_scorer.py            # ★ method: fusion → s(t), polarity, label_3cls
│   ├── sentiment_scorer.py         # wrapper PhoBERT
│   └── ticker_tagger.py            # gắn mã (cho run_tag.py)
├── data/
│   ├── raw_data.xlsx               # nguồn gold (tải từ GitHub)
│   └── gold_cafef.csv              # gold đã chuẩn hoá
├── output/
│   ├── method_config.json          # tham số method đã tinh chỉnh
│   ├── eval_results.csv            # dự đoán trên test (proof số liệu)
│   ├── news_stock_mapping.csv      # quan hệ (tin ↔ mã) từ run_tag
│   └── news_sentiment_hybrid.csv   # sentiment toàn corpus (sau khi run_sentiment --hybrid)
├── prepare_gold.py                 # tạo gold_cafef.csv
├── evaluate.py                     # ★ tinh chỉnh & đánh giá method (sinh số liệu mục 4.3)
├── run_tag.py                      # chạy gắn mã
├── run_sentiment.py                # ★ chạy sentiment toàn corpus (có --hybrid)
├── README.md
└── HUONG_A_HYBRID_SENTIMENT.md     # tài liệu này
```

```bash
cd test/news_sentiment

# B1 — gold set (một lần)
python prepare_gold.py

# B2 — tinh chỉnh & đánh giá method (một lần) → method_config.json + eval_results.csv
python evaluate.py

# B3 — chấm sentiment toàn corpus
python run_sentiment.py --hybrid

# (gắn mã)
python run_tag.py
```
