# Báo cáo tổng hợp công việc — Đồ án tốt nghiệp

> **Đề tài:** Thu thập, xử lý và đánh giá tương quan thay đổi giá chứng khoán với tin tức (VN30, 2022–2026).
> Tài liệu này mô tả chi tiết **từng phần công việc đã làm**: luồng xử lý, các bước trong luồng,
> đầu vào, đầu ra và kết quả đạt được. Trình tự được sắp xếp lại theo **luồng dữ liệu end-to-end**,
> ánh xạ với 3 Nội dung của đề tài.

```
NỘI DUNG 1 — DỮ LIỆU GIÁ                NỘI DUNG 2 — TIN TỨC
 ┌────────────────────────┐             ┌────────────────────────┐
 │ A. Thu thập giá VN30   │             │ D. Crawler tin tức     │
 │ B. EDA dữ liệu giá     │             │ E. Gắn mã + Sentiment  │
 │ C. Tính KPI (15 chỉ số)│             │    (Hybrid PhoBERT+Lex)│
 └───────────┬────────────┘             └───────────┬────────────┘
             │                                      │
             └──────────────────┬───────────────────┘
                                ▼
              NỘI DUNG 3 — PHÂN TÍCH & TRỰC QUAN HOÁ
              ┌──────────────────────────────────────┐
              │ F. Phát hiện điểm thay đổi (PELT)     │
              │ G. Đánh giá tương quan (giá ↔ tin)    │
              │ H. Tích hợp dữ liệu + Dashboard       │
              └──────────────────────────────────────┘
```

---

# PHẦN I — DỮ LIỆU GIÁ (Nội dung 1)

## A. Thu thập dữ liệu giá VN30

**Mục tiêu:** Có chuỗi giá OHLCV ngày cho 30 mã VN30 giai đoạn 2022–2026, kèm lịch sử thành phần
rổ VN30 (vì thành phần thay đổi qua các kỳ rà soát của HOSE).

**Thư mục:** `vnstockprice/`

### Luồng xử lý (3 bước)

**Bước 1 — Dựng lịch sử thành phần VN30** (`crawl_vn30_constituents.py`)
- *Vấn đề:* thư viện `vnstock` (`Listing.symbols_by_group('VN30')`) chỉ trả về **danh sách hiện
  tại**, không có API lịch sử thành phần theo giai đoạn.
- *Giải pháp:* hard-code lịch sử thay đổi VN30 từ **thông báo chính thức của HOSE** (rà soát bán
  niên tháng 1 và tháng 7 hằng năm, từ 2012 đến nay). Mỗi bản ghi là `(symbol, from_date, to_date)`
  với `to_date = NULL` nghĩa là mã vẫn còn trong rổ.
- *Cross-check:* đối chiếu với danh sách VN30 hiện hành lấy từ `vnstock` để tự sửa các sai lệch
  (mã đã rời rổ nhưng để `to_date=NULL`, hoặc ngược lại).
- *Tên công ty:* lấy từ `Listing(source='VCI').all_symbols()`.
- **Đầu ra:** `processed_output_v2/vn30_constituents.csv` — schema `(id, symbol, company_name,
  from_date, to_date, created_at)`, **50 bản ghi** (gồm cả mã đang trong rổ và đã rời rổ).

**Bước 2 — Chuẩn hoá dữ liệu cho Supabase** (`format_for_supabase.py`)
- Đọc 3 file gốc trong `processed_output_v2/` → ghi ra `supabase_ready/` đúng schema bảng Supabase.
- `stock_prices.csv` là file lớn (~334 MB, toàn bộ HOSE ~4,6 triệu dòng) → đọc theo **chunk
  500.000 dòng**: bỏ cột `id` (Supabase tự sinh), chuẩn hoá `date → YYYY-MM-DD`, ép `volume` về
  integer, ép OHLC về numeric.
