import React, { useState } from 'react'
import { useConnectionStatus, useSupabaseQuery } from './hooks/useSupabaseQuery'
import { supabase } from './lib/supabase'

// Layout
import Sidebar from './components/layout/Sidebar'
import TopBar from './components/layout/TopBar'

// Overview / Price / KPI
import KPICards from './components/overview/KPICards'
import PriceChart from './components/overview/PriceChart'

// News & Chat
import NewsFeed from './components/news/NewsFeed'
import AIChat from './components/chat/AIChat'

// Change points & correlation (Mốc 3 + 4)
import ChangePointsView from './components/changepoints/ChangePointsView'

export default function App() {
  const [activePage, setActivePage] = useState('overview')
  const { status: connStatus, lastChecked } = useConnectionStatus()

  const lastUpdateStr = lastChecked
    ? lastChecked.toLocaleTimeString('vi-VN', { hour12: false })
    : null

  return (
    <div className="app-layout">
      <Sidebar
        activePage={activePage}
        onNavigate={setActivePage}
        connectionStatus={connStatus}
      />

      <div className="main-area">
        <TopBar
          activePage={activePage}
          connectionStatus={connStatus}
          lastUpdate={lastUpdateStr}
        />

        <div className="main-scroll">
          {activePage === 'overview' && <OverviewPage />}
          {activePage === 'stocks' && <StocksPage />}
          {activePage === 'news' && <NewsPage />}
          {activePage === 'changepoints' && <ChangePointsView />}
          {activePage === 'ai' && <AIPage />}
          {activePage === 'pipeline' && <PipelinePage />}
        </div>
      </div>

      <div className="right-panel">
        <NewsFeed />
        <AIChat />
      </div>
    </div>
  )
}

/* ════════════════════════════════════════════════════════════════
   PAGES — bám đúng 3 nội dung đồ án
   ════════════════════════════════════════════════════════════════ */

// Tổng quan: KPI 5 thẻ + giá 1 mã + bảng giá VN30
function OverviewPage() {
  return (
    <>
      <KPICards />
      <div className="chart-row">
        <PriceChart />
      </div>
      <StockTable />
    </>
  )
}

// Nội dung 1: Giá + KPI
function StocksPage() {
  return (
    <>
      <KPICards />
      <PriceChart />
      <StockTable />
    </>
  )
}

// Nội dung 2: Tin tức + Sentiment
function NewsPage() {
  return (
    <div style={{ maxWidth: 800, margin: '0 auto' }}>
      <NewsFeedFull />
    </div>
  )
}

function AIPage() {
  return (
    <div style={{ maxWidth: 800, margin: '0 auto' }}>
      <AIChatFull />
    </div>
  )
}

function PipelinePage() {
  return <PipelineStatusView />
}

/* ════════════════════════════════════════════════════════════════
   INLINE SUB-COMPONENTS
   ════════════════════════════════════════════════════════════════ */

