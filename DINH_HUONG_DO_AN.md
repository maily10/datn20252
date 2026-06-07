# Định hướng Đồ án Tốt nghiệp

**Tên đề tài:** Thu thập, xử lý và đánh giá tương quan thay đổi giá chứng khoán với tin tức

> **Tóm tắt:** Xây dựng một **hệ thống end-to-end** thu thập giá chứng khoán VN30 + tin tức tài chính, tính các **chỉ số (KPI)** từ giá, đánh giá **sắc thái tích cực/tiêu cực** của tin, **phát hiện điểm thay đổi** trên giá, rồi **đánh giá tương quan** giữa biến động giá và tin tức, trình bày trên **dashboard**. Trọng tâm là **hệ thống dữ liệu + phân tích mô tả/đối chiếu** (correlation), **không** phải dự báo.

---

## 1. Mục tiêu & phạm vi

**Mục tiêu:** Trả lời câu hỏi *"Tin tức tích cực/tiêu cực có đi cùng với những thời điểm giá chứng khoán biến động bất thường không?"* — bằng một hệ thống thu thập–xử lý–trực quan hoá hoàn chỉnh.

**Phạm vi:**
- **Cổ phiếu:** rổ **VN30** (30 mã) + chỉ số VN-Index.
- **Thời gian:** **2022 → 2026**.
- **Nguồn tin:** 4 báo tài chính (VnEconomy là chính, + Báo Đầu Tư, Thời Báo Tài Chính, Thị trường Tài chính).
- **Tính chất:** mô tả & đối chiếu tương quan (descriptive/correlation), không dự báo (prediction).

---

## 2. Kiến trúc hệ thống

```
┌─────────────────────┐         ┌─────────────────────┐
│  Thu thập GIÁ       │         │  Thu thập TIN TỨC   │
│  (vnstock OHLCV)    │         │  (crawler 4 nguồn)  │
└──────────┬──────────┘         └──────────┬──────────┘
           ▼                               ▼
┌─────────────────────┐         ┌─────────────────────┐
│  Tính KPI / chỉ số  │         │  Sentiment pos/neg  │
│  return, MA, vol,   │         │  + gắn mã cổ phiếu  │
│  RSI, MACD...       │         │                     │
└──────────┬──────────┘         └──────────┬──────────┘
           │                               │
           ▼                               ▼
┌───────────────────────────────────────────────────┐
│  PHÁT HIỆN ĐIỂM THAY ĐỔI (PELT)  +  ĐÁNH GIÁ        │
│  TƯƠNG QUAN (giá ↔ sentiment quanh điểm thay đổi)  │
└──────────────────────┬────────────────────────────┘
                       ▼
            ┌─────────────────────┐
            │     DASHBOARD       │
            │  giá+KPI+điểm+tin   │
            └─────────────────────┘
```

**Lưu trữ:** Supabase/PostgreSQL — bảng `companies`, `stock_prices`, `dim_time`, `technical_indicators` (KPI), `news_links` + `news_content` + `news_sentiment`, `change_points`.

---

## 3. Nội dung 1 — Thu thập giá + tính KPI

### 3.1 Thu thập giá
- Nguồn: thư viện **vnstock** (API dữ liệu chứng khoán VN).
- Dữ liệu: **OHLCV** ngày (open, high, low, close, volume) cho 30 mã VN30 + VN-Index, 2022-2026.
- Lưu vào `stock_prices` (symbol, date, open, high, low, close, volume).

### 3.2 Tính KPI (chỉ số kỹ thuật)
Tính từ giá đóng cửa + khối lượng, lưu vào `technical_indicators`:
| KPI | Ý nghĩa |
|---|---|
| **Daily return** `r_t = (P_t−P_{t-1})/P_{t-1}` | Tỷ suất sinh lời ngày |
| **MA(20), MA(50)** | Trung bình động — xu hướng |
| **Volatility** (độ lệch chuẩn return cuộn 20 ngày) | Mức rủi ro/biến động |
| **RSI(14)** | Chỉ báo quá mua/quá bán |
| **MACD** | Phân kỳ hội tụ trung bình động |
| **Bollinger Bands** | Dải biến động quanh MA |
| **Volume change / OBV** | Biến động khối lượng |
| **Max drawdown** | Mức sụt giảm sâu nhất |

> KPI vừa là **đầu vào** cho phát hiện điểm thay đổi, vừa là **chỉ số hiển thị** trên dashboard.