- `companies.csv`: giữ 2 cột `(symbol, company_name)`. `vn30_constituents.csv`: giữ
  `(id, symbol, from_date, to_date)`, để trống `to_date` cho mã còn trong rổ.
- **Đầu ra:** `supabase_ready/{companies, stock_prices, vn30_constituents}.csv` — sẵn sàng import.

**Bước 3 — Lọc giá theo đúng khoảng thời gian thuộc rổ** (`Volume_precedes_price/fetch_vn30_stock_price.py`)
- Với mỗi mã, chỉ giữ những phiên mà mã đó **đang thuộc VN30** (`from_date ≤ date ≤ to_date`,
  `to_date` rỗng được điền = hôm nay).
- Gộp, khử trùng theo `(symbol, date)`, sắp xếp.
- **Đầu ra:** `vn30_stock_price.csv` — phục vụ bước EDA (mục B).

### Kết quả đạt được
- Lịch sử thành phần VN30 đầy đủ: **50 bản ghi** (mã hiện hành + mã đã rời rổ với mốc ngày).
- Dữ liệu giá OHLCV: bộ VN30 đầy đủ **2012 → 2026-04-03** (lọc 2022–2026 ở bước tính KPI).
- 3 file chuẩn Supabase đã được nạp thành công (`companies`, `stock_prices`, `vn30_constituents`).

---

## B. Phân tích khám phá dữ liệu giá (EDA)

**Mục tiêu:** Hiểu đặc trưng dữ liệu giá trước khi tính KPI/mô hình hoá — phát hiện thiếu dữ liệu,
phân phối, biến động, tương quan giữa các mã.

**File:** `Volume_precedes_price/eda_vn30_stock_price.ipynb` (đọc `vn30_stock_price.csv`)

### Các bước phân tích
1. **Tổng quan dữ liệu:** shape, khoảng thời gian, số mã, thống kê mô tả OHLCV + volume.
2. **Kiểm tra thiếu dữ liệu:** đếm null từng cột + heatmap → kết quả **0% thiếu**.
3. **Số phiên giao dịch theo mã:** bar chart (mã vào rổ sớm có nhiều phiên hơn).
4. **Phân phối giá đóng cửa:** giá mới nhất các mã hiện tại + histogram toàn lịch sử.
5. **Diễn biến giá chuẩn hoá (Base = 100):** so sánh hiệu suất tương đối giữa các mã theo thời gian.
6. **Phân tích khối lượng:** Top mã theo volume trung bình; phân phối `log(volume+1)`; tổng volume
   theo tháng.
7. **Daily return & Volatility:** phân phối return (nhọn, đuôi dày — clip ±20%); độ biến động (std
   return) theo mã.
8. **Ma trận tương quan return** giữa các mã VN30 hiện tại (heatmap) — các mã ngân hàng tương quan
   cao với nhau.
9. **Volume ↔ |Daily return|:** tương quan Pearson theo mã (kiểm chứng "khối lượng đi cùng biến động").
10. **Candlestick mẫu** (VCB, 6 tháng) + biểu đồ volume.
11. **Bảng tóm tắt** tổng hợp.

### Kết quả đạt được (số liệu thực tế)
| Chỉ tiêu | Giá trị |
|---|---|
| Tổng số dòng | **96.849** |
| Số mã | 50 (gồm cả mã đã rời rổ trong lịch sử) |
| Khoảng thời gian | 2012-02-06 → 2026-04-03 (3.536 ngày giao dịch) |
| Giá đóng cửa trung bình | 29,79 (nghìn VND) |
| Volume trung bình | ~4,24 triệu cp/phiên |
| Std daily return | ~0,02 (2%/phiên) |
| Dữ liệu thiếu | **0%** (không có null) |

→ Kết luận EDA: dữ liệu **sạch, đầy đủ**, phân phối return chuẩn-nhọn điển hình của chuỗi tài
chính; nhóm ngân hàng có tương quan return cao → cơ sở để xử lý từng mã độc lập ở các bước sau.

---

