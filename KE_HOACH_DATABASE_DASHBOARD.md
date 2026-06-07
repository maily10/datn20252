# Kế hoạch Database + Dashboard

> Phục vụ **Mốc 5** đồ án — tích hợp kết quả các mốc trước (giá+KPI, sentiment, CPD, tương quan)
> lên Supabase và dựng dashboard. Tài liệu chi tiết kèm **SQL `CREATE TABLE` ready-to-paste**
> cho Supabase SQL Editor. Sau khi bạn tạo bảng, tôi chỉ việc upload dữ liệu.

---

## 1. Tổng quan

### 1.1 Bảng đã có sẵn (giữ nguyên)

| Bảng | Vai trò | Đã có dữ liệu? |
|---|---|---|
| `companies` | Master mã chứng khoán | ✅ |
| `dim_time` | Bảng chiều thời gian (date) | ✅ |
| `dim_time_hourly` | Bảng chiều thời gian giờ — *không dùng cho thesis* | ✅ (bỏ qua) |
| `vn30_constituents` | Lịch sử thành phần VN30 | ✅ |
| `stock_prices` | OHLCV ngày | ✅ |
| `technical_indicators` | KPI kỹ thuật (MA, RSI, MACD, BB, ATR) | ✅ (cần mở rộng — §1.3) |
| `news_links` | Master tin tức (url, title, source, published_at) | ✅ |
| `news_content` | Nội dung tin (content + summary) | ✅ |
| `news_entities` | Entity sentiment cũ — *không dùng, có thể bỏ* | (để lại) |

### 1.2 Bảng cần TẠO MỚI (5 bảng)

| Bảng | Nguồn dữ liệu | Số dòng | Cho mốc |
|---|---|---|---|
| `news_stock_mapping` | `output/news_stock_mapping.csv` | ~44.331 | 2 (gắn mã) |
| `news_sentiment` | `test/news_sentiment/output/news_sentiment_hybrid.csv` | ~15.791 | 2 (sentiment) |
| `daily_sentiment` | `analysis/output/daily_sentiment.csv` | ~20.882 | 4 (aggregate) |
| `change_points` | `analysis/output/change_points.csv` | 455 | 3 (CPD) |
| `correlation_summary` | `analysis/output/correlation_summary.csv` | 30 | 4 |
| `correlation_tests` | `analysis/output/correlation_tests.json` | 1 | 4 |

### 1.3 Cần ALTER `technical_indicators` (thêm 7 cột)

KPI tôi đã tính (file `vnstockprice/technical_indicators.csv`) có thêm `daily_return, log_return,
volatility_20, drawdown, bb_pctb, volume_change, obv` so với schema hiện tại. Để dashboard
hiển thị đủ → thêm cột (chỉ ADD, không sửa cột cũ).

---

## 2. SQL ready-to-paste vào Supabase SQL Editor

> Chạy 1 lần. **Idempotent** (có `IF NOT EXISTS`) — chạy lại không lỗi nếu đã tạo.