---

## 4. Nội dung 2 — Thu thập tin tức + đánh giá tích cực/tiêu cực

### 4.1 Thu thập tin (✅ đã hoàn thành)
- Crawler 4 nguồn (chi tiết: `stocknewscrawl/CRAWLER_FLOW.md`).
- Hiện có **~15.900 bài 2022-2026**, đều có ngày đăng (`news_links` + `news_content`).

### 4.2 Gắn mã cổ phiếu cho tin
- Quét nội dung tin tìm mã VN30 / tên công ty → biết tin **về mã nào**.
- Bài không gắn được mã cụ thể → coi là tin **thị trường chung**.

### 4.3 Đánh giá sentiment (đơn giản: tích cực / tiêu cực / trung lập)
- Dùng **mô hình sentiment tiếng Việt có sẵn** (pre-trained), ví dụ PhoBERT fine-tune cho sentiment, hoặc mô hình zero-shot — cho ra nhãn **pos / neg / neutral** + điểm số.
- **Không cần** kiến trúc nhiều tầng phức tạp; đủ để mỗi tin có 1 nhãn sắc thái.
- **Tổng hợp theo mã theo ngày**: với mỗi mã, tính `mean_sentiment` các tin trong ngày → "dòng cảm xúc" theo thời gian, lưu `news_sentiment`.

---

## 5. Nội dung 3 — Phát hiện điểm thay đổi + đánh giá tương quan + dashboard

### 5.1 Phát hiện điểm thay đổi (Change-Point Detection bằng PELT)
- **Mục tiêu:** tìm những ngày giá "gãy xu hướng" — chuỗi giá đổi chế độ tăng/giảm đột ngột.
- **Cách làm:** dùng thuật toán **PELT** (thư viện `ruptures`) trên chuỗi **log-return**.
  - PELT quét toàn chuỗi, tìm tập điểm chia tối ưu sao cho mỗi đoạn "đồng nhất" về mức trung bình/độ biến động; tham số **penalty** điều khiển bắt nhiều hay ít điểm.
  - Độ phức tạp tuyến tính O(n) → chạy nhanh.
- **Kết quả:** mỗi điểm thay đổi gồm `(mã, ngày, hướng tăng/giảm, độ lớn)`, lưu `change_points`.

### 5.2 Đánh giá tương quan (trọng tâm đề tài)
Với mỗi điểm thay đổi, xét **cửa sổ tin tức quanh nó** (ví dụ [−3, +1] ngày) và đối chiếu:
- **Độ phủ (coverage):** bao nhiêu % điểm thay đổi có tin tức đi kèm.
- **Tỷ lệ khớp hướng:** điểm giá *giảm* có đi kèm tin *tiêu cực* (và ngược lại) bao nhiêu %.
- **Hệ số tương quan** (Pearson / Spearman) giữa `mean_sentiment` và `return` quanh các điểm.
- **Thống kê mô tả + biểu đồ** (không cần mô hình dự báo).

> Đây là phần "đánh giá tương quan" trong tên đề tài — **mô tả & đối chiếu**, trả lời "giá biến động mạnh có đi cùng tin tức cùng chiều không".

### 5.3 Dashboard
- Biểu đồ giá nến + KPI (MA, RSI...) cho từng mã.
- **Đánh dấu điểm thay đổi** trên biểu đồ giá.
- Bảng/timeline tin tức + sentiment; click điểm thay đổi → xem tin quanh ngày đó.
- Bảng tổng hợp tương quan theo mã.
- Công nghệ gợi ý: **Streamlit** (nhanh, Python thuần) hoặc web hiện có (`uiweb`/`realtimeweb`).

---

## 6. Công nghệ sử dụng

| Hạng mục | Công cụ |
|---|---|
| Ngôn ngữ | Python 3.12 |
| Thu thập giá | vnstock |
| Thu thập tin | requests + BeautifulSoup (crawler đã có) |
| Xử lý dữ liệu | pandas, numpy |
| KPI / chỉ số | pandas, ta / pandas-ta |
| Phát hiện điểm thay đổi | ruptures (PELT) |
| Sentiment | transformers (PhoBERT / mô hình sentiment VN) |
| Lưu trữ | Supabase (PostgreSQL) |
| Dashboard | Streamlit (hoặc web sẵn có) |

---

## 7. Phương pháp đánh giá kết quả

