# Báo cáo Mốc 3 — Phát hiện điểm thay đổi giá VN30

> Tài liệu này ghi lại **kết quả thực tế đã đạt** sau khi triển khai phương án trong
> [`PHAT_HIEN_DIEM_THAY_DOI.md`](PHAT_HIEN_DIEM_THAY_DOI.md). Đầu vào Mốc 4 đã sẵn sàng.

---

## 1. Tóm tắt thành quả

| | |
|---|---|
| **Phạm vi** | 30 mã VN30, từ 2022-01-04 → 2026-04-03 (31.710 phiên giao dịch) |
| **Thuật toán** | PELT (`ruptures`, `model="l2"`) trên log-return đã chuẩn hoá |
| **Tham số đã chốt** | `penalty = c · log(n)` với **`c = 0.5`** (sau khi thử c=3, 1, 0.5 — chi tiết §3) |
| **Số điểm thay đổi (CP) phát hiện** | **455 CP**, đều khắp **30/30 mã** |
| **Cân bằng hướng** | 234 tăng (+1) / 221 giảm (−1) — không lệch hệ thống |
| **Phân bố CP/mã** | trung bình 15.2 · trung vị 15 · min 7 · max 25 — đúng target plan |
| **File đầu ra** | `analysis/output/change_points.csv`, `analysis/output/plots/*.png` |
| **Code** | `analysis/detect_change_points.py` (~150 dòng, chạy 1 lệnh) |

---

## 2. Phương pháp đã triển khai (gọn lại theo thực tế)

### 2.1 Đầu vào

`vnstockprice/technical_indicators.csv` (đã có sẵn từ Mốc 1, 31.710 dòng × 22 cột) — dùng **cột
`log_return`** đã tính trước, không phải tính lại. Mỗi mã có ~1.057 phiên giao dịch.

### 2.2 Xử lý cho từng mã

1. Lấy chuỗi `log_return` của mã đó, bỏ NaN.
2. **Chuẩn hoá** về zero-mean, unit-std → để dùng chung một ngưỡng penalty cho mọi mã, không
   phụ thuộc thang biến động riêng.
3. Chạy **PELT** với `model="l2"` (cost = sum of squared deviations từ mean mỗi segment) — phù
   hợp khi tín hiệu CPD là **đổi mức trung bình của return**.
4. Penalty `pen = c · log(n) = 0.5 · log(~1057) ≈ 3.49`.

### 2.3 Gán hướng & độ lớn cho mỗi CP

Với mỗi index `t*` PELT báo, dùng cửa sổ **20 ngày trước/sau**:

```
direction = sign( mean(log_return[t* : t*+20]) − mean(log_return[t*−20 : t*]) )   ∈ {+1, −1}
magnitude = | mean(after) − mean(before) |
```

Tính trên log_return **gốc** (không chuẩn hoá) để magnitude có ý nghĩa đo lường thực.

### 2.4 Đầu ra — `change_points.csv` (455 dòng)

| Cột | Mô tả | Ví dụ |
|---|---|---|
| `symbol` | Mã VN30 | `HPG` |
| `change_point_date` | Ngày điểm thay đổi | `2022-11-15` |
| `direction` | +1 (regime sau cao hơn) hoặc −1 | `1` |
| `magnitude` | Chênh lệch trung bình log-return trước/sau | `0.043902` |

---

## 3. Quá trình chọn penalty `c`

Plan yêu cầu **~10-15 CP/mã/4 năm** (regime trung bình ~70-100 phiên — hợp lý cho chu kỳ trung
hạn). Đã thử 3 giá trị:

| `c` | `pen ≈ c·log(n)` | Tổng CP | CP/mã (mean) | Đánh giá |
|---|---|---|---|---|
| 3.0 | ~21 | 11 (6/30 mã) | 1.8 | **Quá nghiêm** — chỉ bắt được biến động cực mạnh |
| 1.0 | ~7 | 155 (29/30 mã) | 5.3 | Còn ít so với target |
| **0.5** | **~3.49** | **455 (30/30 mã)** | **15.2** | ✅ **Đúng target** |