## C. Tính KPI / chỉ số kỹ thuật

**Mục tiêu:** Từ giá OHLCV, tính **15 chỉ số kỹ thuật** cho 30 mã VN30, vừa là đầu vào cho phát
hiện điểm thay đổi (Nội dung 3), vừa là chỉ số hiển thị trên dashboard.

**File:** `vnstockprice/compute_kpi.ipynb` → `vnstockprice/technical_indicators.csv`

### Luồng xử lý (các bước)
1. **Đọc & lọc:** đọc `supabase_ready/stock_prices.csv` theo chunk 500.000 dòng, **lọc ngay 30 mã
   VN30** để tiết kiệm bộ nhớ; loại dòng lỗi (`close ≤ 0`, ngày không hợp lệ); sort theo `(symbol, date)`.
2. **Tính KPI theo từng mã** (hàm `compute_kpis`), trên chuỗi đã sort:
   - **Sinh lời:** `daily_return = pct_change`, `log_return = ln(Pₜ/Pₜ₋₁)`.
   - **Xu hướng:** `ma_20`, `ma_50` (trung bình động); `macd = EMA12 − EMA26`,
     `macd_signal = EMA9(macd)`, `macd_hist = macd − signal`.
   - **Biến động:** `volatility_20 = std(log_return, 20)`; Bollinger `bb_upper/bb_lower = MA20 ± 2σ`,
     `bb_pctb = (close − lower)/(upper − lower)`.
   - **Động lượng:** `rsi_14` (Wilder smoothing qua EWM α=1/14); `volume_change`; `obv` (On-Balance Volume).
   - **Rủi ro:** `drawdown = (close − cummax)/cummax`.
3. **Cắt thời gian đúng cách:** tính KPI trên **toàn bộ lịch sử trước**, *rồi mới* cắt từ
   `2022-01-01` — để các cửa sổ trượt (MA50, RSI…) đã "đủ ấm", không bị NaN đầu kỳ.
4. **Kiểm tra chất lượng:** RSI ∈ [0,100]; daily_return trong ±7% (biên độ sàn HOSE); **số NaN mỗi
   KPI = 0**.
5. **Trực quan hoá:** giá + MA + Bollinger + RSI cho 1 mã; phân phối return toàn VN30; volatility theo mã.

### Đầu vào / Đầu ra
- **Đầu vào:** `supabase_ready/stock_prices.csv` (toàn HOSE, lọc VN30 còn 93.758 dòng lịch sử đầy đủ).
- **Đầu ra:** `technical_indicators.csv` — **31.710 dòng × 22 cột** (7 cột OHLCV gốc + 15 KPI).

### Kết quả đạt được (số liệu kiểm chứng từ notebook)
| Chỉ tiêu | Giá trị |
|---|---|
| Số dòng KPI | **31.710** |
| Số cột | **22** (7 OHLCV + 15 KPI) |
| Số mã | 30/30 VN30 |
| Khoảng ngày | 2022-01-04 → 2026-04-03 |
| Số phiên/mã (trung bình) | **1.057** |
| RSI range | 6,6 → 95,4 (hợp lệ) |
| Daily return range | −7,1% → +7,2% (đúng biên độ HOSE) |
| NaN mỗi KPI | **0** |

---

# PHẦN II — TIN TỨC (Nội dung 2)

## D. Thu thập tin tức (Web Crawler)

**Mục tiêu:** Crawl tin tức tài chính/chứng khoán từ **4 báo điện tử Việt Nam**, xuất 2 file CSV
chuẩn hoá (links + content) sẵn sàng nạp Supabase.

**Thư mục:** `stocknewscrawl/` (tài liệu chi tiết: `CRAWLER_FLOW.md`)

**4 nguồn:** VnEconomy (chính), Báo Đầu Tư, Thời Báo Tài Chính VN, Thị Trường Tài Chính Tiền Tệ.

### Kiến trúc — pipeline 2 pha độc lập