- **Hệ thống:** chạy end-to-end tự động; dashboard hiển thị đúng giá/KPI/điểm thay đổi/tin.
- **Tương quan:** báo cáo các chỉ số mục 5.2 (coverage, tỷ lệ khớp hướng, hệ số tương quan) kèm biểu đồ.
- **Sentiment:** đánh giá độ chính xác trên một tập tin tự gán nhãn nhỏ (vài trăm bài) → Accuracy/F1.
- **Trung thực:** nếu tương quan yếu cũng là **kết quả hợp lệ** — quan trọng là phương pháp đo đúng và kết luận thẳng thắn.

---

## 8. Tài liệu tham khảo

**Phát hiện điểm thay đổi (CPD):**
1. Killick, Fearnhead & Eckley (2012). *Optimal Detection of Changepoints With a Linear Computational Cost (PELT)*. JASA. — thuật toán dùng chính.
2. Truong, Oudre & Vayatis (2020). *Selective review of offline change point detection methods*. Signal Processing. — paper của thư viện `ruptures`.
3. Aminikhanghahi & Cook (2017). *A survey of methods for time series change point detection*. KAIS. — tổng quan CPD.

**Tin tức ↔ giá chứng khoán (tương quan):**
4. Tetlock (2007). *Giving Content to Investor Sentiment: The Role of Media in the Stock Market*. Journal of Finance. — nền tảng: sắc thái truyền thông tương quan với biến động giá.
5. Bollen, Mao & Zeng (2011). *Twitter mood predicts the stock market*. Journal of Computational Science. — quan hệ tâm lý đám đông ↔ thị trường.

**NLP tiếng Việt / Sentiment:**
6. Nguyen & Nguyen (2020). *PhoBERT: Pre-trained language models for Vietnamese*. Findings of EMNLP. — mô hình sentiment tiếng Việt.

**Phân tích kỹ thuật / KPI:**
7. Murphy (1999). *Technical Analysis of the Financial Markets*. — chuẩn về các chỉ số kỹ thuật (MA, RSI, MACD...).
8. Wilder (1978). *New Concepts in Technical Trading Systems*. — nguồn gốc RSI.

---

## 9. Các mốc kiểm soát chính

> Giả định tổng thời gian ~8 tuần. Mỗi mốc có sản phẩm bàn giao (deliverable) để GVHD nghiệm thu.

| Mốc | Thời gian | Nội dung | Sản phẩm bàn giao |
|---|---|---|---|
| **Mốc 1** | Tuần 1-2 | Thu thập giá VN30 2022-2026; tính KPI; thiết kế + nạp DB | Bảng `stock_prices` + `technical_indicators`; biểu đồ giá/KPI mẫu |
| **Mốc 2** | Tuần 3-4 | (Tin đã thu thập ✅) Gắn mã + chấm sentiment pos/neg; tổng hợp theo mã/ngày | Bảng `news_sentiment`; báo cáo độ chính xác sentiment trên tập gán nhãn nhỏ |
| **Mốc 3** | Tuần 5 | Phát hiện điểm thay đổi bằng PELT trên giá VN30 | Bảng `change_points`; biểu đồ giá + điểm thay đổi |
| **Mốc 4** | Tuần 6 | Đánh giá tương quan giá ↔ tin (coverage, khớp hướng, hệ số tương quan) | Bảng + biểu đồ tương quan; nhận xét |
| **Mốc 5** | Tuần 7 | Xây dashboard tích hợp (giá+KPI+điểm thay đổi+tin+sentiment) | Dashboard chạy demo được |
| **Mốc 6** | Tuần 8 | Viết báo cáo, hoàn thiện, chuẩn bị bảo vệ | Báo cáo + slide |

> Nếu thiếu thời gian: ưu tiên xong **Mốc 1-4** (lõi dữ liệu + tương quan); dashboard (Mốc 5) có thể làm bản tối giản.

---

## 10. Hiện trạng (đã làm được)

- ✅ **Crawler tin tức** 4 nguồn hoàn chỉnh + **~15.900 bài 2022-2026** đã có ngày đăng đầy đủ.
- ✅ Tài liệu luồng crawler: `stocknewscrawl/CRAWLER_FLOW.md`.
- ⏳ Cần làm tiếp: thu thập giá + KPI (Mốc 1), sentiment (Mốc 2), CPD + tương quan (Mốc 3-4), dashboard (Mốc 5).
