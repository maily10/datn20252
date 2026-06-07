-- ════════════════════════════════════════════════════════════════════
-- Cleanup script: drop tables/indexes/functions không cần thiết
-- Chỉ giữ lại: companies, vn30_constituents, stock_prices,
--              dim_time, dim_time_hourly
-- Chạy trong: Supabase Studio → SQL Editor → New query → Run
-- ════════════════════════════════════════════════════════════════════

begin;

-- ── 1. Gỡ các bảng cũ khỏi publication realtime (nếu có) ─────────────
do $$
declare t text;
begin
  for t in
    select unnest(array[
      'news_links','news_content','news_entities','news_stock_mapping',
      'news_sentiment_results','market_sentiment_hourly',
      'model_performance_log','pipeline_run_logs',
      'realized_volatility','risk_scores_daily',
      'technical_indicators','volatility_predictions'
    ])
  loop
    begin
      execute format('alter publication supabase_realtime drop table %I', t);
    exception when others then
      -- bảng không nằm trong publication thì bỏ qua
      null;
    end;
  end loop;
end$$;

-- ── 2. Drop các bảng không cần thiết (CASCADE để xóa luôn FK + index) ─
drop table if exists news_stock_mapping        cascade;
drop table if exists news_entities             cascade;
drop table if exists news_sentiment_results    cascade;
drop table if exists news_content              cascade;
drop table if exists news_links                cascade;

drop table if exists market_sentiment_hourly   cascade;
drop table if exists model_performance_log     cascade;
drop table if exists pipeline_run_logs         cascade;
drop table if exists realized_volatility       cascade;
drop table if exists risk_scores_daily         cascade;
drop table if exists technical_indicators      cascade;
drop table if exists volatility_predictions    cascade;

-- ── 3. Drop tất cả function/procedure do user định nghĩa trong schema public ─
do $$
declare
  r record;
begin
  for r in
    select n.nspname            as schema_name,
           p.proname             as func_name,
           pg_get_function_identity_arguments(p.oid) as args,
           p.prokind             as kind
    from pg_proc p
    join pg_namespace n on n.oid = p.pronamespace
    where n.nspname = 'public'
  loop
    if r.kind = 'p' then
      execute format('drop procedure if exists %I.%I(%s) cascade',
                     r.schema_name, r.func_name, r.args);
    else
      execute format('drop function if exists %I.%I(%s) cascade',
                     r.schema_name, r.func_name, r.args);
    end if;
  end loop;
end$$;

-- ── 4. Drop các index "mồ côi" còn sót (nếu có) trong schema public ──
do $$
declare
  r record;
begin
  for r in
    select schemaname, indexname, tablename
    from pg_indexes
    where schemaname = 'public'
      and tablename not in (
        'companies','vn30_constituents','stock_prices',
        'dim_time','dim_time_hourly'
      )
  loop
    execute format('drop index if exists %I.%I cascade',
                   r.schemaname, r.indexname);
  end loop;
end$$;

commit;

-- ── 5. Kiểm tra kết quả ──────────────────────────────────────────────
select tablename
from pg_tables
where schemaname = 'public'
order by tablename;