**PHA 1 — Thu thập URL** (`crawl_all_sites.py` → `crawler/*`)
- Mỗi nguồn → mỗi chuyên mục → `get_urls_of_category()`. Hai chế độ:
  - **Tuần tự + early-stop** (`start_date` ≠ ""): duyệt từng trang, dừng khi `probe_article_date`
    của bài cuối trang < `start_date` (chạm mốc 2022) hoặc trang rỗng 2 lần liên tiếp.
  - **Song song** (`start_date` = ""): `ThreadPoolExecutor` chạy đồng thời nhiều trang rồi gộp + dedup.
- Đặc thù từng site: phân trang (`?page=N`, `/pN`, AJAX "Xem thêm") và selector lấy link riêng.
- **Đầu ra:** `result/urls/{site}_{category}.txt` (mỗi dòng 1 URL).

**PHA 2 — Trích xuất nội dung** (`crawl_content.py` → `content_crawler/*`)
- Đọc tất cả `*.txt` → list URL duy nhất; load `done_urls` từ `news_links.csv` để **resume**
  (bỏ URL đã crawl).
- `ThreadPoolExecutor(5 workers)`: mỗi URL chọn content-crawler theo **domain**, gọi
  `extract_article(url)` → dict 7 trường. Thứ tự đọc quan trọng: title → summary → image → **date**
  → **content gọi cuối** (vì `extract_best_content` xoá noise DOM tại chỗ, mất ngày nếu đọc sau).
- `extract_best_content`: xoá thẻ/element noise (nav/footer/aside/sidebar/ads/share/comment) qua
  regex, gom toàn bộ `<p>` còn lại, lọc đoạn quá ngắn/footer.
- Lọc bài theo `[start_date, end_date]`; ghi từng dòng + `flush()` ngay (an toàn nếu gián đoạn);
  `sleep(0.2)` lịch sự tránh bị chặn.

### Kỹ thuật & design pattern
Factory Pattern (chọn crawler theo site/domain) · Template Method (`BaseCrawler` định nghĩa khung,
subclass cài chi tiết) · Đa luồng (ThreadPoolExecutor) · Resume/Incremental · Early-stop theo ngày
· Polite crawling · Ghi an toàn (append + flush).

### Đầu ra (2 file liên kết 1-1 qua `news_links.id = news_content.news_id`)
- `vnstocknewsdata/news_links.csv`: `(id, url, title, source, published_at, published_date, status, created_at)`.
- `vnstocknewsdata/news_content.csv`: `(news_id, content, summary, image_url, created_at)`.

### Kết quả đạt được
- **~15.791 bài** giai đoạn **2022–2026**, đều có ngày đăng đầy đủ, từ 4 nguồn.
- Crawler chạy ổn định, có resume + early-stop → có thể cập nhật incremental.

---

## E. Gắn mã cổ phiếu + Đánh giá Sentiment

**Mục tiêu:** Với mỗi tin: (1) xác định tin nói về (các) mã VN30 nào; (2) chấm một **điểm cực tính
liên tục** `s(t) ∈ [−1, 1]` để đối chiếu với biến động giá ở Nội dung 3.

**Thư mục:** `test/news_sentiment/` (tài liệu chi tiết: `HUONG_A_HYBRID_SENTIMENT.md`)

### E.1 Gắn mã (`run_tag.py` → `lib/ticker_tagger.py`)
- **Rule-based**, không cần ML, dựa trên `config/vn30_companies.yml`:
  - Khớp **mã viết hoa nguyên từ** (vd `HPG`, `(VCB)`, `mã FPT`) — phân biệt hoa/thường để "gas"
    không nhầm "GAS".
  - Khớp **tên công ty** (không phân biệt hoa thường, ưu tiên cụm dài nhất).
  - **Blacklist** chống false-positive (vd `GAS` ↔ "natural gas", `VIC` ↔ "victory").
