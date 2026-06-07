import React, { useState, useRef, useEffect } from 'react'
import { supabase } from '../../lib/supabase'
import { askGemini } from '../../lib/gemini'

const INITIAL_MSG = {
  type: 'bot',
  text: 'Xin chào! 👋 Tôi là AI trợ lý phân tích thị trường VN-30.\n\nBạn có thể hỏi:\n• "Thị trường hôm nay thế nào?"\n• "Tóm tắt tin tức gần nhất"\n• "FPT có biến động gì?"\n• "Điểm thay đổi nào đáng chú ý?"\n• "Sentiment ↔ giá có liên hệ thật không?"',
}

export default function AIChat() {
  const [messages, setMessages] = useState([INITIAL_MSG])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const endRef = useRef(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  /**
   * Gather context from Supabase before sending to Gemini.
   * Sources: news_links, news_content, news_sentiment, stock_prices, change_points,
   *          correlation_tests.
   */
  async function gatherContext(question) {
    const ctx = {}

    try {
      // Recent news + sentiment
      const { data: newsData } = await supabase
        .from('news_links')
        .select('id, title, source, published_at')
        .order('published_at', { ascending: false })
        .limit(10)

      if (newsData?.length) {
        const ids = newsData.map(n => n.id)
        const [{ data: contentData }, { data: sentData }] = await Promise.all([
          supabase.from('news_content').select('news_id, summary').in('news_id', ids),
          supabase.from('news_sentiment').select('news_id, score, polarity, label_3cls').in('news_id', ids),
        ])
        const cm = {}, sm = {}
        ;(contentData || []).forEach(c => { cm[c.news_id] = c.summary })
        ;(sentData || []).forEach(s => { sm[s.news_id] = s })

        ctx.recentNews = newsData.map(n => ({
          title: n.title, source: n.source, published_at: n.published_at,
          summary: cm[n.id] || '',
          label_text: sm[n.id]?.label_3cls || 'N/A',
          confidence_score: sm[n.id]?.score?.toFixed?.(3) || 'N/A',
        }))
      }

      // Sentiment distribution
      const { data: allSent } = await supabase
        .from('news_sentiment')
        .select('polarity').limit(2000)
      if (allSent?.length) {
        const c = { positive: 0, negative: 0, neutral: 0 }
        allSent.forEach(s => {
          if (s.polarity === 'positive') c.positive++
          else if (s.polarity === 'negative') c.negative++
          else c.neutral++
        })
        ctx.sentimentSummary = c
      }

      // Change points recent
      const { data: cpData } = await supabase
        .from('change_points')
        .select('symbol, change_point_date, direction, magnitude')
        .order('change_point_date', { ascending: false })
        .limit(15)
      if (cpData?.length) ctx.changePoints = cpData

      // Correlation summary
      const { data: corrData } = await supabase
        .from('correlation_tests')
        .select('*').order('created_at', { ascending: false }).limit(1)
      if (corrData?.length) ctx.correlation = corrData[0]

      // Specific symbol if mentioned
      const symbolMatch = question.match(/\b([A-Z]{2,4})\b/)
      if (symbolMatch) {
        const sym = symbolMatch[1]
        const { data: priceData } = await supabase
          .from('stock_prices')
          .select('symbol, date, close, volume').eq('symbol', sym)
          .order('date', { ascending: false }).limit(10)
        if (priceData?.length) ctx.priceData = priceData
      }
      if (!ctx.priceData) {
        const { data: priceData } = await supabase
          .from('stock_prices')
          .select('symbol, date, close, volume')
          .order('date', { ascending: false }).limit(30)
        if (priceData?.length) ctx.priceData = priceData
      }
    } catch (err) {
      console.error('[AIChat context]', err)
    }
    return ctx
  }

  async function handleSend() {
    const text = input.trim()
    if (!text || loading) return

    const userMsg = { type: 'user', text }
    setMessages(prev => [...prev, userMsg])
    setInput('')
    setLoading(true)

    const loadingId = Date.now()
    setMessages(prev => [...prev, { type: 'bot', text: '🔄 Đang phân tích dữ liệu...', _loading: loadingId }])

    try {
      const context = await gatherContext(text)
      const reply = await askGemini(text, context)

      const sources = []
      if (context.recentNews?.length) sources.push(`${context.recentNews.length} tin`)
      if (context.changePoints?.length) sources.push(`${context.changePoints.length} CP gần`)
      if (context.priceData?.length) sources.push(`${context.priceData.length} giá`)
      if (context.correlation) sources.push('1 kiểm định tương quan')

      setMessages(prev => {
        const filtered = prev.filter(m => m._loading !== loadingId)
        return [...filtered, {
          type: 'bot', text: reply,
          sources: sources.length ? `Dữ liệu: ${sources.join(', ')}` : null,
        }]
      })
    } catch (err) {
      setMessages(prev => {
        const filtered = prev.filter(m => m._loading !== loadingId)
        return [...filtered, { type: 'bot', text: `❌ Lỗi: ${err.message}` }]
      })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="ai-chat">
      <div className="panel-header">
        🤖 AI Chat — Phân tích thị trường
        {loading && <span className="panel-badge">Đang xử lý...</span>}
      </div>

      <div className="chat-messages">
        {messages.map((m, i) => (
          <div key={i} className={`chat-msg ${m.type}${m._loading ? ' loading' : ''}`}>
            <div style={{ whiteSpace: 'pre-wrap' }}>{m.text}</div>
            {m.sources && (
              <div className="msg-sources">📊 {m.sources}</div>
            )}
          </div>
        ))}
        <div ref={endRef} />
      </div>

      <div className="chat-input-area">
        <input
          placeholder="Hỏi về giá, tin tức, điểm thay đổi..."
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleSend()}
          disabled={loading}
        />
        <button
          className="chat-send-btn"
          onClick={handleSend}
          disabled={loading || !input.trim()}
        >
          {loading ? '...' : 'Gửi'}
        </button>
      </div>
    </div>
  )
}
