# VN-30 Dashboard — Realtime (đồ án tốt nghiệp)

Dashboard giám sát thị trường chứng khoán VN-30 theo đúng **3 nội dung đồ án**:

1. **Thu thập giá + tính KPI** — vnstock OHLCV, technical indicators
2. **Thu thập tin tức + sentiment** — crawler 4 báo + Hybrid PhoBERT+Lexicon
3. **Dashboard + phát hiện điểm thay đổi** — PELT trên log-return, đánh giá tương quan

Phần **AI Q&A** giữ nguyên (Gemini 2.0 Flash đọc dữ liệu thật từ DB).

---

## 🚀 Quick start

```powershell
cd "e:\20252\datn\crawler\realtimeweb copy"

# Cách 1 — Bật tất cả (pipeline auto cập nhật giá + dev server)
npm start

# Cách 2 — Chỉ dev server (dữ liệu hiện có trong Supabase)
npm run dev

# Cách 3 — Build production
npm run build
```

Mở trình duyệt: **http://localhost:5173**

---

## 📂 Cấu trúc trang

| Trang | Vai trò | Nội dung đồ án |
|---|---|---|
| 📊 **Tổng quan** | 5 KPI card + giá 1 mã + bảng VN30 | Tổng hợp |
| 📈 **Giá & KPI** | KPI + biểu đồ giá nến + bảng giá | Nội dung 1 |
| 📰 **Tin tức & Sentiment** | Tất cả tin tức + sentiment score | Nội dung 2 |
| 🎯 **Điểm thay đổi** | CP per mã + biểu đồ giá+sentiment+CP + bảng match rate | Nội dung 3 + Mốc 4 |
| 🤖 **AI Phân tích** | Gemini chat với context từ DB | (giữ nguyên) |
| 🔧 **Pipeline** | Đếm rows + ngày mới nhất mỗi bảng + sơ đồ luồng | Monitoring |

Panel phải: **NewsFeed** (realtime) + **AIChat** luôn hiện.

---

## 🔌 Kết nối Supabase

`.env` (đã có sẵn):
```
VITE_SUPABASE_URL=https://ojbafsimgwzoemzsqdbe.supabase.co
VITE_SUPABASE_ANON_KEY=...
VITE_GEMINI_API_KEY=...
```

12 bảng đã có dữ liệu (tính đến 2026-05-29):

| Bảng | Rows | Vai trò |
|---|---|---|
| `companies` | 1.705 | Master mã |
| `stock_prices` | 33.218 | OHLCV |
| `technical_indicators` | 31.710 | KPI kỹ thuật |
| `vn30_constituents` | 50 | Lịch sử VN30 |
| `news_links` | 15.791 | Tin tức |
| `news_content` | 15.791 | Nội dung tin |
| `news_stock_mapping` | 43.380 | Gắn mã (Mốc 2) |
| `news_sentiment` | 15.791 | Sentiment Hybrid (Mốc 2) |
| `daily_sentiment` | 20.882 | Aggregate ngày (Mốc 4) |
| `change_points` | 455 | PELT CPs (Mốc 3) |
| `correlation_summary` | 30 | Per-symbol tương quan |
| `correlation_tests` | 1 | Kiểm định aggregate |

---

## 🔁 Pipeline cập nhật dữ liệu

### Tự động khi `npm start`
`pipeline/refresh.py` chạy nền:
- Lấy danh sách VN30 hiện hành (vnstock Listing)
- Lấy giá OHLCV mới từ ngày cuối có trong DB → hôm nay (incremental)
- Tính KPI (MA, RSI, MACD, BB, drawdown, OBV, volatility, log-return)
- UPSERT lên Supabase

### Thủ công khi muốn refresh toàn bộ
```powershell
# Lấy giá mới
npm run pipeline

# Upload lại toàn bộ output đồ án (CSVs ở folder cha)
npm run upload

# Hoặc chạy các bước riêng (chậm — chỉ khi cần):
python ..\stocknewscrawl\main.py             # crawl tin mới
python ..\test\news_sentiment\run_sentiment.py --hybrid  # ~30-60'
python ..\analysis\detect_change_points.py   # ~5s
python ..\analysis\evaluate_correlation.py   # ~30s
npm run upload                                # sync lên Supabase
```

---

## 🧠 AI Chat (Gemini)

Đặt câu hỏi như:
- *"Thị trường hôm nay thế nào?"*
- *"FPT có điểm thay đổi nào đáng chú ý?"*
- *"Sentiment ↔ giá có liên hệ thật không?"*

Context AI tự kéo từ Supabase: 10 tin mới + tổng hợp sentiment + 15 CP gần nhất + kiểm định tương quan + giá cổ phiếu (10 dòng mới nhất theo mã được hỏi).

**Cấu hình**: không gợi ý mua/bán (không phải mục tiêu đồ án). Không tuyên bố nhân quả — chỉ "liên hệ thống kê".

---

## 🏗 Cấu trúc thư mục

```
realtimeweb copy/
├── src/
│   ├── components/
│   │   ├── layout/       # Sidebar (6 nav items), TopBar
│   │   ├── overview/     # KPICards, PriceChart
│   │   ├── news/         # NewsFeed (panel phải)
│   │   ├── changepoints/ # ChangePointsView (Mốc 3 + 4) ★ MỚI
│   │   └── chat/         # AIChat (giữ nguyên)
│   ├── hooks/            # useSupabaseQuery, useConnectionStatus
│   ├── lib/              # supabase, gemini
│   ├── styles/           # globals.css (design tokens — KHÔNG đổi)
│   ├── App.jsx           # Routing 6 trang
│   └── main.jsx
├── pipeline/
│   ├── upload_initial.py # Upload 1 lần toàn bộ CSV → Supabase
│   └── refresh.py        # Auto chạy khi npm start, lấy giá mới
├── start.js              # Bật pipeline + Vite concurrent
├── package.json          # npm scripts: dev, build, preview, start, pipeline, upload
└── .env                  # Supabase URL + anon key + Gemini key
```

---

## 🎨 Design system (giữ nguyên)

Tokens trong `src/styles/globals.css`:
- Background: `#04090f` (deep) → `#0e1e33` (surface) → `#132847` (elevated)
- Accent: `#00b8ff` (cyan)
- Semantic: green `#00e68a`, red `#ff5757`, yellow `#ffbe2e`
- Layout: 3 cột grid `230px | 1fr | 360px`

**Không sửa CSS** — chỉ thay component content.

---

## ✅ Đã thay đổi so với bản trước

- ✅ Bỏ trang "Cảnh báo rủi ro" (RiskHeatmap, RiskSignals đã xoá)
- ✅ Thêm trang "Điểm thay đổi" (Mốc 3 + 4)
- ✅ KPICards: đổi từ risk_scores → CP count + match rate
- ✅ NewsFeed: chuyển từ `news_sentiment_results` (cũ) → `news_sentiment` (Hybrid PhoBERT)
- ✅ AIChat context: cập nhật để đọc CP + correlation_tests
- ✅ Pipeline tự động: `npm start` → fetch giá mới + KPI mới
- ✅ Upload toàn bộ 12 bảng từ output đồ án → Supabase
- ✅ Giữ nguyên: layout, design tokens, AIChat (Gemini integration)