- Tin không gắn được mã cụ thể → coi là tin **thị trường chung (MARKET)**.
- **Đầu ra:** `output/news_stock_mapping.csv` — quan hệ nhiều-nhiều `(news_id, symbol)`, **~44.331 dòng**.

### E.2 Sentiment — Hướng A: Hybrid PhoBERT + Từ điển tài chính
**Công thức (một method duy nhất):**
```
s_model = P(pos|t) − P(neg|t)                  ∈ [−1,1]   (PhoBERT: wonrax/phobert-base-vietnamese-sentiment)
s_lex   = tanh( k · (pos_hits − neg_hits) )    ∈ [−1,1]   (từ điển tài chính tự biên soạn)
s(t)    = (1 − α)·s_model + α·s_lex            ∈ [−1,1]   ← OUTPUT CHÍNH
```
- **Hai "lens" rời rạc hoá** (chỉ để trình bày, không phải method khác): `polarity` (pos nếu s>0,
  neg nếu s≤0) và `label_3cls` (pos/neg/neutral qua ngưỡng τ).
- **Tại sao hybrid:** model phổ thông yếu ở sắc thái tài chính ("chia cổ tức" bị chấm neutral); VN
  chưa có từ điển tài chính chuẩn (kiểu Loughran-McDonald). Lai model + từ điển vừa tận dụng ngữ
  nghĩa, vừa minh bạch (đọc được cụm nào, hệ số nào).
- **Từ điển tài chính** (`config/finance_lexicon.yml`): **122 cụm** (56 tích cực, 66 tiêu cực) + 9
  từ phủ định; ưu tiên cụm từ (tránh từ đơn đa nghĩa "tăng/giảm"); xử lý phủ định trong cửa sổ ~18 ký tự.

**Quy trình tinh chỉnh & đánh giá** (`prepare_gold.py` → `evaluate.py`)
1. Gold set: **CafeF 1.005 tiêu đề** có nhãn chuyên gia (1/2/3 → neg/neu/pos; phân bố 187/249/569).
2. Chia stratified train/test = 70/30, seed 42; cache `(s_model, net)` 1 lần cho cả 1.005 bài.
3. Tinh chỉnh `(α, k)` trên train tối ưu **binary macro-F1** → `α = 0.6`, `k = 0.8`.
4. Tinh chỉnh `τ` tối ưu 3-class macro-F1 → `τ = 0.1`. Tham số chốt lưu `output/method_config.json`.
5. Chấm toàn corpus: `run_sentiment.py --hybrid` (title + summary, cắt 256 token) →
   `output/news_sentiment_hybrid.csv` (`news_id, score, polarity, label_3cls, model_score, lex_net, prob_*`).

### Kết quả đạt được (trên TEST)
| Cấu hình | Lens | n | Accuracy | macro-F1 |
|---|---|---|---|---|
| PhoBERT thuần (argmax) | 3 lớp | 302 | 0,593 | 0,545 |
| **Hybrid (Hướng A)** | 3 lớp | 302 | **0,646** | **0,583** |
| PhoBERT thuần (sign) | Polarity | 227 | 0,815 | 0,767 |
| **★ Hybrid (Hướng A)** | **Polarity** | 227 | **0,872** | **0,827** |

→ **Hybrid > PhoBERT thuần ở cả hai lens.** Trên lens vận hành (polarity): **Accuracy 87,2% /
macro-F1 0,827**; đóng góp riêng của từ điển: **+5,7 điểm Accuracy, +6,0 điểm F1**. Per-class
polarity: negative F1 0,739 / positive F1 0,915.

**Đầu ra cuối:** `news_sentiment_hybrid.csv` (~15.791 bài có điểm sentiment) + `news_stock_mapping.csv`.

---

# PHẦN III — PHÂN TÍCH & TRỰC QUAN HOÁ (Nội dung 3)

## F. Phát hiện điểm thay đổi giá (Change-Point Detection — PELT)

**Mục tiêu:** Tìm những ngày giá "gãy xu hướng" (đổi chế độ tăng/giảm đột ngột) trên 30 mã VN30.

