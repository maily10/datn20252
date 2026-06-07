# Báo cáo Mốc 4 — Đánh giá liên hệ Sentiment ↔ Điểm thay đổi giá VN30

> Tài liệu ghi lại **kết quả thực tế** khi triển khai phần đánh giá liên hệ (§3 của
> [`PHAT_HIEN_DIEM_THAY_DOI.md`](PHAT_HIEN_DIEM_THAY_DOI.md)) trên 455 CP đã phát hiện ở Mốc 3 +
> 15.791 bài đã chấm sentiment ở Mốc 2.

---

## 1. Tóm tắt thành quả

| | |
|---|---|
| **Code** | [analysis/evaluate_correlation.py](evaluate_correlation.py) — 1 lệnh, chạy ~30 giây |
| **Đầu vào** | 455 CP (Mốc 3) + 15.791 sentiment (Mốc 2) + 44.331 mapping news↔symbol |
| **Cửa sổ quanh CP** | [−3, +1] ngày |
| **Chỉ số bắt buộc thực hiện** | ✅ Coverage · ✅ Match rate · ✅ Permutation test · ✅ Bootstrap CI · ✅ 3 biểu đồ |
| | |
| **Coverage** (mức độ có tin) | **99.3%** (452/455 CP có ≥1 tin trong cửa sổ) |
| **Match rate** (cùng hướng) | **50.44%** (228/452) |
| **Bootstrap 95% CI** | **[45.8%, 55.3%]** — chứa 50% → match rate không khác ngẫu nhiên có ý nghĩa |
| **Permutation null mean** | 49.73% (std 3.77%) |
| **p-value 2 phía** | **0.87** → **KHÔNG bác H₀** ở α=0.05 |

**Kết luận trung thực**: trên TỔNG THỂ VN30, sentiment news **không có liên hệ thống kê đủ mạnh**
với hướng điểm thay đổi giá (cửa sổ ±3 ngày). Theo plan §1 và §5 — đây là **kết quả hợp lệ**,
không phải thất bại; chúng ta đo đúng, kết luận đúng.

---

## 2. Phương pháp đã triển khai (theo thực tế)

### 2.1 Pipeline 6 bước (đã chạy đầu-cuối)

```
[1] Load: sentiment (15.791) + mapping (44.331) + links (date) + change_points (455)
[2] Join + dedup → 44.331 dòng (news_id × symbol_or_MARKET × date × score)
[3] Tính daily_sentiment(symbol, date) = mean(score), n_news → 20.882 dòng
[4] Mỗi CP: tìm tin trong cửa sổ [-3, +1] khớp (cùng mã hoặc MARKET) → coverage + match
[5] Permutation test (1000 shuffles ngày các tin) → null distribution
[6] Bootstrap 95% CI (1000 resamples các CP có signal)
```

### 2.2 Định nghĩa cụ thể

- **Cửa sổ**: `[cp_date − 3, cp_date + 1]` ngày dương lịch (5 ngày, gồm `cp_date`).
- **Tin "khớp" CP**: news_id được gắn mã `symbol(CP)` HOẶC `MARKET`.
- **mean_score trong cửa sổ**: trung bình `score` (∈ [−1, 1]) của tin khớp.
- **Match**: `sign(direction_CP) == sign(mean_score)`.
- **Permutation test (1 phía)**: shuffle 1.000 lần dates của các tin (giữ score + symbol), tính
  match rate trên dữ liệu tráo → p = P(match_perm ≥ match_obs).
- **Bootstrap 95% CI**: resample có hoàn lại 1.000 lần các 0/1 outcomes của 452 CP có signal.

### 2.3 Hiệu suất

- 1.000 permutations × 455 CP × cửa sổ 5 ngày: ~25 giây trên CPU (numpy + binary search).
- Toàn bộ pipeline kết thúc < 1 phút.

---

## 3. Kết quả định lượng chi tiết

### 3.1 Aggregate (toàn 30 mã VN30)

| Chỉ số | Giá trị | Diễn giải |
|---|---|---|
| Tổng CP | 455 | từ Mốc 3 |
| Có tin trong cửa sổ | 452 (99.3%) | hầu như mọi CP đều "có tin" |
| Có signal (mean ≠ 0) | 452 | mean liên tục, gần như không 0 chính xác |
| Match | 228 | (228/452 = 50.44%) |
| Permutation null mean | 0.4973 | rất gần 0.50, đúng kỳ vọng ngẫu nhiên |
| Permutation null std | 0.0377 | |
| **p-value 2 phía** | **0.8700** | → **KHÔNG bác H₀** |
| **Bootstrap 95% CI** | **[0.458, 0.553]** | **chứa 0.50** |

