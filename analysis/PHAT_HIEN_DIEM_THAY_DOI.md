# Phát hiện điểm thay đổi — Đơn giản
## (kèm đánh giá thống kê liên hệ sentiment ↔ thay đổi giá)

> Phục vụ **Mốc 3 + Mốc 4** đồ án *"Thu thập, xử lý và đánh giá tương quan thay đổi giá
> chứng khoán với tin tức"*.
>
> **Tinh thần** — đây là **phân tích MỐI LIÊN HỆ thống kê** theo truyền thống **event-study
> modernized** (MacKinlay 1997; Corrado 1989), **không** dự báo và **không** tuyên bố nhân quả.
> Đây là *thiết kế chủ động* — đúng chuẩn mực dòng nghiên cứu sentiment ↔ giá.

---

## Tóm tắt

| | |
|---|---|
| **CPD** | PELT trên log-return từng mã (1 thuật toán, 1 penalty) |
| **Đánh giá liên hệ — BẮT BUỘC** | Coverage + Match rate quanh CP, kèm **Permutation test** + **Bootstrap 95% CI** + 2-3 biểu đồ |
| **TUỲ CHỌN** (robustness) | Pearson/Spearman, Welch t-test, Mann-Whitney, FDR Benjamini-Hochberg |
| **Output** | `change_points.csv`, `daily_sentiment.csv`, `correlation_summary.csv`, `correlation_tests.json`, `plots/` |
| **Tiền lệ trực tiếp** | *Sentiment correlation in financial news networks and associated market movements* (Scientific Reports, 2021) — cùng pipeline, kết luận *"weak but statistically significant association"* |

---

## 1. Mục tiêu

Hai câu hỏi đồ án trả lời:

1. **Có ngày nào giá "gãy xu hướng"?** → CPD
2. **Quanh ngày đó, sentiment tin tức có khác bình thường một cách có ý nghĩa thống kê (không phải ngẫu nhiên) không?** → đánh giá *liên hệ*

**Khung kết luận có thể đưa ra** (tinh thần event study, không vượt quá):

- ✅ *"Có / không có mối LIÊN HỆ thống kê giữa sentiment và điểm thay đổi giá."*
- ✅ *"Match rate quanh CP cao/thấp hơn mức ngẫu nhiên với p = …"*
- ❌ *"Tin tức GÂY RA biến động giá"* (claim nhân quả — vượt phạm vi).
- ❌ *"Sentiment hôm nay DỰ BÁO giá ngày mai"* (claim dự báo — vượt phạm vi).

---

## 2. Phát hiện điểm thay đổi (CPD) — đơn giản

### 2.1 Phương pháp: 1 thuật toán, 1 chuỗi, 1 tham số

- **Đầu vào**: `stock_prices.csv` (đã có từ Mốc 1).
- **Chuỗi**: log-return ngày `r_t = log(P_t / P_{t−1})`.
- **Thuật toán**: **PELT** (`ruptures.Pelt(model="rbf")`).
- **Penalty cố định**: `pen = c · log(n) · Var(r)` với `c = 1.0` (chỉnh nếu quá nhiều/ít CP; mục tiêu ~10-15 CP/mã/4 năm; kiểm bằng mắt trên 1-2 mã).

### 2.2 Gán hướng & độ lớn cho mỗi CP

Với mỗi điểm `t*`:

```
direction = sign( mean(r_{t*+1..t*+20}) − mean(r_{t*−20..t*−1}) )      ∈ {+1, −1}
magnitude = | mean(r_{t*+1..t*+20}) − mean(r_{t*−20..t*−1}) |
```

### 2.3 Đầu ra — `change_points.csv`

| Cột | Mô tả |
|---|---|
| `symbol` | mã VN30 hoặc `VNINDEX` |
| `change_point_date` | ngày điểm thay đổi |
| `direction` | +1 (tăng) / −1 (giảm) |
| `magnitude` | độ lớn chênh lệch trung bình return |

---

## 3. Đánh giá liên hệ — bắt buộc + tuỳ chọn

### 3.1 Chuẩn bị dữ liệu

Join 3 nguồn → `daily_sentiment`:

```
news_sentiment_hybrid.csv  +  news_stock_mapping.csv  +  news_links.csv
     (news_id → score)        (news_id → symbol)         (news_id → date)

→ daily_sentiment(symbol, date) = mean(score) các tin về symbol đó (gộp cả MARKET) ngày đó
   n_news(symbol, date)         = số tin
```

### 3.2 BẮT BUỘC — 4 chỉ số cốt lõi

#### Chỉ số 1 — Coverage (mô tả)

```
Coverage = % CP có ≥ 1 tin trong cửa sổ [−3, +1] ngày (cùng mã hoặc MARKET)
```

Trả lời: *tin tức có "có mặt" quanh CP hay không?*

#### Chỉ số 2 — Match rate (mô tả)

Trong các CP có tin:

```
Match rate = % CP có  sign(direction_CP) == sign(mean_score trong cửa sổ)
```