**File:** `analysis/detect_change_points.py` (báo cáo: `BAO_CAO_CPD.md`)

### Luồng xử lý (cho từng mã)
1. **Đầu vào:** cột `log_return` từ `technical_indicators.csv` (đã có sẵn, không tính lại); bỏ NaN;
   bỏ mã < 100 ngày.
2. **Chuẩn hoá** log-return về zero-mean, unit-std → dùng chung một ngưỡng penalty cho mọi mã.
3. **Chạy PELT** (`ruptures.Pelt(model="l2")`) — cost = tổng bình phương lệch khỏi mean mỗi đoạn,
   phù hợp tín hiệu "đổi mức trung bình của return".
4. **Penalty:** `pen = c · log(n)` với **`c = 0.5`** (≈ 3,49 cho n≈1.057). Đã thử c=3 (quá ít, 11 CP),
   c=1 (155 CP), **c=0.5 (455 CP, đúng target ~10-15 CP/mã, phủ 30/30 mã)**.
5. **Gán hướng & độ lớn** mỗi CP với cửa sổ 20 ngày trước/sau (trên log-return gốc):
   `direction = sign(mean(after) − mean(before)) ∈ {+1,−1}`, `magnitude = |mean(after) − mean(before)|`.
6. **Vẽ minh hoạ** 6 mã đại diện + histogram CP/mã.

### Đầu ra
- `analysis/output/change_points.csv` — `(symbol, change_point_date, direction, magnitude)`, **455 dòng**.
- `output/plots/cp_*.png` (giá + vạch CP) + `cp_count_per_symbol.png`.

### Kết quả đạt được
| Chỉ tiêu | Giá trị |
|---|---|
| Tổng CP | **455** (30/30 mã) |
| Penalty | PELT model=l2, `c = 0.5` |
| CP/mã | trung bình 15,2 · median 15 · min 7 (TPB) · max 25 (VIC) |
| Cân bằng hướng | 234 tăng (+1) / 221 giảm (−1) — không lệch hệ thống |
| Magnitude | mean 1,18% · max 4,39% (HPG 2022-11-15) |

**Sanity check thuyết phục:** HPG & GVR cùng có CP tăng ngày **2022-11-15** → PELT bắt đúng
*market-wide regime shift* (đáy thị trường VN trước nhịp hồi cuối 2022). Phân bố CP theo năm khớp
thực tế (2022 nhiều nhất 206 CP, 2024 yên nhất 19 CP, 2025 sôi động trở lại 126 CP).

---

## G. Đánh giá tương quan giá ↔ tin tức (trọng tâm đề tài)

**Mục tiêu:** Trả lời câu hỏi đề tài — *tin tức tích cực/tiêu cực có đi cùng hướng với các điểm
biến động giá bất thường không?*

**File:** `analysis/evaluate_correlation.py` (báo cáo: `BAO_CAO_MOC4.md`)

### Luồng xử lý — pipeline 6 bước
1. **Load & join:** `news_sentiment_hybrid.csv` (dedup theo `news_id`) + `news_stock_mapping.csv`
   + `news_links.csv` (lấy ngày) + `change_points.csv` → mỗi dòng = `(news_id, symbol-or-MARKET, date, score)`.
2. **Tính `daily_sentiment(symbol, date)`** = `mean(score)`, `n_news` → **~20.882 dòng**, ghi
   `output/daily_sentiment.csv`.
3. **Encode tăng tốc:** date → int (days-since-epoch), symbol → int code; sort theo date để
   **binary search** (numpy searchsorted) thay vì quét tuyến tính.
4. **Match per CP:** với mỗi CP, lấy tin trong cửa sổ **[−3, +1] ngày** gắn mã `symbol(CP)` HOẶC
   `MARKET`; tính `mean_score`; **match** nếu `sign(direction) == sign(mean_score)`.
