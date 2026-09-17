import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import Setter from './pages/Setter'
import Centre from './pages/Centre'
import Forensic from './pages/Forensic'
import Audit from './pages/Audit'

const Icons = {
  Lock: () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect>
      <path d="M7 11V7a5 5 0 0 1 10 0v4"></path>
    </svg>
  ),
  Building: () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 21h18"></path>
      <path d="M5 21V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v16"></path>
      <path d="M9 9h1"></path>
      <path d="M9 13h1"></path>
      <path d="M9 17h1"></path>
      <path d="M14 9h1"></path>
      <path d="M14 13h1"></path>
      <path d="M14 17h1"></path>
    </svg>
  ),
  Radar: () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10"></circle>
      <path d="m16.2 7.8-4.2 4.2"></path>
      <circle cx="12" cy="12" r="6"></circle>
      <circle cx="12" cy="12" r="2"></circle>
    </svg>
  ),
  Ledger: () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
      <polyline points="14 2 14 8 20 8"></polyline>
      <line x1="16" y1="13" x2="8" y2="13"></line>
      <line x1="16" y1="17" x2="8" y2="17"></line>
      <polyline points="10 9 9 9 8 9"></polyline>
    </svg>
  ),
  ShieldLogo: () => (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path>
      <path d="m9 12 2 2 4-4"></path>
    </svg>
  )
}

const NAV = [
  { path: '/setter',   label: 'Paper Vault',        Icon: Icons.Lock,     section: 'CUSTODY OPERATIONS' },
  { path: '/centre',   label: 'Centre Custodian',   Icon: Icons.Building, section: null },
  { path: '/forensic', label: 'Forensic Tracer',    Icon: Icons.Radar,    section: 'INTELLIGENCE' },
  { path: '/audit',    label: 'Ledger Audit Chain', Icon: Icons.Ledger,   section: null },
]

export default function App() {
  return (
    <BrowserRouter>
      <div className="app-shell">
        {/* Sidebar */}
        <nav className="sidebar">
          <div className="sidebar-logo">
            <div className="sidebar-logo-icon">
              <Icons.ShieldLogo />
            </div>
            <div className="sidebar-logo-text">
              <span>ZeroLock</span>
              <span className="sidebar-logo-sub">Enterprise Custody</span>
            </div>
          </div>

          {NAV.map((item) => (
            <div key={item.path}>
              {item.section && (
                <div className="nav-section-label">{item.section}</div>
              )}
              <NavLink
                to={item.path}
                className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}
              >
                <item.Icon />
                <span>{item.label}</span>
              </NavLink>
            </div>
          ))}

          <div style={{ marginTop: 'auto', paddingTop: 24 }}>
            <div style={{
              padding: '12px 14px',
              background: '#f5f5f7',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-md)',
              fontSize: '11.5px',
              color: 'var(--text-secondary)',
              lineHeight: 1.6
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#34c759', display: 'inline-block' }}></span>
                <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>EVM Gateway Online</span>
              </div>
              <div style={{ color: 'var(--text-secondary)', fontSize: '11px', fontFamily: 'JetBrains Mono, monospace' }}>
                Chain: Hardhat (31337)
              </div>
              <div style={{ color: 'var(--text-secondary)', fontSize: '11px', fontFamily: 'JetBrains Mono, monospace', marginTop: 2 }}>
                Contract: PaperVault.sol
              </div>
            </div>
          </div>
        </nav>

        {/* Main content */}
        <main className="main-content">
          <Routes>
            <Route path="/"          element={<Setter />} />
            <Route path="/setter"    element={<Setter />} />
            <Route path="/centre"    element={<Centre />} />
            <Route path="/forensic"  element={<Forensic />} />
            <Route path="/audit"     element={<Audit />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}