```sql
-- ╔═══════════════════════════════════════════════════════════════════════════╗
-- ║  KẾ HOẠCH BẢNG MỚI CHO ĐỒ ÁN — Mốc 2/3/4                                   ║
-- ╚═══════════════════════════════════════════════════════════════════════════╝

BEGIN;

-- ── (A) Mở rộng technical_indicators cho đủ KPI đã tính ────────────────────
ALTER TABLE public.technical_indicators
  ADD COLUMN IF NOT EXISTS daily_return    NUMERIC,
  ADD COLUMN IF NOT EXISTS log_return      NUMERIC,
  ADD COLUMN IF NOT EXISTS volatility_20   NUMERIC,
  ADD COLUMN IF NOT EXISTS drawdown        NUMERIC,
  ADD COLUMN IF NOT EXISTS bb_pctb         NUMERIC,
  ADD COLUMN IF NOT EXISTS volume_change   NUMERIC,
  ADD COLUMN IF NOT EXISTS obv             NUMERIC;

-- ── (B) news_stock_mapping — gắn mã (many-to-many) ─────────────────────────
CREATE TABLE IF NOT EXISTS public.news_stock_mapping (
    id          BIGSERIAL PRIMARY KEY,
    news_id     INTEGER NOT NULL REFERENCES public.news_links(id) ON DELETE CASCADE,
    symbol      TEXT NOT NULL,        -- mã VN30 hoặc 'MARKET'
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_news_symbol UNIQUE (news_id, symbol)
);
CREATE INDEX IF NOT EXISTS idx_nsm_news    ON public.news_stock_mapping(news_id);
CREATE INDEX IF NOT EXISTS idx_nsm_symbol  ON public.news_stock_mapping(symbol);
COMMENT ON TABLE public.news_stock_mapping IS
    'Mốc 2 — gắn mã. Một tin có thể về nhiều mã, hoặc về MARKET.';

-- ── (C) news_sentiment — sentiment đầu ra của Hướng A hybrid ───────────────
CREATE TABLE IF NOT EXISTS public.news_sentiment (
    news_id        INTEGER PRIMARY KEY REFERENCES public.news_links(id) ON DELETE CASCADE,
    score          NUMERIC NOT NULL,                 -- s(t) ∈ [-1, 1] (output method)
    polarity       TEXT    NOT NULL CHECK (polarity IN ('positive','negative')),
    label_3cls     TEXT    NOT NULL CHECK (label_3cls IN ('positive','neutral','negative')),
    model_score    NUMERIC,                          -- P(pos) − P(neg) thuần model
    lex_net        INTEGER,                          -- pos_hits − neg_hits từ từ điển
    prob_negative  NUMERIC,
    prob_neutral   NUMERIC,
    prob_positive  NUMERIC,
    method         TEXT    DEFAULT 'hybrid_phobert_lex_v1',
    created_at     TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ns_polarity ON public.news_sentiment(polarity);
COMMENT ON TABLE public.news_sentiment IS
    'Mốc 2 — sentiment mỗi tin. score liên tục là output chính; polarity/label_3cls là view.';

-- ── (D) daily_sentiment — aggregate theo (mã, ngày) cho Mốc 4 ──────────────
CREATE TABLE IF NOT EXISTS public.daily_sentiment (
    symbol      TEXT NOT NULL,           -- VN30 ticker hoặc 'MARKET'
    date        DATE NOT NULL,
    mean_score  NUMERIC NOT NULL,        -- mean(news_sentiment.score)
    n_news      INTEGER NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (symbol, date)
);
CREATE INDEX IF NOT EXISTS idx_ds_date    ON public.daily_sentiment(date);
CREATE INDEX IF NOT EXISTS idx_ds_symbol  ON public.daily_sentiment(symbol);
COMMENT ON TABLE public.daily_sentiment IS
    'Mốc 4 — tín hiệu sentiment hàng ngày, dùng cho phân tích tương quan và dashboard.';

-- ── (E) change_points — điểm thay đổi giá Mốc 3 ────────────────────────────
CREATE TABLE IF NOT EXISTS public.change_points (
    id                  BIGSERIAL PRIMARY KEY,
    symbol              TEXT     NOT NULL REFERENCES public.companies(symbol),
    change_point_date   DATE     NOT NULL REFERENCES public.dim_time(date),
    direction           SMALLINT NOT NULL CHECK (direction IN (1, -1)),
    magnitude           NUMERIC  NOT NULL,                 -- |Δ mean log-return|
    method              TEXT     DEFAULT 'pelt_l2_c05',    -- PELT model=l2, pen=0.5*log(n)
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_change_point UNIQUE (symbol, change_point_date)
);
CREATE INDEX IF NOT EXISTS idx_cp_symbol ON public.change_points(symbol);
CREATE INDEX IF NOT EXISTS idx_cp_date   ON public.change_points(change_point_date);
COMMENT ON TABLE public.change_points IS
    'Mốc 3 — PELT trên log-return chuẩn hoá. direction=+1 tăng regime, -1 giảm.';

-- ── (F) correlation_summary — per-symbol results Mốc 4 ─────────────────────
CREATE TABLE IF NOT EXISTS public.correlation_summary (
    symbol         TEXT    PRIMARY KEY REFERENCES public.companies(symbol),
    n_cp           INTEGER NOT NULL,
    n_covered      INTEGER NOT NULL,
    coverage       NUMERIC NOT NULL,
    n_with_signal  INTEGER NOT NULL,
    n_match        INTEGER NOT NULL,
    match_rate     NUMERIC,                       -- NULL nếu n_with_signal = 0
    window_before  INTEGER DEFAULT 3,
    window_after   INTEGER DEFAULT 1,
    created_at     TIMESTAMPTZ DEFAULT NOW()
);
COMMENT ON TABLE public.correlation_summary IS
    'Mốc 4 — coverage & match rate per mã. Aggregate trong correlation_tests.';

-- ── (G) correlation_tests — aggregate VN30 + kiểm định ─────────────────────
CREATE TABLE IF NOT EXISTS public.correlation_tests (
    id                  SERIAL  PRIMARY KEY,
    scope               TEXT    NOT NULL DEFAULT 'aggregate_vn30',
    n_change_points     INTEGER NOT NULL,
    window_before       INTEGER NOT NULL,
    window_after        INTEGER NOT NULL,
    coverage            NUMERIC NOT NULL,
    match_rate          NUMERIC NOT NULL,
    permutation_n       INTEGER NOT NULL,
    null_mean           NUMERIC NOT NULL,
    null_std            NUMERIC NOT NULL,
    p_value_one_sided   NUMERIC NOT NULL,
    p_value_two_sided   NUMERIC NOT NULL,
    bootstrap_n         INTEGER NOT NULL,
    bootstrap_ci_low    NUMERIC NOT NULL,
    bootstrap_ci_high   NUMERIC NOT NULL,
    reject_h0_at_005    BOOLEAN NOT NULL,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);
COMMENT ON TABLE public.correlation_tests IS
    'Mốc 4 — permutation p-value + bootstrap CI cho match rate ở mức aggregate.';

COMMIT;
```

