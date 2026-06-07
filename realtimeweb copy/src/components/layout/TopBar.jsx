import React, { useState, useEffect } from 'react'

const PAGE_TITLES = {
  overview: 'Tổng Quan Thị Trường',
  stocks: 'Giá & Chỉ Số Kỹ Thuật (KPI)',
  news: 'Tin Tức & Sentiment',
  changepoints: 'Điểm Thay Đổi & Tương Quan',
  ai: 'AI Phân Tích',
  pipeline: 'Pipeline & Đồng Bộ Dữ Liệu',
}

export default function TopBar({ activePage, connectionStatus, lastUpdate }) {
  const [clock, setClock] = useState(new Date())

  useEffect(() => {
    const id = setInterval(() => setClock(new Date()), 1000)
    return () => clearInterval(id)
  }, [])

  const timeStr = clock.toLocaleTimeString('vi-VN', { hour12: false })
  const dateStr = clock.toLocaleDateString('vi-VN', {
    weekday: 'long', day: '2-digit', month: '2-digit', year: 'numeric'
  })

  // Trading hours check (VN: 9:00-11:30, 13:00-14:45)
  const h = clock.getHours()
  const m = clock.getMinutes()
  const isTrading = (h >= 9 && (h < 11 || (h === 11 && m <= 30)))
    || (h >= 13 && (h < 14 || (h === 14 && m <= 45)))
  const dow = clock.getDay()
  const isWeekday = dow >= 1 && dow <= 5
  const tradingActive = isTrading && isWeekday

  return (
    <div className="topbar">
      <div className="topbar-left">
        <h1 className="topbar-title">{PAGE_TITLES[activePage] || 'Dashboard'}</h1>
        {tradingActive && (
          <span style={{
            fontSize: 11, fontWeight: 600,
            color: 'var(--green)',
            background: 'var(--green-bg)',
            padding: '3px 10px',
            borderRadius: 12,
            border: '1px solid rgba(0,230,138,0.2)',
          }}>
            🟢 Phiên giao dịch đang mở
          </span>
        )}
      </div>

      <div className="topbar-right">
        {lastUpdate && (
          <div className="topbar-status">
            <span className={`status-dot ${connectionStatus}`} />
            <span>Cập nhật: {lastUpdate}</span>
          </div>
        )}
        <div className="topbar-clock" title={dateStr}>
          {timeStr}
          <span style={{ fontSize: 10, marginLeft: 6, opacity: 0.7 }}>
            {clock.toLocaleDateString('vi-VN', { day: '2-digit', month: '2-digit' })}
          </span>
        </div>
      </div>
    </div>
  )
}