→ 2 kiểm định bắt buộc đồng thuận: **không có bằng chứng thống kê** rằng sentiment đi cùng
hướng với CP nhiều hơn ngẫu nhiên ở mức toàn-VN30.

### 3.2 Per-symbol breakdown (file `correlation_summary.csv`)

Có **biến thiên đáng kể giữa các mã**:

| Nhóm | Mã (match rate) |
|---|---|
| **Cao nhất (>60%)** | VCB **0.727** · SSB **0.727** · CTG **0.714** · VIC **0.680** · GVR **0.636** · VNM **0.636** · VPB **0.636** · BID **0.600** · MWG **0.600** |
| **Trung bình (~50%)** | HPG 0.533 · MBB 0.538 · PLX 0.529 · STB 0.500 · SAB 0.500 · VIB 0.500 · BCM 0.467 · SHB 0.467 · TCB 0.467 · VHM 0.474 · VRE 0.474 · VJC 0.444 · BVH 0.429 · FPT 0.429 · MSN 0.429 |
| **Thấp (<40%)** | TPB 0.571 (n=7) · GAS 0.375 · SSI 0.368 · LPB 0.333 · HDB 0.273 · ACB 0.250 |

**Lưu ý quan trọng về độ tin cậy per-symbol**: cỡ mẫu mỗi mã chỉ 7-25 CP, độ rộng CI 95% binomial
quanh 50% là khoảng ±25 điểm phần trăm. Vì vậy **chỉ aggregate mới đủ power** để kết luận thống
kê — per-symbol chỉ là gợi ý định hướng, không phải bằng chứng.

### 3.3 Phân bố null vs observed (Permutation test)

Biểu đồ: [`output/plots/permutation_null_histogram.png`](output/plots/permutation_null_histogram.png)

```
Null distribution (1000 shuffles):   trung bình 0.4973 · std 0.0377
                                        khoảng [0.380 — 0.620]  (≈ ±2σ)
Observed match rate:                  0.5044   ← nằm gần như giữa null distribution
```

Match rate quan sát rơi vào **giữa** phân phối null → không có dấu hiệu khác biệt.

---

## 4. Đánh giá trung thực — vì sao p > 0.05?

Đây là phần quan trọng nhất của báo cáo (theo plan §1 và §5). Các khả năng giải thích, **không
phải bào chữa mà là kết luận khoa học**:

### 4.1 Thật sự không có liên hệ mạnh

- Tin tức tài chính trên báo VN có thể **không lead giá** đủ tin cậy. Tin thường *theo sau*
  diễn biến giá (báo viết về cú giảm sau khi giảm), gây *endogeneity* — đã ghi nhận trong
  [`PHAT_HIEN_DIEM_THAY_DOI.md`](PHAT_HIEN_DIEM_THAY_DOI.md) §5 mục 3.
- Souza et al. (2021, Scientific Reports) tìm thấy *"weak but statistically significant"* —
  ở thị trường VN, signal có thể *yếu hơn nữa* và không đạt ngưỡng có ý nghĩa.

### 4.2 Coverage quá cao làm loãng tín hiệu

99.3% CP có tin → gần như mọi CP có "ai đó nói gì đó" trong cửa sổ. Với:
- Trung bình ~15 tin/ngày
- Cộng cả MARKET (5.972 tin) + tin các mã VN30 khác → cửa sổ ±3 ngày trung bình có ~75 tin

→ `mean_score` bị **trung hoà bởi tin nhiễu, không liên quan**. Đây là hạn chế nội tại của
việc gộp cả MARKET. Có thể thử: chỉ tính tin gắn mã trực tiếp, không gồm MARKET.

### 4.3 Biến thiên per-symbol gợi ý có signal ở mã nhất định

- 9 mã có match rate ≥ 60% (VCB, SSB, CTG, VIC, GVR, VNM, VPB, BID, MWG)
- 5 mã có match rate ≤ 40% (ACB, HDB, LPB, SSI, GAS)

→ Có thể signal **tồn tại ở mã có tin chuyên biệt nhiều** (ngân hàng lớn, blue-chip có tin sát
sườn) nhưng bị **trung hoà** khi gộp với mã ít/khó gắn mã (HDB, LPB ít tin → match xấu).

### 4.4 Cửa sổ [−3, +1] có thể không tối ưu

Chưa robustness check với cửa sổ khác. Có thể tin tác động ngắn hạn (±1 ngày) hoặc dài hơn (±5).

### 4.5 Chất lượng sentiment

Đã đánh giá ở Mốc 2: polarity F1 = 0.813 trên gold CafeF. Nhưng:
- Gold = title-only, lệch domain so với corpus crawler (4 báo VN khác).
- Pipeline cắt 256 tokens (không full content) — đã ghi nhận hạn chế.

---

## 5. Biểu đồ minh hoạ

