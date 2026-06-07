-- ╔═══════════════════════════════════════════════════════════════════════╗
-- ║  Bảng lưu HOSE Index daily (VN-Index, foreign flow, total volume…)    ║
-- ║  Nguồn: API /Market/GetHoseIndex                                       ║
-- ║                                                                          ║
-- ║  PASTE & RUN trong Supabase Dashboard → SQL Editor (1 lần, ~2 giây)     ║
-- ╚═══════════════════════════════════════════════════════════════════════╝

CREATE TABLE IF NOT EXISTS public.hose_index_daily (
    com_group_code            TEXT      NOT NULL DEFAULT 'VNINDEX',
    trading_date              DATE      NOT NULL,

    index_value               NUMERIC,
    index_change              NUMERIC,
    percent_index_change      NUMERIC,
    reference_index           NUMERIC,

    open_index                NUMERIC,
    close_index               NUMERIC,
    highest_index             NUMERIC,
    lowest_index              NUMERIC,

    total_match_volume        BIGINT,
    total_match_value         BIGINT,
    total_deal_volume         BIGINT,
    total_deal_value          BIGINT,
    total_volume              BIGINT,
    total_value               BIGINT,

    total_stock_up_price      INTEGER,
    total_stock_down_price    INTEGER,
    total_stock_no_change     INTEGER,

    foreign_buy_value_total   BIGINT,
    foreign_buy_volume_total  BIGINT,
    foreign_sell_value_total  BIGINT,
    foreign_sell_volume_total BIGINT,
    foreign_net_value         BIGINT GENERATED ALWAYS AS
        (COALESCE(foreign_buy_value_total, 0) - COALESCE(foreign_sell_value_total, 0)) STORED,

    fetched_at                TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (com_group_code, trading_date)
);

CREATE INDEX IF NOT EXISTS idx_hose_date ON public.hose_index_daily(trading_date);
COMMENT ON TABLE public.hose_index_daily IS
    'VN-Index daily — fetched từ /Market/GetHoseIndex. Dùng cho dashboard overview.';

-- Cho phép anon đọc
GRANT SELECT ON public.hose_index_daily TO anon;

-- Verify
SELECT 'hose_index_daily ready' AS status,
       count(*) AS rows
  FROM public.hose_index_daily;