function StockTable() {
  const { data: prices, loading } = useSupabaseQuery('stock_prices', {
    select: 'symbol, date, open, close, high, low, volume',
    orderBy: 'date', ascending: false, limit: 200, refreshInterval: 60000,
  })

  // Latest per symbol
  const bySymbol = {}
  prices.forEach(p => { if (!bySymbol[p.symbol]) bySymbol[p.symbol] = p })
  const rows = Object.values(bySymbol).sort((a, b) => a.symbol.localeCompare(b.symbol))

  return (
    <div className="card">
      <div className="card-header"><div className="card-title">📋 Bảng giá VN-30</div></div>
      <div className="card-body" style={{ overflowY: 'auto' }}>
        {loading ? (
          <div className="loading-spinner"><div className="spinner" /> Đang tải...</div>
        ) : rows.length === 0 ? (
          <div className="empty-state"><div className="empty-icon">📉</div><span>Chưa có dữ liệu giá</span></div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border-subtle)', color: 'var(--text-muted)', textTransform: 'uppercase', fontSize: 10 }}>
                <th style={{ padding: '8px 10px', textAlign: 'left' }}>Mã</th>
                <th style={{ padding: '8px 10px', textAlign: 'right' }}>Mở</th>
                <th style={{ padding: '8px 10px', textAlign: 'right' }}>Cao</th>
                <th style={{ padding: '8px 10px', textAlign: 'right' }}>Thấp</th>
                <th style={{ padding: '8px 10px', textAlign: 'right' }}>Đóng</th>
                <th style={{ padding: '8px 10px', textAlign: 'right' }}>KL</th>
                <th style={{ padding: '8px 10px', textAlign: 'right' }}>Ngày</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(r => {
                const change = r.open ? ((r.close - r.open) / r.open * 100) : 0
                const changeColor = change > 0 ? 'var(--green)' : change < 0 ? 'var(--red)' : 'var(--text-secondary)'
                return (
                  <tr key={r.symbol} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                    <td style={{ padding: '8px 10px', fontWeight: 700, color: 'var(--accent)' }}>{r.symbol}</td>
                    <td style={{ padding: '8px 10px', textAlign: 'right' }}>{r.open?.toLocaleString()}</td>
                    <td style={{ padding: '8px 10px', textAlign: 'right' }}>{r.high?.toLocaleString()}</td>
                    <td style={{ padding: '8px 10px', textAlign: 'right' }}>{r.low?.toLocaleString()}</td>
                    <td style={{ padding: '8px 10px', textAlign: 'right', fontWeight: 600, color: changeColor }}>
                      {r.close?.toLocaleString()} <span style={{ fontSize: 10 }}>({change >= 0 ? '+' : ''}{change.toFixed(1)}%)</span>
                    </td>
                    <td style={{ padding: '8px 10px', textAlign: 'right', color: 'var(--text-muted)' }}>
                      {r.volume ? `${(r.volume / 1e3).toFixed(0)}K` : '—'}
                    </td>
                    <td style={{ padding: '8px 10px', textAlign: 'right', color: 'var(--text-muted)', fontSize: 11 }}>{r.date}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

const SENT_DISPLAY = {
  positive: { label: 'Tích cực', cls: 'positive' },
  negative: { label: 'Tiêu cực', cls: 'negative' },
  neutral:  { label: 'Trung tính', cls: 'neutral' },
}

function NewsFeedFull() {
  const { data: news, loading } = useSupabaseQuery('news_links', {
    select: 'id, url, title, source, published_at',
    orderBy: 'published_at', ascending: false, limit: 100, realtime: true,
  })

  const [sentMap, setSentMap] = React.useState({})
  const [filter, setFilter] = React.useState('all')   // all | positive | negative | neutral

  React.useEffect(() => {
    if (!news.length) return
    const ids = news.map(n => n.id)
    supabase.from('news_sentiment')
      .select('news_id, score, polarity, label_3cls').in('news_id', ids)
      .then(({ data }) => {
        const m = {}
        ;(data || []).forEach(s => { m[s.news_id] = s })
        setSentMap(m)
      })
  }, [news])

  const filtered = filter === 'all'
    ? news
    : news.filter(n => sentMap[n.id]?.label_3cls === filter)

  const FILTERS = [
    { v: 'all', label: 'Tất cả' },
    { v: 'positive', label: '👍 Tích cực' },
    { v: 'negative', label: '👎 Tiêu cực' },
    { v: 'neutral',  label: '😐 Trung tính' },
  ]

  return (
    <div className="card">
      <div className="card-header">
        <div className="card-title">📰 Tin tức & Sentiment ({filtered.length}/{news.length})</div>
        <div className="news-filter">
          {FILTERS.map(f => (
            <button key={f.v}
              className={`filter-btn${filter === f.v ? ' active' : ''}`}
              onClick={() => setFilter(f.v)}>
              {f.label}
            </button>
          ))}
        </div>
      </div>
      <div className="card-body" style={{ overflowY: 'auto', maxHeight: 700 }}>
        {loading ? (
          <div className="loading-spinner"><div className="spinner" /> Đang tải...</div>
        ) : filtered.length === 0 ? (
          <div className="empty-state"><div className="empty-icon">📭</div><span>Không có tin</span></div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border-subtle)', color: 'var(--text-muted)',
                           textTransform: 'uppercase', fontSize: 10 }}>
                <th style={{ padding: '10px', textAlign: 'left', width: 100 }}>Ngày</th>
                <th style={{ padding: '10px', textAlign: 'left', width: 140 }}>Nguồn</th>
                <th style={{ padding: '10px', textAlign: 'left' }}>Tiêu đề</th>
                <th style={{ padding: '10px', textAlign: 'center', width: 110 }}>Sắc thái</th>
                <th style={{ padding: '10px', textAlign: 'right', width: 90 }}>Score</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map(n => {
                const s = sentMap[n.id]
                const info = s ? SENT_DISPLAY[s.label_3cls] : null
                const sc = s?.score
                return (
                  <tr key={n.id}
                      style={{ borderBottom: '1px solid var(--border-subtle)', cursor: 'pointer' }}
                      onClick={() => n.url && window.open(n.url, '_blank')}>
                    <td style={{ padding: '10px', color: 'var(--text-muted)', fontSize: 11 }}>
                      {n.published_at?.slice(0, 10)}
                    </td>
                    <td style={{ padding: '10px', color: 'var(--text-secondary)' }}>{n.source}</td>
                    <td style={{ padding: '10px' }}>{n.title}</td>
                    <td style={{ padding: '10px', textAlign: 'center' }}>
                      {info ? <span className={`sentiment-badge ${info.cls}`}>{info.label}</span>
                            : <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>—</span>}
                    </td>
                    <td style={{ padding: '10px', textAlign: 'right', fontWeight: 600,
                                 color: sc > 0.2 ? 'var(--green)' : sc < -0.2 ? 'var(--red)' : 'var(--text-secondary)' }}>
                      {sc !== undefined && sc !== null ? (sc > 0 ? '+' : '') + Number(sc).toFixed(3) : '—'}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

function AIChatFull() {
  return (
    <div className="card" style={{ height: 600 }}>
      <div className="card-header"><div className="card-title">🤖 AI Phân tích thị trường</div></div>
      <div className="card-body" style={{ display: 'flex', flexDirection: 'column' }}>
        <AIChat />
      </div>
    </div>
  )
}

/**
 * Pipeline page — hiển thị tiến độ đồng bộ + nút trigger refresh.
 * Đếm số bản ghi mỗi bảng + ngày dữ liệu mới nhất.
 */
function PipelineStatusView() {
  const tables = [
    { name: 'companies', label: 'Công ty', icon: '🏢' },
    { name: 'stock_prices', label: 'Giá OHLCV', icon: '📈' },
    { name: 'technical_indicators', label: 'KPI kỹ thuật', icon: '📊' },
    { name: 'vn30_constituents', label: 'Thành phần VN30', icon: '📜' },
    { name: 'news_links', label: 'Tin tức', icon: '📰' },
    { name: 'news_content', label: 'Nội dung tin', icon: '📄' },
    { name: 'news_stock_mapping', label: 'Gắn mã (Mốc 2)', icon: '🔖' },
    { name: 'news_sentiment', label: 'Sentiment (Mốc 2)', icon: '💬' },
    { name: 'daily_sentiment', label: 'Sentiment ngày (Mốc 4)', icon: '📅' },
    { name: 'change_points', label: 'Điểm thay đổi (Mốc 3)', icon: '🎯' },
    { name: 'correlation_summary', label: 'Tương quan/mã (Mốc 4)', icon: '🔗' },
    { name: 'correlation_tests', label: 'Kiểm định (Mốc 4)', icon: '🧪' },
  ]
  return (
    <div className="card">
      <div className="card-header">
        <div className="card-title">🔧 Pipeline & trạng thái bảng dữ liệu</div>
        <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
          Refresh tự động 30s · Chạy lại pipeline: <code>npm run pipeline</code>
        </span>
      </div>
      <div className="card-body">
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 12 }}>
          {tables.map(t => <TableStat key={t.name} table={t.name} label={t.label} icon={t.icon} />)}
        </div>
        <div style={{ marginTop: 20, padding: 14, background: 'var(--bg-elevated)', borderRadius: 'var(--radius-md)',
                       border: '1px solid var(--border-subtle)', fontSize: 12, color: 'var(--text-secondary)' }}>
          <div style={{ fontWeight: 700, color: 'var(--accent)', marginBottom: 6 }}>📦 Luồng dữ liệu</div>
          <div>1. <b>vnstock</b> → lấy giá mới + thông tin VN30 → <code>stock_prices</code>, <code>vn30_constituents</code></div>
          <div>2. <b>Crawler</b> → lấy tin mới từ 4 báo → <code>news_links</code>, <code>news_content</code></div>
          <div>3. <b>Hybrid PhoBERT + Lexicon</b> → chấm sentiment → <code>news_sentiment</code></div>
          <div>4. <b>Ticker tagger</b> (rule-based) → gắn mã → <code>news_stock_mapping</code></div>
          <div>5. <b>PELT (ruptures)</b> → log-return → <code>change_points</code></div>
          <div>6. <b>Aggregate</b> → mean(score) ngày → <code>daily_sentiment</code></div>
          <div>7. <b>Permutation + Bootstrap</b> → <code>correlation_summary</code>, <code>correlation_tests</code></div>
        </div>
      </div>
    </div>
  )
}

function TableStat({ table, label, icon }) {
  const { data, loading } = useSupabaseQuery(table, {
    select: '*', limit: 1, refreshInterval: 30000,
  })
  // We can't easily get count from useSupabaseQuery; do a separate count query
  const [count, setCount] = React.useState(null)
  const [latestDate, setLatestDate] = React.useState(null)

  React.useEffect(() => {
    supabase.from(table).select('*', { count: 'exact', head: true })
      .then(({ count }) => setCount(count))
    const dateCols = ['date', 'change_point_date', 'published_at', 'created_at']
    Promise.all(dateCols.map(col =>
      supabase.from(table).select(col).order(col, { ascending: false }).limit(1)
        .then(r => r.error ? null : r.data?.[0]?.[col])
    )).then(results => {
      const found = results.find(r => r)
      if (found) setLatestDate(String(found).slice(0, 10))
    })
  }, [table])

  return (
    <div style={{ padding: 12, background: 'var(--bg-elevated)', borderRadius: 'var(--radius-md)',
                  border: '1px solid var(--border-subtle)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
        <span style={{ fontSize: 16 }}>{icon}</span>
        <span style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: 0.5 }}>{table}</span>
      </div>
      <div style={{ fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 22, fontWeight: 700, color: count > 0 ? 'var(--accent)' : 'var(--text-muted)' }}>
        {count === null ? '...' : count.toLocaleString()}
      </div>
      {latestDate && (
        <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 4 }}>Mới nhất: {latestDate}</div>
      )}
    </div>
  )
}