5. **Permutation test** (1.000 lần): tráo ngày các tin theo `news_id` (giữ score + symbol) → phân
   phối null cho match rate → p-value.
6. **Bootstrap 95% CI** (1.000 resample các CP có signal).

**Định nghĩa chính xác:** cửa sổ `[cp_date−3, cp_date+1]` (5 ngày); coverage = % CP có ≥1 tin khớp;
match rate = % CP có sentiment cùng hướng; permutation 2 phía quanh trung bình null.

### Đầu ra
`correlation_summary.csv` (per-mã: n_cp, coverage, match_rate) · `correlation_tests.json` (observed
+ permutation + bootstrap) · `null_rates.npy` · 3 biểu đồ (`permutation_null_histogram.png`,
`match_rate_by_symbol.png`, `price_sentiment_cp_{VCB,HPG,VIC}.png`).

### Kết quả đạt được
| Chỉ số | Giá trị | Diễn giải |
|---|---|---|
| **Coverage** | **99,3%** (452/455) | hầu như mọi CP đều có tin trong cửa sổ |
| **Match rate** | **50,44%** (228/452) | gần như ngẫu nhiên |
| Permutation null mean | 0,4973 (std 0,0377) | đúng kỳ vọng ngẫu nhiên 50% |
| **p-value (2 phía)** | **0,87** | **KHÔNG bác H₀** ở α=0.05 |
| **Bootstrap 95% CI** | **[45,8%, 55,3%]** | **chứa 50%** |

**Kết luận trung thực:** Trên **tổng thể VN30**, sentiment tin tức **không có liên hệ thống kê đủ
mạnh** với hướng điểm thay đổi giá (cửa sổ ±3 ngày). Theo định hướng đề tài (§7), đây là **kết quả
hợp lệ** — đo đúng phương pháp, kết luận thẳng thắn. Có **biến thiên đáng kể per-symbol** (VCB/SSB
0,727; CTG 0,714; VIC 0,680 cao — ACB/HDB/LPB <40% thấp) nhưng cỡ mẫu mỗi mã chỉ 7–25 CP nên chỉ
**aggregate mới đủ power** để kết luận. Các hạn chế đã ghi nhận (làm hướng nghiên cứu tiếp): coverage
quá cao làm loãng tín hiệu, gộp MARKET trung hoà signal, sentiment cắt 256 token, cửa sổ cố định,
báo VN có thể *theo sau* giá (endogeneity).

---

## H. Tích hợp dữ liệu lên Supabase + Dashboard

**Mục tiêu:** Gom toàn bộ kết quả (giá, KPI, tin, sentiment, CP, tương quan) lên một CSDL tập trung
và trực quan hoá thành dashboard tương tác.

**Thư mục:** `realtimeweb copy/` (bản dashboard mới nhất, đúng đồ án) — React 18 + Vite + Chart.js +
Supabase + Gemini 2.0 Flash.

### H.1 Lớp lưu trữ — Supabase (PostgreSQL)
12 bảng đã có dữ liệu:

| Bảng | Rows | Nguồn |
|---|---|---|
| `companies` | 1.705 | vnstockprice |
| `stock_prices` | 33.218 | OHLCV |
| `technical_indicators` | 31.710 | KPI (mục C) |
| `vn30_constituents` | 50 | lịch sử rổ VN30 |
| `news_links` / `news_content` | 15.791 / 15.791 | crawler (mục D) |
| `news_stock_mapping` | ~43.380 | gắn mã (mục E.1) |
| `news_sentiment` | 15.791 | hybrid sentiment (mục E.2) |
| `daily_sentiment` | 20.882 | aggregate (mục G) |
| `change_points` | 455 | PELT (mục F) |
| `correlation_summary` / `correlation_tests` | 30 / 1 | tương quan (mục G) |