→ Chốt **`c = 0.5`** — vừa khít plan, vừa cover được **toàn bộ 30 mã** (không mã nào bị bỏ).

---

## 4. Kết quả định lượng

### 4.1 Phân bố CP theo mã (sắp xếp giảm dần)

| Nhóm | Mã | CP |
|---|---|---|
| **Nhiều CP nhất** (>20) | VIC (25), GVR (22), LPB (21), BVH (21), SAB (20) |  |
| **Ít CP nhất** (<12) | TPB (7), BID (10), MWG (10), VPB (11), SSB (11) |  |

Biểu đồ: [`output/plots/cp_count_per_symbol.png`](output/plots/cp_count_per_symbol.png)

### 4.2 Phân bố CP theo năm × hướng

| Năm | ↓ giảm | ↑ tăng | Tổng | Nhận xét |
|---|---|---|---|---|
| 2022 | 90 | 116 | **206** | Năm nhiều biến động nhất — khớp giai đoạn khủng hoảng TPDN + sụp giảm 4Q/2022 |
| 2023 | 23 | 31 | 54 | Phục hồi, ít biến động |
| 2024 | 10 | 9 | 19 | Năm yên ắng nhất |
| 2025 | 64 | 62 | **126** | Sôi động trở lại |
| 2026 (Q1) | 34 | 16 | 50 | Lệch giảm — gợi ý đợt điều chỉnh đầu 2026 |

→ Phân bố này **có ý nghĩa thực tế**, không phải nhiễu — khớp với chu kỳ thị trường VN.

### 4.3 Top 5 CP có magnitude lớn nhất (sự kiện đáng chú ý)

| Mã | Ngày | Hướng | Magnitude | Khả năng diễn giải |
|---|---|---|---|---|
| **HPG** | 2022-11-15 | +1 | 0.0439 | Đáy hồi phục thép sau cú sụp Q3-Q4/2022 |
| **VHM** | 2026-01-08 | −1 | 0.0400 | Sụt mạnh đầu 2026 (cần đối chiếu tin) |
| **VPB** | 2025-08-22 | −1 | 0.0384 | Biến động giữa 2025 |
| **GVR** | 2022-11-15 | +1 | 0.0377 | Cùng ngày HPG → sự kiện toàn thị trường |
| **VRE** | 2025-10-14 | −1 | 0.0353 | Q4/2025 |

→ **HPG & GVR cùng ngày 2022-11-15** là dấu hiệu thuyết phục: PELT bắt đúng *market-wide regime
shift* (đáy thị trường trước nhịp hồi cuối 2022 — sự kiện thực tế thị trường VN ai cũng biết).
Đây là **sanity check tự nhiên** rằng thuật toán hoạt động đúng.

### 4.4 Biểu đồ giá + CP cho 6 mã đại diện

| Mã | File | # CP |
|---|---|---|
| VCB | [`output/plots/cp_VCB.png`](output/plots/cp_VCB.png) | 11 |
| HPG | [`output/plots/cp_HPG.png`](output/plots/cp_HPG.png) | 15 |
| FPT | [`output/plots/cp_FPT.png`](output/plots/cp_FPT.png) | 14 |
| VIC | [`output/plots/cp_VIC.png`](output/plots/cp_VIC.png) | 25 |
| MWG | [`output/plots/cp_MWG.png`](output/plots/cp_MWG.png) | 10 |
| VNM | [`output/plots/cp_VNM.png`](output/plots/cp_VNM.png) | 12 |

(xanh = chuyển sang regime tăng; đỏ = chuyển sang regime giảm)

---

## 5. Đánh giá chất lượng (sanity check)

| Tiêu chí | Kết quả | Đánh giá |
|---|---|---|
| Mọi mã đều có CP | 30/30 | ✅ |
| Số CP/mã hợp lý (~10-15) | mean 15.2, median 15 | ✅ đúng target |
| Cân bằng tăng/giảm | 234 / 221 (51% / 49%) | ✅ không bias |
| CP "sự kiện chung" được bắt | HPG & GVR cùng ngày 2022-11-15 | ✅ thuật toán hoạt động |
| Phân bố theo năm phản ánh thị trường | 2022 nhiều, 2024 yên, 2025 sôi | ✅ khớp thực tế |
| Magnitude có ý nghĩa | mean 1.18%, max 4.39% | ✅ đo bằng đơn vị return |

