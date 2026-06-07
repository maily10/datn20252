import React, { useState, useEffect } from 'react'
import {
  Chart as ChartJS, CategoryScale, LinearScale,
  PointElement, LineElement, Tooltip, Legend, Filler,
} from 'chart.js'
import { Line } from 'react-chartjs-2'
import { supabase } from '../../lib/supabase'
import { useSupabaseQuery } from '../../hooks/useSupabaseQuery'

ChartJS.register(
  CategoryScale, LinearScale, PointElement,
  LineElement, Tooltip, Legend, Filler,
)

/**
 * Plugin Chart.js vẽ vạch dọc ở mỗi change point.
 * Đỏ = direction -1 (giảm), Xanh = direction +1 (tăng).
 */
const cpLinesPlugin = {
  id: 'cpLines',
  afterDatasetsDraw(chart, _args, options) {
    const cps = options?.cps || []
    if (!cps.length) return
    const { ctx, chartArea, scales } = chart
    if (!scales.x) return
    cps.forEach(cp => {
      const idx = chart.data.labels.indexOf(cp.date)
      if (idx < 0) return
      const x = scales.x.getPixelForValue(idx)
      if (x < chartArea.left || x > chartArea.right) return
      ctx.save()
      ctx.beginPath()
      ctx.moveTo(x, chartArea.top)
      ctx.lineTo(x, chartArea.bottom)
      ctx.strokeStyle = cp.direction === 1
        ? 'rgba(0,230,138,0.6)'      // xanh tăng
        : 'rgba(255,87,87,0.75)'      // đỏ giảm
      ctx.lineWidth = 1.4
      ctx.setLineDash([])
      ctx.stroke()
      ctx.restore()
    })
  },
}
ChartJS.register(cpLinesPlugin)

const TIME_RANGES = [
  { label: '30D', days: 30 },
  { label: '90D', days: 90 },
  { label: '6M',  days: 180 },
  { label: '1Y',  days: 365 },
  { label: 'Tất cả', days: 9999 },
]

/**
 * Trang Mốc 3 + 4 — drill-down per VN30 company.
 *
 * Layout (cập nhật theo mã được chọn):
 *   1. KPI cards (rsi, macd, atr, bb_bw, volatility, log_return, drawdown, |CP|)
 *   2. Biểu đồ giá close + sentiment MA20 + **vạch đỏ/xanh ở mỗi CP**
 *   3. Bảng tin tức về mã + sentiment đã chấm
 *   4. KPI tổng aggregate (cuối trang) + bảng match_rate per mã VN30
 */
