import React from 'react'

const navItems = [
  { icon: '📊', label: 'Tổng quan', id: 'overview' },
  { icon: '📈', label: 'Giá & KPI', id: 'stocks' },
  { icon: '📰', label: 'Tin tức & Sentiment', id: 'news' },
  { icon: '🎯', label: 'Điểm thay đổi', id: 'changepoints' },
  { icon: '🤖', label: 'AI Phân tích', id: 'ai' },
  { icon: '🔧', label: 'Pipeline', id: 'pipeline' },
]

export default function Sidebar({ activePage, onNavigate, connectionStatus }) {
  return (
    <aside className="sidebar">
      {/* Brand */}
      <div className="sidebar-brand">
        <div className="brand-icon">📡</div>
        <div>
          <div className="brand-text">VN-30 Dashboard</div>
          <div className="brand-sub">Giá · Tin · Điểm thay đổi</div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="sidebar-nav">
        {navItems.map(item => (
          <button
            key={item.id}
            className={`nav-btn${activePage === item.id ? ' active' : ''}`}
            onClick={() => onNavigate(item.id)}
          >
            <span className="nav-icon">{item.icon}</span>
            {item.label}
          </button>
        ))}
      </nav>

      {/* Footer */}
      <div className="sidebar-footer">
        <div className="conn-status">
          <span className={`status-dot ${connectionStatus}`} />
          <span className="conn-label">Supabase</span>
          <span className={`conn-state ${connectionStatus === 'online' ? 'ok' : connectionStatus === 'offline' ? 'err' : 'wait'}`}>
            {connectionStatus === 'online' ? 'Connected' : connectionStatus === 'offline' ? 'Offline' : 'Checking...'}
          </span>
        </div>
        <div className="sidebar-version">VN-30 Monitor · Đồ án v1.0</div>
      </div>
    </aside>
  )
}