### Sau khi paste & Run

Kiểm tra nhanh bằng:
```sql
SELECT table_name FROM information_schema.tables
 WHERE table_schema = 'public' ORDER BY table_name;
```
Phải thấy đủ 9 bảng + 5 bảng mới (`news_stock_mapping, news_sentiment, daily_sentiment,
change_points, correlation_summary, correlation_tests`).

---

## 3. Quan hệ giữa các bảng (ERD text)

```
                ┌───────────────────┐
                │   companies       │ (symbol PK)
                └─────────┬─────────┘
                          │
        ┌─────────────────┼─────────────────────┬──────────────────┐
        ▼                 ▼                     ▼                  ▼
  stock_prices    technical_indicators    change_points    correlation_summary
  (symbol,date)   (symbol,date,timeframe) (symbol,date)    (symbol)
        ▲                 ▲                     ▲
        │                 │                     │
        └───────┬─────────┴─────────────────────┘
                │
            dim_time (date)
                
  news_links (id PK) ──┬── news_content (news_id FK)
                       │
                       ├── news_stock_mapping (news_id, symbol)──► companies.symbol  / 'MARKET'
                       │
                       └── news_sentiment (news_id FK, score)
                                  │
                                  └──aggregate──► daily_sentiment (symbol, date)
                                                       │
                                                       └──join với change_points──► correlation_*
```

---

## 4. Data pipeline (sau khi bảng đã tạo)

Tôi sẽ chạy **một script upload** (`upload_to_supabase.py`) đọc các CSV/JSON cục bộ + insert
qua `supabase-py` service_role. Thứ tự (do FK):

| # | Bảng đích | Nguồn cục bộ | Kích thước | Ghi chú |
|---|---|---|---|---|
| 1 | `technical_indicators` (UPDATE/UPSERT) | `vnstockprice/technical_indicators.csv` | 31.710 | Chỉ thêm 7 cột mới; PK `(symbol, date, timeframe)` — set `timeframe='1D'` |
| 2 | `news_stock_mapping` | `test/news_sentiment/output/news_stock_mapping.csv` | 44.331 | INSERT batched |
| 3 | `news_sentiment` | `test/news_sentiment/output/news_sentiment_hybrid.csv` | 15.791 | dedup theo `news_id` (bỏ 441 dòng lặp) |
| 4 | `daily_sentiment` | `analysis/output/daily_sentiment.csv` | 20.882 | UPSERT theo `(symbol, date)` |
| 5 | `change_points` | `analysis/output/change_points.csv` | 455 | UPSERT theo `(symbol, change_point_date)` |
| 6 | `correlation_summary` | `analysis/output/correlation_summary.csv` | 30 | |
| 7 | `correlation_tests` | `analysis/output/correlation_tests.json` | 1 | scope='aggregate_vn30' |