export default function ChangePointsView() {
  const [symbol, setSymbol] = useState('FPT')
  const [symbols, setSymbols] = useState([])
  const [rangeDays, setRangeDays] = useState(180)

  // ── 1. Symbol list (chỉ 30 VN30) ─────────────────────────────────
  useEffect(() => {
    async function loadSyms() {
      // FIX: order by date desc → 500 dòng mới nhất sẽ chứa đủ 30 mã
      // (default order là PK = (symbol,date,timeframe) → 500 dòng đầu = toàn 1 mã ACB)
      const { data } = await supabase
        .from('technical_indicators')
        .select('symbol')
        .order('date', { ascending: false })
        .limit(500)
      if (data) {
        const u = [...new Set(data.map(r => r.symbol))].sort()
        setSymbols(u)
        if (u.length && !u.includes(symbol)) setSymbol(u[0])
      }
    }
    loadSyms()
  }, [])

  // ── 2. Per-stock data (chart + KPI latest) ────────────────────────
  const [priceData, setPriceData] = useState([])
  const [sentimentData, setSentimentData] = useState([])
  const [cpForSymbol, setCpForSymbol] = useState([])
  const [latestKpi, setLatestKpi] = useState(null)
  const [newsRows, setNewsRows] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!symbol) return
    setLoading(true)

    const cutoff = new Date()
    cutoff.setDate(cutoff.getDate() - rangeDays)
    const cutoffStr = cutoff.toISOString().slice(0, 10)

    Promise.all([
      // Price
      supabase.from('stock_prices')
        .select('date, close, volume')
        .eq('symbol', symbol)
        .gte('date', cutoffStr)
        .order('date', { ascending: true })
        .limit(2000),
      // Sentiment per date (cùng mã hoặc MARKET)
      supabase.from('daily_sentiment')
        .select('symbol, date, mean_score, n_news')
        .in('symbol', [symbol, 'MARKET'])
        .gte('date', cutoffStr)
        .order('date', { ascending: true })
        .limit(4000),
      // CPs for this symbol
      supabase.from('change_points')
        .select('change_point_date, direction, magnitude')
        .eq('symbol', symbol)
        .order('change_point_date', { ascending: true })
        .limit(500),
      // Latest KPI snapshot
      supabase.from('technical_indicators')
        .select('*')
        .eq('symbol', symbol)
        .order('date', { ascending: false })
        .limit(1),
    ]).then(([p, s, c, k]) => {
      setPriceData(p.data || [])
      setSentimentData(s.data || [])
      setCpForSymbol(c.data || [])
      setLatestKpi(k.data?.[0] || null)
    })

    // News table: 2 queries (mapping → news_id list → news_links + sentiment)
    ;(async () => {
      const { data: maps } = await supabase
        .from('news_stock_mapping')
        .select('news_id')
        .eq('symbol', symbol)
        .limit(500)
      if (!maps?.length) { setNewsRows([]); setLoading(false); return }
      const ids = maps.map(m => m.news_id)

      const [{ data: links }, { data: sents }] = await Promise.all([
        supabase.from('news_links')
          .select('id, title, source, url, published_at')
          .in('id', ids).order('published_at', { ascending: false }).limit(50),
        supabase.from('news_sentiment')
          .select('news_id, score, polarity, label_3cls, lex_net')
          .in('news_id', ids).limit(500),
      ])
      const sMap = {}
      ;(sents || []).forEach(s => { sMap[s.news_id] = s })
      const rows = (links || []).map(l => ({ ...l, sent: sMap[l.id] }))
      setNewsRows(rows)
      setLoading(false)
    })()
  }, [symbol, rangeDays])

  // ── 3. Aggregate stats (toàn VN30) ────────────────────────────────
  const { data: cpsAll } = useSupabaseQuery('change_points', {
    select: 'direction', limit: 1000, refreshInterval: 60000,
  })
  const { data: corrTests } = useSupabaseQuery('correlation_tests', {
    select: '*', orderBy: 'created_at', ascending: false, limit: 1, refreshInterval: 60000,
  })
  const { data: corrSummary } = useSupabaseQuery('correlation_summary', {
    select: 'symbol, n_cp, coverage, match_rate', orderBy: 'match_rate',
    ascending: false, limit: 50, refreshInterval: 60000,
  })

  // ── 4. Build chart data ───────────────────────────────────────────
  const labels = priceData.map(d => d.date)
  const closes = priceData.map(d => d.close)

  // Sentiment series aligned (gộp tin của symbol + MARKET → mean weighted by n_news)
  const sentByDate = {}
  sentimentData.forEach(s => {
    const k = s.date
    if (!sentByDate[k]) sentByDate[k] = { sum: 0, n: 0 }
    sentByDate[k].sum += (s.mean_score || 0) * (s.n_news || 1)
    sentByDate[k].n += (s.n_news || 1)
  })
  const sentScores = labels.map(d => {
    const v = sentByDate[d]
    return v ? v.sum / v.n : null
  })
  // Rolling MA(10) sentiment
  const sentMA = sentScores.map((_, i, arr) => {
    const win = arr.slice(Math.max(0, i - 9), i + 1).filter(v => v !== null)
    return win.length < 3 ? null : win.reduce((a, b) => a + b, 0) / win.length
  })

  // CPs as plugin payload (filter to window)
  const cpsInRange = cpForSymbol.filter(cp => labels.includes(cp.change_point_date)).map(cp => ({
    date: cp.change_point_date,
    direction: cp.direction,
  }))

  const chartData = {
    labels,
    datasets: [
      {
        label: `Giá ${symbol}`, data: closes,
        borderColor: '#00b8ff', backgroundColor: 'rgba(0,184,255,0.06)',
        yAxisID: 'y', tension: 0.25, fill: true,
        borderWidth: 1.7, pointRadius: 0, pointHoverRadius: 4,
      },
      {
        label: 'Sentiment MA10', data: sentMA,
        borderColor: '#ffbe2e', backgroundColor: 'transparent',
        yAxisID: 'y1', tension: 0.3, borderDash: [3, 3],
        borderWidth: 1.3, pointRadius: 0, spanGaps: true,
      },
    ],
  }
  const chartOptions = {
    responsive: true, maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    scales: {
      x: { ticks: { color: '#4e6a84', font: { size: 9 }, maxTicksLimit: 12 },
           grid: { color: 'rgba(56,120,180,0.05)' } },
      y: { type: 'linear', position: 'left',
           ticks: { color: '#8da5bf', font: { size: 10 } },
           grid: { color: 'rgba(56,120,180,0.08)' } },
      y1: { type: 'linear', position: 'right', min: -1, max: 1,
            ticks: { color: '#ffbe2e', font: { size: 10 } },
            grid: { drawOnChartArea: false } },
    },
    plugins: {
      legend: { labels: { color: '#8da5bf', font: { size: 11 }, usePointStyle: true } },
      tooltip: { backgroundColor: '#132847', borderColor: 'rgba(0,184,255,0.3)',
                 borderWidth: 1, titleColor: '#e8f0fa', bodyColor: '#8da5bf' },
      cpLines: { cps: cpsInRange },
    },
  }

  // ── 5. KPI cards data — đồng bộ với compute_kpi.ipynb ─────────────
  const k = latestKpi || {}
  const close = priceData.length ? priceData[priceData.length - 1].close : null
  const fmt = (v, d = 2) => (v === null || v === undefined) ? '—' : Number(v).toFixed(d)
  const fmtPct = v => (v === null || v === undefined) ? '—' : `${(Number(v) * 100).toFixed(2)}%`
  const fmtBig = v => {
    if (v === null || v === undefined) return '—'
    const n = Number(v)
    if (Math.abs(n) >= 1e9) return (n / 1e9).toFixed(2) + 'B'
    if (Math.abs(n) >= 1e6) return (n / 1e6).toFixed(2) + 'M'
    if (Math.abs(n) >= 1e3) return (n / 1e3).toFixed(1) + 'K'
    return n.toFixed(0)
  }
  const rsi = k.rsi_14 !== undefined && k.rsi_14 !== null ? Number(k.rsi_14) : null
  const rsiColor = rsi === null ? 'accent' : rsi >= 70 ? 'red' : rsi <= 30 ? 'green' : 'accent'
  const macdHist = k.macd_hist !== undefined ? Number(k.macd_hist) : null
  const macdColor = macdHist === null ? 'accent' : macdHist >= 0 ? 'green' : 'red'
  // Trend signal: close vs MA20/MA50
  const ma20 = k.ma_20 ? Number(k.ma_20) : null
  const ma50 = k.ma_50 ? Number(k.ma_50) : null
  const trendColor = (close && ma50 && close > ma50) ? 'green' : (close && ma50 && close < ma50) ? 'red' : 'accent'
  const trendLabel = (close && ma50)
    ? (close > ma50 ? 'Trên MA50 (uptrend)' : 'Dưới MA50 (downtrend)')
    : ''

  const kpiCards = [
    { icon: '📊', label: 'RSI(14)',
      value: fmt(rsi, 1),
      sub: rsi === null ? '' : rsi >= 70 ? 'Quá mua' : rsi <= 30 ? 'Quá bán' : 'Trung tính',
      color: rsiColor },
    { icon: '〽️', label: 'MACD Hist',
      value: fmt(macdHist, 3),
      sub: `MACD ${fmt(k.macd_line, 3)} | Sig ${fmt(k.macd_signal, 3)}`,
      color: macdColor },
    { icon: '📏', label: 'MA20 / MA50',
      value: `${fmt(ma20, 2)} / ${fmt(ma50, 2)}`,
      sub: trendLabel,
      color: trendColor },
    { icon: '📐', label: 'Bollinger %b',
      value: fmt(k.bb_pctb, 2),
      sub: `Upper ${fmt(k.bb_upper, 2)} / Lower ${fmt(k.bb_lower, 2)}`,
      color: (k.bb_pctb > 1) ? 'red' : (k.bb_pctb < 0) ? 'green' : 'accent' },
    { icon: '🔁', label: 'Volatility(20)',
      value: fmt(k.volatility_20, 4),
      sub: 'σ log-return 20 ngày',
      color: 'yellow' },
    { icon: '↕️', label: 'Daily / Log return',
      value: fmtPct(k.daily_return),
      sub: `log_ret ${fmt(k.log_return, 4)}`,
      color: (k.daily_return || 0) > 0 ? 'green' : (k.daily_return || 0) < 0 ? 'red' : 'accent' },
    { icon: '📉', label: 'Drawdown',
      value: fmtPct(k.drawdown),
      sub: 'từ đỉnh lịch sử',
      color: 'red' },
    { icon: '🔊', label: 'Volume Δ / OBV',
      value: fmtPct(k.volume_change),
      sub: `OBV ${fmtBig(k.obv)}`,
      color: (k.volume_change || 0) > 0 ? 'green' : 'accent' },
    { icon: '🎯', label: 'Điểm thay đổi',
      value: cpForSymbol.length,
      sub: `🟢 ${cpForSymbol.filter(c => c.direction === 1).length} · 🔴 ${cpForSymbol.filter(c => c.direction === -1).length}`,
      color: 'accent' },
  ]

  // ── 6. Aggregate KPIs (cuối trang) ────────────────────────────────
  const totalCp = cpsAll.length
  const cpUp = cpsAll.filter(c => c.direction === 1).length
  const cpDown = cpsAll.filter(c => c.direction === -1).length
  const corr = corrTests[0]

  const SENT_DISPLAY = {
    positive: { label: 'Tích cực', cls: 'positive' },
    negative: { label: 'Tiêu cực', cls: 'negative' },
    neutral:  { label: 'Trung tính', cls: 'neutral' },
  }

  return (
    <>
      {/* ── Header chọn mã ─────────────────────────────────────── */}
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-header">
          <div className="card-title">
            🎯 Phân tích theo mã —{' '}
            <select
              value={symbol} onChange={e => setSymbol(e.target.value)}
              style={{
                background: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)',
                color: 'var(--accent)', padding: '4px 10px', borderRadius: 6,
                fontSize: 13, fontWeight: 700, cursor: 'pointer', fontFamily: 'var(--font)',
              }}
            >
              {symbols.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <div className="time-range">
            {TIME_RANGES.map(t => (
              <button key={t.days}
                className={`time-btn${rangeDays === t.days ? ' active' : ''}`}
                onClick={() => setRangeDays(t.days)}>
                {t.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* ── KPI cards của mã được chọn ────────────────────────── */}
      <div className="kpi-grid" style={{ marginBottom: 16 }}>
        {kpiCards.map((kpi, i) => (
          <div key={i} className="kpi-card">
            <div className="kpi-icon">{kpi.icon}</div>
            <div className="kpi-label">{kpi.label}</div>
            <div className={`kpi-value ${kpi.color}`}>{kpi.value}</div>
            {kpi.sub && <div className="kpi-sub">{kpi.sub}</div>}
          </div>
        ))}
      </div>

      {/* ── Biểu đồ giá + sentiment + CP red lines ─────────────── */}
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-header">
          <div className="card-title">
            📈 {symbol} — Giá + Sentiment + Điểm thay đổi
          </div>
          <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
            <span style={{ color: 'var(--green)' }}>━</span> CP tăng ({cpsInRange.filter(c => c.direction === 1).length}) ·{' '}
            <span style={{ color: 'var(--red)' }}>━</span> CP giảm ({cpsInRange.filter(c => c.direction === -1).length})
          </span>
        </div>
        <div className="card-body" style={{ height: 380 }}>
          {priceData.length === 0 ? (
            <div className="empty-state">
              <div className="empty-icon">📉</div>
              <span>Chưa có dữ liệu giá cho {symbol}</span>
            </div>
          ) : (
            <Line data={chartData} options={chartOptions} />
          )}
        </div>
      </div>

      {/* ── Bảng tin tức về mã + sentiment ─────────────────────── */}
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-header">
          <div className="card-title">📰 Tin tức về {symbol} (kèm sentiment)</div>
          <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{newsRows.length} bài</span>
        </div>
        <div className="card-body" style={{ overflowY: 'auto', maxHeight: 400 }}>
          {loading ? (
            <div className="loading-spinner"><div className="spinner" /> Đang tải...</div>
          ) : newsRows.length === 0 ? (
            <div className="empty-state"><div className="empty-icon">📭</div><span>Chưa có tin về {symbol}</span></div>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border-subtle)', color: 'var(--text-muted)', textTransform: 'uppercase', fontSize: 10 }}>
                  <th style={{ padding: '8px 10px', textAlign: 'left', width: 100 }}>Ngày</th>
                  <th style={{ padding: '8px 10px', textAlign: 'left', width: 120 }}>Nguồn</th>
                  <th style={{ padding: '8px 10px', textAlign: 'left' }}>Tiêu đề</th>
                  <th style={{ padding: '8px 10px', textAlign: 'center', width: 100 }}>Sắc thái</th>
                  <th style={{ padding: '8px 10px', textAlign: 'right', width: 80 }}>Score</th>
                </tr>
              </thead>
              <tbody>
                {newsRows.map(r => {
                  const s = r.sent
                  const info = s ? SENT_DISPLAY[s.label_3cls] : null
                  const sc = s?.score
                  return (
                    <tr key={r.id}
                        style={{ borderBottom: '1px solid var(--border-subtle)', cursor: 'pointer' }}
                        onClick={() => r.url && window.open(r.url, '_blank')}>
                      <td style={{ padding: '8px 10px', color: 'var(--text-muted)', fontSize: 11 }}>
                        {r.published_at?.slice(0, 10)}
                      </td>
                      <td style={{ padding: '8px 10px', color: 'var(--text-secondary)' }}>{r.source}</td>
                      <td style={{ padding: '8px 10px' }}>{r.title}</td>
                      <td style={{ padding: '8px 10px', textAlign: 'center' }}>
                        {info ? <span className={`sentiment-badge ${info.cls}`}>{info.label}</span> : '—'}
                      </td>
                      <td style={{ padding: '8px 10px', textAlign: 'right', fontWeight: 600,
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

      {/* ── Aggregate VN30 + bảng match rate ───────────────────── */}
      <div className="kpi-grid" style={{ marginBottom: 16 }}>
        <div className="kpi-card">
          <div className="kpi-icon">🎯</div><div className="kpi-label">Tổng CP toàn VN30</div>
          <div className="kpi-value accent">{totalCp}</div>
          <div className="kpi-sub">🟢 {cpUp} tăng · 🔴 {cpDown} giảm</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-icon">📊</div><div className="kpi-label">Coverage</div>
          <div className="kpi-value green">{corr ? `${(corr.coverage * 100).toFixed(1)}%` : '—'}</div>
          <div className="kpi-sub">{corr ? `cửa sổ ±${corr.window_before}/${corr.window_after}` : ''}</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-icon">🔗</div><div className="kpi-label">Match rate</div>
          <div className="kpi-value yellow">{corr ? `${(corr.match_rate * 100).toFixed(1)}%` : '—'}</div>
          <div className="kpi-sub">
            {corr ? `CI [${(corr.bootstrap_ci_low * 100).toFixed(1)}, ${(corr.bootstrap_ci_high * 100).toFixed(1)}]%` : ''}
          </div>
        </div>
        <div className="kpi-card">
          <div className="kpi-icon">🧪</div><div className="kpi-label">Permutation p</div>
          <div className={`kpi-value ${corr && corr.p_value_two_sided < 0.05 ? 'green' : 'accent'}`}>
            {corr ? Number(corr.p_value_two_sided).toFixed(3) : '—'}
          </div>
          <div className="kpi-sub">{corr ? (corr.reject_h0_at_005 ? '✓ Có liên hệ' : 'Không bác H₀') : ''}</div>
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <div className="card-title">📋 Match rate per mã VN30 (click để chọn)</div>
          <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{corrSummary.length} mã</span>
        </div>
        <div className="card-body" style={{ overflowY: 'auto', maxHeight: 320 }}>
          {corrSummary.length === 0 ? (
            <div className="empty-state"><div className="empty-icon">📊</div><span>Chưa có dữ liệu tương quan</span></div>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border-subtle)', color: 'var(--text-muted)', textTransform: 'uppercase', fontSize: 10 }}>
                  <th style={{ padding: '8px 10px', textAlign: 'left' }}>Mã</th>
                  <th style={{ padding: '8px 10px', textAlign: 'right' }}># CP</th>
                  <th style={{ padding: '8px 10px', textAlign: 'right' }}>Coverage</th>
                  <th style={{ padding: '8px 10px', textAlign: 'right' }}>Match rate</th>
                </tr>
              </thead>
              <tbody>
                {corrSummary.map(r => {
                  const mr = r.match_rate
                  const cls = mr >= 0.6 ? 'green' : mr <= 0.4 ? 'red' : 'accent'
                  const active = r.symbol === symbol
                  return (
                    <tr key={r.symbol}
                        style={{ borderBottom: '1px solid var(--border-subtle)', cursor: 'pointer',
                                 background: active ? 'rgba(0,184,255,0.08)' : 'transparent' }}
                        onClick={() => setSymbol(r.symbol)}>
                      <td style={{ padding: '8px 10px', fontWeight: 700, color: 'var(--accent)' }}>{r.symbol}</td>
                      <td style={{ padding: '8px 10px', textAlign: 'right' }}>{r.n_cp}</td>
                      <td style={{ padding: '8px 10px', textAlign: 'right' }}>{(r.coverage * 100).toFixed(1)}%</td>
                      <td style={{ padding: '8px 10px', textAlign: 'right', fontWeight: 600, color: `var(--${cls})` }}>
                        {mr !== null ? `${(mr * 100).toFixed(1)}%` : '—'}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </>
  )
}
