import React, { useState, useEffect } from 'react'
import { supabase, subscribeToTable } from '../../lib/supabase'

const FILTERS = [
  { label: 'Tất cả', value: 'all' },
  { label: '👍 Tích cực', value: 'positive' },
  { label: '👎 Tiêu cực', value: 'negative' },
  { label: '😐 Trung tính', value: 'neutral' },
]

const SENTIMENT_DISPLAY = {
  positive: { label: 'Tích cực', cls: 'positive' },
  negative: { label: 'Tiêu cực', cls: 'negative' },
  neutral:  { label: 'Trung tính', cls: 'neutral' },
}

export default function NewsFeed() {
  const [filter, setFilter] = useState('all')
  const [news, setNews] = useState([])
  const [sentiments, setSentiments] = useState({})
  const [summaries, setSummaries] = useState({})
  const [loading, setLoading] = useState(true)

  const fetchNews = async () => {
    try {
      const { data: newsData, error } = await supabase
        .from('news_links')
        .select('id, url, title, source, published_at, published_date')
        .order('published_at', { ascending: false })
        .limit(30)
      if (error) throw error
      setNews(newsData || [])

      const ids = (newsData || []).map(n => n.id)
      if (!ids.length) { setLoading(false); return }

      const { data: sentData } = await supabase
        .from('news_sentiment')
        .select('news_id, score, polarity, label_3cls, lex_net')
        .in('news_id', ids)
      const smap = {}
      ;(sentData || []).forEach(s => { smap[s.news_id] = s })
      setSentiments(smap)

      const { data: contentData } = await supabase
        .from('news_content')
        .select('news_id, summary')
        .in('news_id', ids)
      const cmap = {}
      ;(contentData || []).forEach(c => { cmap[c.news_id] = c.summary })
      setSummaries(cmap)
    } catch (err) {
      console.error('[NewsFeed]', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchNews()
    const unsub = subscribeToTable('news_links', 'INSERT', () => fetchNews())
    return unsub
  }, [])

  const filtered = filter === 'all'
    ? news
    : news.filter(n => sentiments[n.id]?.label_3cls === filter)

  const timeAgo = (dateStr) => {
    if (!dateStr) return ''
    const diff = Date.now() - new Date(dateStr).getTime()
    const mins = Math.floor(diff / 60000)
    if (mins < 0) return 'vừa xong'
    if (mins < 60) return `${mins} phút trước`
    const hours = Math.floor(mins / 60)
    if (hours < 24) return `${hours} giờ trước`
    const days = Math.floor(hours / 24)
    return `${days} ngày trước`
  }

  return (
    <div className="news-feed">
      <div className="panel-header">
        📰 Tin tức & Sentiment
        <span className="panel-badge">{news.length} bài</span>
      </div>

      <div className="news-filter">
        {FILTERS.map(f => (
          <button
            key={f.value}
            className={`filter-btn${filter === f.value ? ' active' : ''}`}
            onClick={() => setFilter(f.value)}
          >
            {f.label}
          </button>
        ))}
      </div>

      <div className="news-list">
        {loading ? (
          <div className="loading-spinner"><div className="spinner" /> Đang tải tin tức...</div>
        ) : filtered.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">📭</div>
            <span>Không có tin tức</span>
          </div>
        ) : (
          filtered.map(n => {
            const s = sentiments[n.id]
            const info = s ? SENTIMENT_DISPLAY[s.label_3cls] : null
            const summary = summaries[n.id] || ''
            const score = s?.score
            const lexNet = s?.lex_net

            return (
              <article
                key={n.id}
                className="news-card"
                onClick={() => n.url && window.open(n.url, '_blank')}
              >
                <h4>{n.title || 'Không có tiêu đề'}</h4>
                <div className="news-meta">
                  <span>{n.source}</span>
                  <span>• {timeAgo(n.published_at)}</span>
                  {lexNet !== undefined && lexNet !== 0 && lexNet !== null && (
                    <span style={{ fontSize: 10, opacity: 0.7 }}>
                      • lex {lexNet > 0 ? '+' : ''}{lexNet}
                    </span>
                  )}
                  {info && (
                    <span className={`sentiment-badge ${info.cls}`}>{info.label}</span>
                  )}
                </div>
                {summary && <p className="news-summary">{summary}</p>}
                {score !== undefined && score !== null && (
                  <div className="news-confidence">
                    <span>Score: {score > 0 ? '+' : ''}{Number(score).toFixed(3)}</span>
                    <div className="confidence-bar">
                      <div
                        className="confidence-fill"
                        style={{
                          width: `${Math.min(100, Math.abs(Number(score)) * 100)}%`,
                          background: score > 0.2 ? 'var(--green)' :
                                       score < -0.2 ? 'var(--red)' : 'var(--text-muted)',
                        }}
                      />
                    </div>
                  </div>
                )}
              </article>
            )
          })
        )}
      </div>
    </div>
  )
}