Batch size: 500 dòng/request (Supabase API safe). Ước tổng thời gian upload: **2-5 phút**.

---

## 5. Dashboard — thiết kế

### 5.1 Stack đề xuất

**Khuyến nghị: Streamlit** (Python thuần, ~1-2 ngày dựng):
- Connect Supabase đơn giản qua `supabase-py`.
- `streamlit-plotly` / `plotly` cho biểu đồ tương tác.
- Triển khai local: `streamlit run dashboard.py`.

Hoặc tận dụng [`realtimeweb/`](realtimeweb/) (React + Vite + Supabase) — đã có sẵn skeleton kết nối Supabase, đẹp hơn nhưng tốn thời gian hơn.

### 5.2 Trang & widget chi tiết

#### 🏠 Trang 1 — Overview

| Widget | Dữ liệu (query) |
|---|---|
| KPI card: # mã VN30, # tin, # CP, accuracy sentiment | `SELECT count FROM companies`, `news_links`, `change_points`, hardcode 86.8% |
| Biểu đồ VN-Index 2022→nay | (cần bổ sung mã `VNINDEX` vào stock_prices) hoặc dùng FPT/VCB làm proxy |
| Top 5 CP gần đây | `SELECT * FROM change_points ORDER BY change_point_date DESC LIMIT 5` |
| Tin nổi bật 7 ngày qua | `news_links JOIN news_sentiment ORDER BY ABS(score) DESC LIMIT 10` |

#### 📈 Trang 2 — Per-stock detail (cốt lõi)

User chọn mã từ dropdown 30 VN30. Hiển thị:

| Widget | Dữ liệu |
|---|---|
| Biểu đồ giá nến + overlay MA20/MA50/BB | `SELECT * FROM stock_prices JOIN technical_indicators USING(symbol,date) WHERE symbol=:s` |
| **Đánh dấu CP** trên biểu đồ giá (xanh tăng / đỏ giảm) | `SELECT * FROM change_points WHERE symbol=:s` |
| **Đường daily_sentiment MA20** dưới giá | `SELECT date, mean_score FROM daily_sentiment WHERE symbol IN (:s, 'MARKET')` |
| Bảng tin tức mới nhất về mã đó | `news_stock_mapping JOIN news_links JOIN news_sentiment WHERE symbol=:s ORDER BY published_at DESC LIMIT 30` |
| KPI snapshot (RSI, MACD, drawdown hiện tại) | `technical_indicators` dòng cuối của mã |

#### 🔗 Trang 3 — Phân tích tương quan (key chứng minh)

| Widget | Dữ liệu |
|---|---|
| KPI card: Coverage, Match rate, p-value, 95% CI | `SELECT * FROM correlation_tests` |
| **Bar chart match rate per mã** | `SELECT symbol, match_rate FROM correlation_summary ORDER BY match_rate DESC` |
| Permutation null histogram (ảnh PNG) | `analysis/output/plots/permutation_null_histogram.png` |
| Bảng chi tiết per mã | `correlation_summary` full table |
| Click vào mã → list CP + tin trong cửa sổ | join `change_points` + `news_stock_mapping` + `news_links` + `news_sentiment` cửa sổ `[date-3, date+1]` |

#### 📰 Trang 4 — Browser tin tức (filter)

| Filter | Query |
|---|---|
| Theo mã | `news_stock_mapping.symbol = :s` |
| Theo nguồn báo | `news_links.source IN (...)` |
| Theo polarity | `news_sentiment.polarity = :p` |
| Theo khoảng ngày | `published_at BETWEEN ... AND ...` |
| Theo score range | `score BETWEEN :lo AND :hi` |

### 5.3 Queries mẫu (tham khảo dựng dashboard)

