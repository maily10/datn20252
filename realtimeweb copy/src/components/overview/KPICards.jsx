import React from 'react'
import { useSupabaseQuery } from '../../hooks/useSupabaseQuery'

/**
 * KPI cards — phản ánh trực tiếp 3 nội dung đồ án:
 *   (1) Thu thập giá   → # mã có giá + ngày cập nhật mới nhất
 *   (2) Tin + Sentiment → # tin đã chấm + tỉ lệ tích cực/tiêu cực
 *   (3) Điểm thay đổi  → # CP đã phát hiện + match rate ↔ tin (Mốc 4)
 */
export default function KPICards() {
  const { data: prices } = useSupabaseQuery('stock_prices', {
    select: 'symbol, date, close',
    orderBy: 'date', ascending: false, limit: 60, refreshInterval: 60000,
  })

  const { data: sentiments } = useSupabaseQuery('news_sentiment', {
    select: 'polarity, score', limit: 2000, refreshInterval: 60000,
  })

  const { data: newsCount } = useSupabaseQuery('news_links', {
    select: 'id', limit: 100, refreshInterval: 60000,
  })

  const { data: cps } = useSupabaseQuery('change_points', {
    select: 'id, direction', limit: 1000, refreshInterval: 60000,
  })

  const { data: corrTests } = useSupabaseQuery('correlation_tests', {
    select: 'match_rate, p_value_two_sided, bootstrap_ci_low, bootstrap_ci_high',
    orderBy: 'created_at', ascending: false, limit: 1, refreshInterval: 60000,
  })

  // ── Compute KPIs ────────────────────────────────────────────
  const uniqueSymbols = [...new Set(prices.map(p => p.symbol))]
  const latestDate = prices[0]?.date

  const sentCounts = { positive: 0, negative: 0 }
  sentiments.forEach(s => {
    if (s.polarity === 'positive') sentCounts.positive++
    else if (s.polarity === 'negative') sentCounts.negative++
  })
  const totalScored = sentCounts.positive + sentCounts.negative
  const posRatio = totalScored ? sentCounts.positive / totalScored : 0
  const sentLabel = totalScored === 0 ? 'Chưa có' :
    posRatio > 0.55 ? 'Tích cực' :
    posRatio < 0.45 ? 'Tiêu cực' : 'Cân bằng'
  const sentColor = totalScored === 0 ? 'accent' :
    posRatio > 0.55 ? 'green' :
    posRatio < 0.45 ? 'red' : 'accent'

  const cpUp = cps.filter(c => c.direction === 1).length
  const cpDown = cps.filter(c => c.direction === -1).length

  const corr = corrTests[0]
  const corrLabel = corr ? `${(corr.match_rate * 100).toFixed(1)}%` : '—'
  const corrSub = corr
    ? `p=${corr.p_value_two_sided?.toFixed(2)} · CI [${(corr.bootstrap_ci_low * 100).toFixed(1)}, ${(corr.bootstrap_ci_high * 100).toFixed(1)}]%`
    : 'chưa chạy đánh giá'

  const kpis = [
    {
      icon: '📈', label: 'Mã VN30 có giá',
      value: uniqueSymbols.length || '—', color: 'accent',
      sub: latestDate ? `Cập nhật ${latestDate}` : 'chưa có dữ liệu',
    },
    {
      icon: '📰', label: 'Tin đã chấm sentiment',
      value: totalScored ? `${totalScored.toLocaleString()}` : '0', color: 'green',
      sub: totalScored ? `👍 ${sentCounts.positive} · 👎 ${sentCounts.negative}`
                       : `${newsCount.length}+ tin trong DB`,
    },
    {
      icon: '💬', label: 'Cảm xúc trung bình',
      value: sentLabel, color: sentColor,
      sub: totalScored ? `Tỉ lệ tích cực ${(posRatio * 100).toFixed(1)}%` : 'chờ pipeline',
    },
    {
      icon: '🎯', label: 'Điểm thay đổi',
      value: cps.length || '—', color: 'yellow',
      sub: cps.length ? `🟢 ${cpUp} tăng · 🔴 ${cpDown} giảm` : 'chưa phát hiện',
    },
    {
      icon: '🔗', label: 'Match rate (CP↔tin)',
      value: corrLabel,
      color: corr && corr.p_value_two_sided < 0.05 ? 'green' : 'accent',
      sub: corrSub,
    },
  ]

  return (
    <div className="kpi-grid">
      {kpis.map((kpi, i) => (
        <div key={i} className="kpi-card">
          <div className="kpi-icon">{kpi.icon}</div>
          <div className="kpi-label">{kpi.label}</div>
          <div className={`kpi-value ${kpi.color}`}>{kpi.value}</div>
          {kpi.sub && <div className="kpi-sub">{kpi.sub}</div>}
        </div>
      ))}
    </div>
  )
}