---

## 6. Hạn chế đã ghi nhận

1. **Chưa làm cho VN-Index** — `technical_indicators.csv` chỉ có 30 VN30. Có thể bổ sung sau bằng
   cách tính log-return từ `stock_prices.csv` (chỉ số hoặc xây từ VNINDEX nếu có trong dữ liệu giá).
2. **Penalty cố định cho cả 30 mã** — không tinh chỉnh per-mã. Hậu quả: TPB chỉ có 7 CP còn VIC
   25 CP. Sự khác biệt này phản ánh đúng biến động riêng nhưng chưa được kiểm soát chặt.
3. **Cửa sổ ±20 ngày gán hướng/magnitude là lựa chọn cố định** — chưa robustness check với cửa
   sổ khác. Có thể bổ sung khi vào Mốc 4 nếu cần.
4. **PELT là offline CPD** — chỉ chạy hậu kiểm (retrospective), không phát hiện real-time. Phù
   hợp mục tiêu phân tích tương quan, không thay model dự báo.

---

## 7. Đầu vào Mốc 4 đã sẵn sàng

`change_points.csv` (455 CP) là đầu vào trực tiếp cho **Mốc 4 — Đánh giá tương quan**:

1. Join với `daily_sentiment(symbol, date)` (tính từ `news_sentiment_hybrid.csv` sau khi bạn
   chạy xong `run_sentiment.py --hybrid`).
2. Cửa sổ [−3, +1] ngày quanh mỗi CP → 4 chỉ số bắt buộc:
   - **Coverage** (% CP có tin)
   - **Match rate** (% CP có sentiment cùng hướng với `direction`)
   - **Permutation test** cho match rate (1.000 lần shuffle)
   - **Bootstrap 95% CI** cho match rate (1.000 lần resample)
3. 2-3 biểu đồ minh hoạ (giá + sentiment + CP; histogram null).

---

## 8. Cấu trúc file & cách reproduce

```
analysis/
├── PHAT_HIEN_DIEM_THAY_DOI.md       # plan (method + cơ sở lý thuyết)
├── BAO_CAO_CPD.md                   # tài liệu này (kết quả Mốc 3)
├── detect_change_points.py          # code (1 lệnh chạy đầu-cuối)
└── output/
    ├── change_points.csv            # 455 CP
    └── plots/
        ├── cp_count_per_symbol.png  # histogram CP/mã
        ├── cp_VCB.png               # giá + CP cho VCB
        ├── cp_HPG.png               # ... và 4 mã khác
        ├── cp_FPT.png
        ├── cp_VIC.png
        ├── cp_MWG.png
        └── cp_VNM.png
```

**Reproduce** (1 lệnh, ~5-10 giây):
```bash
cd analysis
python detect_change_points.py
```

**Đổi penalty** nếu muốn ít/nhiều CP hơn — sửa hằng `PEN_C` ở đầu `detect_change_points.py`:
- `PEN_C = 1.0` → ~5 CP/mã (chỉ bắt sự kiện rõ ràng)
- `PEN_C = 0.5` → ~15 CP/mã (mặc định, plan target)
- `PEN_C = 0.3` → nhiều CP hơn (bắt cả nhiễu vừa)

---

## 9. Tham khảo nhanh (chi tiết xem `PHAT_HIEN_DIEM_THAY_DOI.md` mục 4)

- **Killick, Fearnhead & Eckley (2012)** — PELT, JASA 107(500) — thuật toán dùng chính.
- **Truong, Oudre & Vayatis (2020)** — paper nền của `ruptures`.
- **MacKinlay (1997)** — Event Studies in Economics and Finance, J. Economic Literature 35(1) —
  khung dùng các CP làm "event" cho Mốc 4.