| File | Mô tả |
|---|---|
| [`permutation_null_histogram.png`](output/plots/permutation_null_histogram.png) | Phân phối null 1.000 shuffles + vạch đứng observed = 0.504, null mean = 0.497 |
| [`match_rate_by_symbol.png`](output/plots/match_rate_by_symbol.png) | Bar chart per-symbol match rate, xanh nếu ≥50%, đỏ nếu <50% |
| [`price_sentiment_cp_VCB.png`](output/plots/price_sentiment_cp_VCB.png) | Giá VCB + daily_sentiment (MA20) + vạch CP (xanh tăng / đỏ giảm) |
| [`price_sentiment_cp_HPG.png`](output/plots/price_sentiment_cp_HPG.png) | Tương tự cho HPG |
| [`price_sentiment_cp_VIC.png`](output/plots/price_sentiment_cp_VIC.png) | Tương tự cho VIC |

---

## 6. Đầu ra & cấu trúc file

```
analysis/output/
├── change_points.csv               # Mốc 3 (455 CP)
├── daily_sentiment.csv             # 20.882 dòng (mã × ngày, mean_score + n_news)
├── correlation_summary.csv         # 30 mã: n_cp, coverage, match_rate
├── correlation_tests.json          # observed + permutation + bootstrap CI
├── null_rates.npy                  # phân phối null (1000 giá trị) — dùng lại nếu cần
└── plots/
    ├── permutation_null_histogram.png    ★ chứng minh / không chứng minh
    ├── match_rate_by_symbol.png          ★ overview per-symbol
    ├── price_sentiment_cp_VCB.png
    ├── price_sentiment_cp_HPG.png
    └── price_sentiment_cp_VIC.png
```

**Reproduce** (1 lệnh, ~30 giây):
```bash
cd analysis
python evaluate_correlation.py
```

---

## 7. So sánh với tiền lệ

| | **Souza et al. (2021)** Sci Reports | **Đồ án này** |
|---|---|---|
| Đối tượng | Cổ phiếu Mỹ, Reuters financial news | VN30, 4 báo tài chính VN |
| Pipeline | CPD + sentiment network + association | CPD + sentiment hybrid + association |
| Kết luận | *weak but statistically significant association* | **không có liên hệ thống kê** ở tổng thể (p=0.87) |

→ Kết quả của đồ án **yếu hơn tiền lệ** — phù hợp với (a) sentiment VN khó hơn (không lexicon
tài chính chuẩn, đã ghi ở Mốc 2), (b) corpus tin VN có thể có nhiều noise hơn Reuters,
(c) báo VN có thể *theo sau* giá nhiều hơn dẫn dắt.

---

## 8. Hạn chế đã ghi nhận

1. **Sentiment cắt 256 tokens, chỉ dùng title + summary** — Mốc 2 đã nêu; ảnh hưởng signal-to-noise.
2. **Gắn mã document-level, bài liệt kê đa mã không lọc** — có thể làm loãng matching.
3. **Cửa sổ [−3, +1] cố định** — chưa robustness check.
4. **Aggregate-only kiểm định** — per-symbol không đủ power (n=10-25 mỗi mã).
5. **Tin MARKET có thể trung hoà signal** — có thể thử chỉ giữ tin gắn mã trực tiếp.
6. **PELT penalty c=0.5 cố định** — chưa per-symbol tune; có thể CP "ít quan trọng" làm loãng tín hiệu.

Tất cả 6 hạn chế đều là **hướng nghiên cứu tiếp**, không phải lỗi.

---

## 9. Sẵn sàng cho Mốc 5 (Dashboard)

Cả `change_points.csv`, `daily_sentiment.csv`, `correlation_summary.csv` đã chuẩn hoá — sẵn
sàng load vào **Streamlit** để dashboard hiển thị:
1. Biểu đồ giá + đánh dấu CP per mã.
2. Đường daily_sentiment overlay.
3. Bảng tổng hợp tương quan per mã.
4. Click CP → liệt kê tin trong cửa sổ ±3 ngày.

---

## 10. Tham khảo

(chi tiết xem [`PHAT_HIEN_DIEM_THAY_DOI.md`](PHAT_HIEN_DIEM_THAY_DOI.md) §4)

- **Killick et al. (2012)** — PELT (CPD)
- **Corrado (1989)** — nonparametric event-study test (tiền lệ của permutation cho match rate)
- **MacKinlay (1997)** — Event Studies in Economics and Finance (khung tổng quan)
- **Souza et al. (2021)** — Scientific Reports, *Sentiment correlation in financial news networks*
  (tiền lệ trực tiếp)
- **Efron & Tibshirani (1993)** — bootstrap CI
- **Good (2005)** — permutation tests
- **Tetlock (2007)** — sentiment ↔ giá, J. Finance