**Giá + KPI + CP cho 1 mã:**
```sql
SELECT p.date, p.open, p.high, p.low, p.close, p.volume,
       t.ma_20, t.ma_50, t.rsi_14, t.bb_upper, t.bb_lower,
       c.direction AS cp_direction
  FROM stock_prices p
  LEFT JOIN technical_indicators t USING (symbol, date)
  LEFT JOIN change_points c ON c.symbol=p.symbol AND c.change_point_date=p.date
 WHERE p.symbol = 'VCB' AND p.date >= '2022-01-01'
 ORDER BY p.date;
```

**Tin quanh một CP cụ thể:**
```sql
WITH cp AS (
  SELECT symbol, change_point_date AS d FROM change_points WHERE id = :cp_id
)
SELECT l.title, l.source, l.published_at, s.score, s.polarity
  FROM cp
  JOIN news_stock_mapping m ON m.symbol IN (cp.symbol, 'MARKET')
  JOIN news_links l         ON l.id = m.news_id
  JOIN news_sentiment s     ON s.news_id = m.news_id
 WHERE l.published_at::date BETWEEN cp.d - INTERVAL '3 days' AND cp.d + INTERVAL '1 day'
 ORDER BY l.published_at;
```

**Daily sentiment + return cho biểu đồ overlay:**
```sql
SELECT d.date, d.mean_score, d.n_news, t.daily_return, t.close
  FROM daily_sentiment d
  LEFT JOIN technical_indicators t ON t.symbol = d.symbol AND t.date = d.date
 WHERE d.symbol = 'HPG' AND d.date BETWEEN '2022-01-01' AND '2026-04-30'
 ORDER BY d.date;
```

---

## 6. Tiến độ + Việc tiếp theo

### Hôm nay (sau khi bạn paste SQL)

- [ ] Bạn paste SQL §2 vào Supabase SQL Editor → Run.
- [ ] Tôi viết `upload_to_supabase.py` đọc CSV + insert qua service_role.
- [ ] Tôi chạy upload, verify count mỗi bảng.

### Ngày sau (Mốc 5)

- [ ] Dựng skeleton Streamlit: 4 trang nêu trên.
- [ ] Kết nối Supabase từ Streamlit, build query helpers.
- [ ] Demo end-to-end: chọn mã → giá + CP + tin + sentiment.

---

## 7. Rủi ro & cách giảm

| Rủi ro | Mitigation |
|---|---|
| FK constraint fail khi insert (news_id không có trong news_links) | Tôi lọc trước khi upload, log những row bị skip |
| Bảng `news_entities` cũ có thể nhầm với `news_sentiment` mới | Không động `news_entities`, để lại — có thể DROP sau nếu chắc không dùng |
| `technical_indicators.timeframe` chưa có giá trị | Set `'1D'` cho mọi dòng khi upsert |
| Dữ liệu trùng giữa các lần upload | UPSERT (PK violation handler) thay vì INSERT thuần |
| Service_role key lộ ra client (dashboard) | Streamlit chạy server-side, key trong `.streamlit/secrets.toml` — KHÔNG đẩy lên Git |

---

## 8. Phụ lục — DROP bảng nếu cần làm lại

```sql
-- ⚠️ CHỈ chạy nếu muốn xoá hết bảng mới và làm lại
DROP TABLE IF EXISTS public.correlation_tests   CASCADE;
DROP TABLE IF EXISTS public.correlation_summary CASCADE;
DROP TABLE IF EXISTS public.change_points       CASCADE;
DROP TABLE IF EXISTS public.daily_sentiment     CASCADE;
DROP TABLE IF EXISTS public.news_sentiment      CASCADE;
DROP TABLE IF EXISTS public.news_stock_mapping  CASCADE;
-- KHÔNG DROP technical_indicators — chỉ thêm cột.
-- Nếu muốn rollback cột thêm:
ALTER TABLE public.technical_indicators
  DROP COLUMN IF EXISTS daily_return,
  DROP COLUMN IF EXISTS log_return,
  DROP COLUMN IF EXISTS volatility_20,
  DROP COLUMN IF EXISTS drawdown,
  DROP COLUMN IF EXISTS bb_pctb,
  DROP COLUMN IF EXISTS volume_change,
  DROP COLUMN IF EXISTS obv;
```