Trả lời: *khi giá giảm/tăng, sentiment có cùng hướng không?*

#### Chỉ số 3 — Permutation test cho match rate ★

- **H₀**: tin tức xuất hiện ngẫu nhiên quanh CP → match rate quan sát chỉ là tình cờ.
- **Cách làm**:
  1. Quan sát `match_obs`.
  2. Tráo **1.000 lần** ngày của các tin (giữ nguyên `score`, đổi `date`).
  3. Tính `match_perm` mỗi lần → phân phối null.
  4. **p-value** = `(số lần match_perm ≥ match_obs) / 1000`.
- **Kết luận**: `p < 0.05` → **bác H₀** → sentiment có **liên hệ thống kê** với CP, không phải ngẫu nhiên.

> **Cơ sở**: chính là biến thể chuẩn của **Corrado (1989)** — nonparametric rank test cho event
> study (J. Financial Economics), tiền lệ kinh điển trong tài chính khi giả định Gaussian yếu.

#### Chỉ số 4 — Bootstrap 95% CI cho match rate ★

- Resample các cặp `(CP, sentiment_trong_cửa_sổ)` **có hoàn lại** 1.000 lần.
- Tính match rate mỗi lần → phân phối bootstrap.
- **95% CI** = `[percentile_2.5, percentile_97.5]`.
- **Kết luận**: *"match rate = X% [95% CI: Y%, Z%]"*. Nếu CI **không chứa 50%** (mức ngẫu nhiên) → liên hệ ổn định, không phải may rủi.

> **Cơ sở**: Efron & Tibshirani (1993) — nonparametric CI cho thống kê có phân phối phức tạp.

### 3.3 Biểu đồ minh hoạ (bắt buộc — 2 đến 3 cái)

1. **Giá + sentiment + CP** cho VN-Index (và 1-2 mã đại diện): biểu đồ giá nến + đường
   `daily_sentiment` overlay + đánh dấu các CP.
2. **Histogram permutation null**: phân phối `match_perm` (1.000 mẫu), vạch đứng tại `match_obs`
   → trực quan p-value.
3. *(tuỳ chọn)* **Bar chart**: match rate per mã VN30 + thanh sai số 95% CI.

### 3.4 TUỲ CHỌN — chỉ làm nếu rảnh (robustness check)

| Cái | Cách dùng |
|---|---|
| **Pearson + Spearman** | `scipy.stats.pearsonr/spearmanr(daily_sentiment, daily_return)` per mã, lag 0 và 1 |
| **Welch t-test** | `scipy.stats.ttest_ind(sample_quanh_CP, sample_thuong, equal_var=False)` |
| **Mann-Whitney U** | `scipy.stats.mannwhitneyu(...)` — nonparametric phiên bản của Welch |
| **FDR Benjamini-Hochberg** | `statsmodels.stats.multitest.multipletests(pvals, method="fdr_bh")` — khi test trên 30 mã |

Không bắt buộc cho thesis — chỉ là *robustness check*. Nếu kết quả từ 4 test tuỳ chọn này
**đồng thuận** với 2 test bắt buộc → kết luận càng mạnh.

### 3.5 Đầu ra

| File | Nội dung |
|---|---|
| `correlation_summary.csv` | per mã: `coverage, match_rate, n_cp, n_cp_with_news` |
| `correlation_tests.json` | `permutation_p, bootstrap_ci_low, bootstrap_ci_high` per mã + tổng VN30 |
| `plots/` | 2-3 biểu đồ ở 3.3 |

---

## 4. Cơ sở lý thuyết — 14 tài liệu, 4 nhóm

> **Tiền lệ trực tiếp cho thesis**: *Sentiment correlation in financial news networks and associated
> market movements* (**Scientific Reports**, Nature, 2021) — cùng pipeline (CPD + sentiment +
> event-window association). Kết luận: *"weak but statistically significant association between
> strong media sentiment and abnormal market return and volatility"*. Khẳng định pipeline là
> *general-purpose framework* → thesis có quyền nhắm tới kết luận tương tự (liên hệ yếu nhưng có
> ý nghĩa thống kê) — đây là kết quả phổ biến và hoàn toàn hợp lệ trong dòng này.

### A. Event-study methodology (khung chính)

1. **MacKinlay, A. C. (1997).** *Event Studies in Economics and Finance.* J. Economic Literature,
   35(1) — bài tổng quan kinh điển, dùng làm khung.
2. **Corrado, C. J. (1989).** *A nonparametric test for abnormal security-price performance in
   event studies.* J. Financial Economics, 23(2), 385–395 — **tiền lệ trực tiếp cho permutation
   test trong event study**.
3. **Kolari, J. W. & Pynnonen, S. (2011).** *Nonparametric Rank Tests for Event Studies.*
   J. Empirical Finance, 18(5) — mở rộng Corrado, vẫn được dùng rộng.
