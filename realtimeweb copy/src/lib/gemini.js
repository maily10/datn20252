/**
 * Gemini AI client for the AI Chat feature.
 *
 * Uses the Gemini REST API directly from the browser.
 * The API key should be set in .env as VITE_GEMINI_API_KEY.
 */

const API_KEY = import.meta.env.VITE_GEMINI_API_KEY
const MODEL = 'gemini-2.0-flash'
const API_URL = `https://generativelanguage.googleapis.com/v1beta/models/${MODEL}:generateContent`

const SYSTEM_PROMPT = `Bạn là AI trợ lý phân tích thị trường chứng khoán Việt Nam, đặc thù rổ VN-30.
Bạn có quyền truy cập dữ liệu từ hệ thống đồ án (giá OHLCV, KPI kỹ thuật, tin tức, sentiment Hybrid PhoBERT+Lexicon, điểm thay đổi PELT, kiểm định thống kê tương quan).

Nhiệm vụ:
- Phân tích thị trường VN-30 dựa trên dữ liệu được cung cấp
- Giải thích sắc thái tin tức (Hybrid PhoBERT + từ điển tài chính)
- Diễn giải điểm thay đổi giá (PELT) và liên hệ với tin tức nếu có
- Trả lời câu hỏi về cổ phiếu cụ thể, tin tức, hoặc tổng quan thị trường

Quy tắc:
- Luôn trả lời bằng tiếng Việt
- Dựa trên dữ liệu thực được cung cấp, KHÔNG bịa đặt
- KHÔNG đưa khuyến nghị mua/bán (không phải mục tiêu đồ án)
- KHÔNG tuyên bố nhân quả khi không có bằng chứng — chỉ nói về "liên hệ thống kê"
- Sử dụng số liệu cụ thể từ dữ liệu`

/**
 * Send a message to Gemini with database context.
 */
export async function askGemini(userMessage, context = {}) {
  if (!API_KEY) {
    return '⚠️ Chưa cấu hình VITE_GEMINI_API_KEY trong file .env.'
  }

  let contextStr = ''
  if (context.recentNews?.length) {
    contextStr += '\n📰 TIN TỨC GẦN NHẤT:\n'
    context.recentNews.forEach((n, i) => {
      contextStr += `${i + 1}. [${n.source}] ${n.title} — Sentiment: ${n.label_text} (score=${n.confidence_score})\n`
      if (n.summary) contextStr += `   Tóm tắt: ${n.summary.substring(0, 200)}...\n`
    })
  }
  if (context.sentimentSummary) {
    const s = context.sentimentSummary
    contextStr += `\n💬 TỔNG HỢP SENTIMENT: Tích cực=${s.positive} · Tiêu cực=${s.negative} · Trung tính=${s.neutral}\n`
  }
  if (context.changePoints?.length) {
    contextStr += '\n🎯 ĐIỂM THAY ĐỔI GẦN NHẤT (PELT):\n'
    context.changePoints.forEach(c => {
      const arrow = c.direction === 1 ? '↑' : '↓'
      contextStr += `  ${c.symbol} ${c.change_point_date}: ${arrow} magnitude=${c.magnitude?.toFixed?.(4)}\n`
    })
  }
  if (context.correlation) {
    const k = context.correlation
    contextStr += `\n🔗 KIỂM ĐỊNH TƯƠNG QUAN (aggregate VN30):\n`
    contextStr += `  Coverage=${(k.coverage * 100).toFixed(1)}%, Match rate=${(k.match_rate * 100).toFixed(1)}%\n`
    contextStr += `  Permutation p (2 phía)=${k.p_value_two_sided?.toFixed?.(3)}, `
    contextStr += `Bootstrap 95% CI=[${(k.bootstrap_ci_low * 100).toFixed(1)}%, ${(k.bootstrap_ci_high * 100).toFixed(1)}%]\n`
    contextStr += `  → ${k.reject_h0_at_005 ? 'Có liên hệ thống kê' : 'Không bác H₀ ở α=0.05 (không có liên hệ ý nghĩa thống kê)'}\n`
  }
  if (context.priceData?.length) {
    contextStr += '\n💰 GIÁ CỔ PHIẾU GẦN NHẤT:\n'
    context.priceData.forEach(p => {
      contextStr += `  ${p.symbol}: close=${p.close}, volume=${p.volume} (${p.date})\n`
    })
  }

  const fullPrompt = contextStr
    ? `[DỮ LIỆU HỆ THỐNG]\n${contextStr}\n\n[CÂU HỎI CỦA NGƯỜI DÙNG]\n${userMessage}`
    : userMessage

  try {
    const response = await fetch(`${API_URL}?key=${API_KEY}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        system_instruction: { parts: [{ text: SYSTEM_PROMPT }] },
        contents: [{ parts: [{ text: fullPrompt }] }],
        generationConfig: { temperature: 0.4, maxOutputTokens: 2000 },
      }),
    })

    if (!response.ok) {
      const errData = await response.json().catch(() => ({}))
      throw new Error(errData?.error?.message || `HTTP ${response.status}`)
    }

    const data = await response.json()
    return data?.candidates?.[0]?.content?.parts?.[0]?.text
      || 'Không nhận được phản hồi từ AI.'
  } catch (err) {
    console.error('[Gemini]', err)
    return `❌ Lỗi khi gọi Gemini: ${err.message}`
  }
}