### H.2 Pipeline cập nhật dữ liệu
- **`pipeline/refresh.py`** (tự chạy khi `npm start`): (1) lấy VN30 hiện hành từ vnstock; (2) fetch
  giá OHLCV **incremental** (từ max date trong DB → hôm nay, rate-limit ~17 req/phút); (3) tính lại
  KPI cho dữ liệu mới (lấy thêm history để MA/RSI đủ ấm); (4) UPSERT lên Supabase; (5) fetch HOSE
  Index. **Không** tự động crawl tin / re-sentiment / re-CPD (chạy thủ công khi cần).
- **`pipeline/upload_initial.py`** (`npm run upload`): upload 1 lần toàn bộ CSV output → 12 bảng.

### H.3 Giao diện — 6 trang
| Trang | Nội dung | Nội dung đề tài |
|---|---|---|
| 📊 Tổng quan | 5 KPI card + giá 1 mã + bảng VN30 | Tổng hợp |
| 📈 Giá & KPI | Biểu đồ giá nến + KPI + bảng giá | Nội dung 1 |
| 📰 Tin tức & Sentiment | Tin + score sentiment | Nội dung 2 |
| 🎯 **Điểm thay đổi** | **drill-down per mã** | **Nội dung 3 + tương quan** |
| 🤖 AI Phân tích | Gemini chat đọc context từ DB | — |
| 🔧 Pipeline | Đếm rows + ngày mới nhất mỗi bảng | Monitoring |

**Trang "Điểm thay đổi"** (`ChangePointsView.jsx`) là nơi **ghép toàn bộ luồng** lại: chọn 1 mã VN30
→ hiển thị (1) 9 KPI card (RSI, MACD, MA20/50, Bollinger %b, volatility, return, drawdown, OBV, số
CP); (2) **biểu đồ giá Close + đường Sentiment MA10 + vạch dọc đỏ/xanh tại mỗi điểm thay đổi**
(Chart.js plugin tự vẽ); (3) bảng tin tức về mã kèm badge sắc thái + score; (4) KPI aggregate toàn
VN30 (coverage, match rate, p-value, CI) + bảng match rate per mã (click để chọn mã). Đây chính là
hiện thực hoá trực quan của câu hỏi đề tài: *quanh mỗi điểm giá gãy xu hướng, tin tức nói gì và cùng
hướng hay không.*

**AI Chat (Gemini):** tự kéo context từ Supabase (10 tin mới + tổng hợp sentiment + 15 CP gần nhất +
kiểm định tương quan + giá theo mã được hỏi); cấu hình **không gợi ý mua/bán, không tuyên bố nhân
quả** — chỉ "liên hệ thống kê" (đúng phạm vi mô tả/đối chiếu của đề tài).

---

# TÓM TẮT TRẠNG THÁI CÁC PHẦN

| # | Phần công việc | Trạng thái | Kết quả chính |
|---|---|---|---|
| A | Thu thập giá VN30 | ✅ | 50 bản ghi lịch sử rổ + OHLCV 2012–2026, 3 file chuẩn Supabase |
| B | EDA dữ liệu giá | ✅ | 96.849 dòng, 0% thiếu, phân tích phân phối/biến động/tương quan |
| C | Tính KPI | ✅ | `technical_indicators.csv` — **31.710 dòng × 22 cột**, 15 KPI, 0 NaN |
| D | Crawler tin tức | ✅ | **~15.791 bài** 2022–2026, 4 nguồn, 2 file CSV liên kết |
| E | Gắn mã + Sentiment | ✅ | Hybrid PhoBERT+Lexicon, **polarity acc 87,2% / F1 0,827**; mapping ~44.331 dòng |
| F | Phát hiện điểm thay đổi (PELT) | ✅ | **455 CP**, c=0.5, 30/30 mã, 234↑/221↓ |
| G | Đánh giá tương quan | ✅ | coverage 99,3%, match rate 50,44%, **p=0,87 (không bác H₀)**, CI [45,8%, 55,3%] |
| H | Tích hợp + Dashboard | ✅ | 12 bảng Supabase + dashboard React 6 trang + AI chat |
```