4. *Single-firm inference in event studies via the permutation test* (Empirical Economics, 2024)
   — permutation test trong event study, gần đây nhất, đúng vấn đề.

### B. Sentiment ↔ giá (association style)

5. **Tetlock, P. C. (2007).** *Giving Content to Investor Sentiment.* J. Finance, 62(3).
6. **Antweiler, W. & Frank, M. Z. (2004).** *Is All That Talk Just Noise?* J. Finance, 59(3).
7. **Bollen, J., Mao, H. & Zeng, X. (2011).** *Twitter mood predicts the stock market.*
   J. Computational Science.
8. **Engelberg, J. E. & Parsons, C. A. (2011).** *The Causal Impact of Media in Financial
   Markets.* J. Finance, 66(1).
9. *Sentiment correlation in financial news networks and associated market movements.*
   **Scientific Reports** (Nature), 2021 — **tiền lệ trực tiếp**, arXiv 2011.06430.

### C. CPD (Phát hiện điểm thay đổi)

10. **Killick, R., Fearnhead, P. & Eckley, I. A. (2012).** *Optimal Detection of Changepoints
    With a Linear Computational Cost.* JASA, 107(500) — **PELT** (thuật toán dùng chính).
11. **Truong, C., Oudre, L. & Vayatis, N. (2020).** *Selective review of offline change point
    detection methods.* Signal Processing, 167 — paper nền của thư viện `ruptures`.
12. **Aminikhanghahi, S. & Cook, D. J. (2017).** *A survey of methods for time series change
    point detection.* KAIS, 51(2).

### D. Nonparametric inference (nền cho permutation + bootstrap)

13. **Good, P. (2005).** *Permutation, Parametric, and Bootstrap Tests of Hypotheses* (3rd ed.).
    Springer.
14. **Efron, B. & Tibshirani, R. (1993).** *An Introduction to the Bootstrap.* Chapman & Hall.

---

## 5. Hạn chế — thiết kế chủ động, không phải khuyết

Các điểm dưới đây **là thiết kế** của phương pháp event-study, không phải lỗ hổng:

1. **KHÔNG tuyên bố nhân quả** *(THIẾT KẾ)* — event study only documents *association*, không
   claim causation. Bác H₀ chỉ chứng minh sentiment không xuất hiện ngẫu nhiên quanh CP, không
   nói tin *gây ra* biến động giá. (Engelberg & Parsons 2011 dùng identification strategy đặc
   biệt — nằm ngoài phạm vi đồ án.)
2. **KHÔNG dự báo** *(THIẾT KẾ)* — phân tích **hậu nghiệm** (retrospective): phát hiện CP rồi
   mới xem tin. Đồ án không xây model dự báo.
3. **Endogeneity của tin** — tin có thể *phản ứng* giá (đặc biệt khi đăng cuối ngày). Lag 1
   giảm vấn đề này nhưng không xoá hết.
4. **Cửa sổ [−3, +1] là lựa chọn** — nên báo cáo độ nhạy với khung khác ([−5, +2], [−1, +1]).
5. **Gắn mã chưa hoàn hảo** — bài liệt kê nhiều mã có sai số (xem `HUONG_A_HYBRID_SENTIMENT.md`
   mục 4.4); có thể lọc bài >5 mã trước khi tổng hợp.
6. **Multiple testing** — 30 mã × test → một số p < 0.05 có thể false positive. Nếu báo cáo
   *per-symbol*: dùng **FDR Benjamini-Hochberg** (tuỳ chọn, mục 3.4); nếu chỉ báo cáo *aggregate*
   (trung bình VN30): không cần.

---

## Phụ lục — Cấu trúc file & cách chạy

```
analysis/                                       (thư mục mới)
├── PHAT_HIEN_DIEM_THAY_DOI.md                  (tài liệu này)
├── change_points_and_correlation.ipynb         (notebook chạy đầu-cuối)
└── output/
    ├── change_points.csv
    ├── daily_sentiment.csv
    ├── correlation_summary.csv
    ├── correlation_tests.json
    └── plots/
        ├── price_sentiment_cp_vnindex.png
        ├── price_sentiment_cp_<mã>.png
        └── permutation_null_histogram.png
```

**Tiền điều kiện**:
- ✅ `stock_prices.csv` (Mốc 1)
- ⏳ `news_sentiment_hybrid.csv` (Mốc 2 — cần chạy `run_sentiment.py --hybrid` toàn corpus)
- ✅ `news_stock_mapping.csv` (`run_tag.py` đã có)

**Cách chạy** (sau khi build notebook):
```bash
cd analysis
jupyter notebook change_points_and_correlation.ipynb
# Chạy hết tuần tự: CPD → daily_sentiment → 4 chỉ số bắt buộc → plots → (tuỳ chọn)
```

**Thư viện**: `ruptures`, `scipy`, `pandas`, `numpy`, `matplotlib` (đã có/cần `pip install ruptures`);
`statsmodels` chỉ cần nếu dùng FDR (tuỳ chọn).
