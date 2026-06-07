import React, { useState, useEffect } from 'react'
import {
  Chart as ChartJS, CategoryScale, LinearScale,
  PointElement, LineElement, BarElement,
  Tooltip, Legend, Filler,
} from 'chart.js'
import { Line } from 'react-chartjs-2'
import { supabase } from '../../lib/supabase'

ChartJS.register(
  CategoryScale, LinearScale, PointElement,
  LineElement, BarElement, Tooltip, Legend, Filler,
)

const TIME_RANGES = [
  { label: '7D', days: 7 },
  { label: '30D', days: 30 },
  { label: '90D', days: 90 },
  { label: '1Y', days: 365 },
]

export default function PriceChart() {
  const [symbol, setSymbol] = useState('')
  const [range, setRange] = useState(30)
  const [priceData, setPriceData] = useState([])
  const [symbols, setSymbols] = useState([])
  const [loading, setLoading] = useState(true)

  // Load available symbols from stock_prices (actual data, not companies table)
  useEffect(() => {
    async function loadSymbols() {
      // Lấy mã từ technical_indicators (chỉ 30 mã VN30, KHÔNG có hàng nghìn mã khác)
      // → tránh lỗi cũ: ORDER BY symbol + LIMIT 500 chỉ trả 1 mã "A32"
      const { data } = await supabase
        .from('technical_indicators')
        .select('symbol')
        .order('date', { ascending: false })
        .limit(2000)

      // Fallback nếu technical_indicators rỗng → dùng stock_prices order theo date
      let unique = data ? [...new Set(data.map(r => r.symbol))].sort() : []
      if (unique.length === 0) {
        const fb = await supabase
          .from('stock_prices')
          .select('symbol')
          .order('date', { ascending: false })
          .limit(2000)
        unique = fb.data ? [...new Set(fb.data.map(r => r.symbol))].sort() : []
      }

      setSymbols(unique)
      if (unique.length > 0 && !symbol) {
        const preferred = ['FPT', 'VNM', 'HPG', 'VCB', 'ACB']
        const found = preferred.find(s => unique.includes(s))
        setSymbol(found || unique[0])
      }
    }
    loadSymbols()
  }, [])

  // Load price data for selected symbol
  useEffect(() => {
    if (!symbol) return

    setLoading(true)
    const cutoff = new Date()
    cutoff.setDate(cutoff.getDate() - range)

    supabase
      .from('stock_prices')
      .select('date, open, high, low, close, volume')
      .eq('symbol', symbol)
      .gte('date', cutoff.toISOString().slice(0, 10))
      .order('date', { ascending: true })
      .limit(500)
      .then(({ data, error }) => {
        if (!error && data) setPriceData(data)
        else setPriceData([])
        setLoading(false)
      })
  }, [symbol, range])

  // Chart data
  const labels = priceData.map(d => {
    const dt = new Date(d.date)
    return `${dt.getDate()}/${dt.getMonth() + 1}`
  })

  const chartData = {
    labels,
    datasets: [
      {
        label: `Giá ${symbol}`,
        data: priceData.map(d => d.close),
        borderColor: '#00b8ff',
        backgroundColor: 'rgba(0,184,255,0.06)',
        yAxisID: 'y',
        tension: 0.3,
        fill: true,
        borderWidth: 2,
        pointRadius: 0,
        pointHoverRadius: 4,
      },
      {
        label: 'Khối lượng',
        data: priceData.map(d => d.volume),
        borderColor: '#ffbe2e',
        backgroundColor: 'rgba(255,190,46,0.04)',
        yAxisID: 'y1',
        tension: 0.3,
        borderDash: [4, 3],
        borderWidth: 1.5,
        pointRadius: 0,
      },
    ],
  }

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    scales: {
      x: {
        ticks: { color: '#4e6a84', font: { size: 10 }, maxTicksLimit: 12 },
        grid: { color: 'rgba(56,120,180,0.06)' },
      },
      y: {
        type: 'linear', position: 'left',
        ticks: { color: '#8da5bf', font: { size: 10 } },
        grid: { color: 'rgba(56,120,180,0.08)' },
      },
      y1: {
        type: 'linear', position: 'right',
        ticks: {
          color: '#ffbe2e', font: { size: 10 },
          callback: v => v >= 1e6 ? `${(v / 1e6).toFixed(1)}M` : v >= 1e3 ? `${(v / 1e3).toFixed(0)}K` : v,
        },
        grid: { drawOnChartArea: false },
      },
    },
    plugins: {
      legend: { labels: { color: '#8da5bf', font: { size: 11 }, usePointStyle: true, pointStyle: 'circle' } },
      tooltip: {
        backgroundColor: '#132847',
        borderColor: 'rgba(0,184,255,0.3)',
        borderWidth: 1,
        titleColor: '#e8f0fa',
        bodyColor: '#8da5bf',
        callbacks: {
          label: ctx => {
            if (ctx.datasetIndex === 1) return `Volume: ${(ctx.parsed.y / 1e3).toFixed(0)}K`
            return `Giá: ${ctx.parsed.y?.toLocaleString('vi-VN')}`
          }
        }
      },
    },
  }

  return (
    <div className="card" style={{ flex: 1 }}>
      <div className="card-header">
        <div className="card-title">
          📈 Giá & Khối lượng —{' '}
          <select
            value={symbol}
            onChange={e => setSymbol(e.target.value)}
            style={{
              background: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)',
              color: 'var(--accent)', padding: '3px 8px', borderRadius: 6,
              fontSize: 12, fontWeight: 700, cursor: 'pointer', fontFamily: 'var(--font)',
            }}
          >
            {symbols.length === 0 && <option value="">Đang tải...</option>}
            {symbols.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        <div className="time-range">
          {TIME_RANGES.map(t => (
            <button
              key={t.days}
              className={`time-btn${range === t.days ? ' active' : ''}`}
              onClick={() => setRange(t.days)}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>
      <div className="card-body">
        {loading ? (
          <div className="loading-spinner"><div className="spinner" /> Đang tải dữ liệu {symbol}...</div>
        ) : priceData.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">📉</div>
            <span>Chưa có dữ liệu giá cho {symbol} trong {range} ngày gần nhất</span>
            <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>Thử chọn khoảng thời gian lớn hơn hoặc mã khác</span>
          </div>
        ) : (
          <Line data={chartData} options={chartOptions} style={{ height: '100%' }} />
        )}
      </div>
    </div>
  )
}
