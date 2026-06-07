-- ╔═══════════════════════════════════════════════════════════════════════╗
-- ║  FIX QUYỀN + BẢNG HOSE INDEX — Paste & RUN trong Supabase SQL Editor   ║
-- ║  (1 lần, ~3 giây)                                                       ║
-- ╚═══════════════════════════════════════════════════════════════════════╝

-- ── (A) GRANT anon SELECT trên 6 bảng mới (vì SQL CREATE TABLE không auto) ─
GRANT SELECT ON public.news_sentiment       TO anon;
GRANT SELECT ON public.news_stock_mapping   TO anon;
GRANT SELECT ON public.daily_sentiment      TO anon;
GRANT SELECT ON public.change_points        TO anon;
GRANT SELECT ON public.correlation_summary  TO anon;
GRANT SELECT ON public.correlation_tests    TO anon;

-- ── (B) Bảng HOSE Index daily (VN-Index, foreign flow…) ──────────────────
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
GRANT SELECT ON public.hose_index_daily TO anon;

-- ── Verify ──────────────────────────────────────────────────────────────
SELECT table_name, privilege_type
  FROM information_schema.role_table_grants
 WHERE grantee = 'anon'
   AND table_schema = 'public'
   AND table_name IN (
     'news_sentiment','news_stock_mapping','daily_sentiment',
     'change_points','correlation_summary','correlation_tests','hose_index_daily'
   )
 ORDER BY table_name;
