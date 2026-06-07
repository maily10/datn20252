-- ════════════════════════════════════════════════════════════════════
-- Schema cho VN-30 Risk Monitor (self-host Supabase / Postgres)
-- Chạy trong: Supabase Studio → SQL Editor → New query → Run
-- ════════════════════════════════════════════════════════════════════

create table if not exists companies (
  symbol        text primary key,
  company_name  text not null default ''
);

create table if not exists vn30_constituents (
  id         int primary key,
  symbol     text not null references companies(symbol),
  from_date  date not null,
  to_date    date
);

create table if not exists stock_prices (
  symbol      text not null references companies(symbol),
  date        date not null,
  open        numeric,
  high        numeric,
  low         numeric,
  close       numeric,
  volume      bigint default 0,
  created_at  timestamptz default now(),
  primary key (symbol, date)
);
create index if not exists idx_stock_prices_date on stock_prices(date desc);
create index if not exists idx_stock_prices_symbol_date on stock_prices(symbol, date desc);

create table if not exists dim_time (
  date         date primary key,
  year         int,
  quarter      int,
  month        int,
  day          int,
  day_of_week  int,
  is_weekend   boolean
);

create table if not exists news_links (
  id              bigint primary key,
  url             text not null unique,
  title           text,
  source          text,
  published_at    timestamptz,
  published_date  date,
  status          text default 'published',
  created_at      timestamptz default now()
);
create index if not exists idx_news_links_published on news_links(published_at desc);

create table if not exists news_content (
  news_id     bigint primary key references news_links(id) on delete cascade,
  content     text,
  summary     text,
  image_url   text,
  created_at  timestamptz default now()
);

create table if not exists news_sentiment_results (
  news_id            bigint primary key references news_links(id) on delete cascade,
  predicted_label    int,
  label_text         text,
  confidence_score   numeric,
  sentiment_score    numeric,
  prob_negative      numeric,
  prob_neutral       numeric,
  prob_positive      numeric,
  cap_do_tac_dong    text,
  khung_thoi_gian    text,
  quality            text,
  model_version      text,
  inferred_at        timestamptz default now()
);

create table if not exists news_entities (
  id         bigserial primary key,
  news_id    bigint references news_links(id) on delete cascade,
  entity     text not null,
  type       text,
  sentiment  text
);
create index if not exists idx_news_entities_news on news_entities(news_id);

create table if not exists news_stock_mapping (
  id               bigserial primary key,
  news_id          bigint references news_links(id) on delete cascade,
  symbol           text references companies(symbol),
  relevance        numeric,
  sentiment_score  numeric
);
create index if not exists idx_nsm_news on news_stock_mapping(news_id);
create index if not exists idx_nsm_symbol on news_stock_mapping(symbol);

create table if not exists risk_scores_daily (
  symbol          text references companies(symbol),
  date            date,
  composite_risk  numeric,
  risk_level      text,
  primary key (symbol, date)
);

create table if not exists pipeline_run_logs (
  id                 bigserial primary key,
  run_type           text not null,
  status             text not null,
  source             text,
  started_at         timestamptz default now(),
  finished_at        timestamptz,
  records_processed  bigint default 0,
  records_failed     bigint default 0,
  error_message      text
);

-- ════════════════════════════════════════════════════════════════════
-- Row Level Security — cho phép anon đọc tất cả bảng dashboard cần
-- ════════════════════════════════════════════════════════════════════
do $$
declare t text;
begin
  for t in
    select unnest(array[
      'companies','vn30_constituents','stock_prices','dim_time',
      'news_links','news_content','news_sentiment_results',
      'news_entities','news_stock_mapping','risk_scores_daily',
      'pipeline_run_logs'
    ])
  loop
    execute format('alter table %I enable row level security', t);
    execute format(
      'drop policy if exists "anon read" on %I; '
      'create policy "anon read" on %I for select to anon using (true);',
      t, t
    );
  end loop;
end$$;

-- ════════════════════════════════════════════════════════════════════
-- Bật Realtime cho 2 bảng push lên UI
-- ════════════════════════════════════════════════════════════════════
alter publication supabase_realtime add table news_links;
alter publication supabase_realtime add table stock_prices;
