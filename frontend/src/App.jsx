import { useState } from 'react'
import {
  LayoutDashboard, Search, AlertTriangle, GitBranch, Users,
  FileText, MessageSquare, TrendingUp, Settings as SettingsIcon,
  BarChart2, Layers
} from 'lucide-react'
import Dashboard from './pages/Dashboard'
import Keywords from './pages/Keywords'
import BudgetWaste from './pages/BudgetWaste'
import Harvesting from './pages/Harvesting'
import Competitors from './pages/Competitors'
import Reports from './pages/Reports'
import AIChat from './pages/AIChat'
import SalesTracker from './pages/SalesTracker'
import MERDashboard from './pages/MERDashboard'
import CreativeCockpit from './pages/CreativeCockpit'
import Settings from './pages/Settings'

const NAV_ITEMS = [
  { id: 'dashboard',   label: 'Dashboard',       icon: LayoutDashboard },
  { id: 'mer',         label: 'MER / Blended',   icon: BarChart2 },
  { id: 'sales',       label: 'Sales Tracker',   icon: TrendingUp },
  { id: 'creatives',   label: 'Creative Cockpit',icon: Layers },
  { id: 'keywords',    label: 'Keywords',        icon: Search },
  { id: 'waste',       label: 'Waste',           icon: AlertTriangle },
  { id: 'harvest',     label: 'Harvest',         icon: GitBranch },
  { id: 'competitors', label: 'Competitors',     icon: Users },
  { id: 'reports',     label: 'Reports',         icon: FileText },
  { id: 'ai',          label: 'AI Chat',         icon: MessageSquare },
]

const PAGES = {
  dashboard:   Dashboard,
  mer:         MERDashboard,
  sales:       SalesTracker,
  creatives:   CreativeCockpit,
  keywords:    Keywords,
  waste:       BudgetWaste,
  harvest:     Harvesting,
  competitors: Competitors,
  reports:     Reports,
  ai:          AIChat,
  settings:    Settings,
}

export default function App() {
  const [active, setActive] = useState('dashboard')
  const [expanded, setExpanded] = useState(false)
  const Page = PAGES[active] || Dashboard

  return (
    <div className="flex min-h-screen">
      {/* Sidebar */}
      <nav
        onMouseEnter={() => setExpanded(true)}
        onMouseLeave={() => setExpanded(false)}
        className="fixed left-0 top-0 h-screen z-40 flex flex-col border-r transition-all duration-[400ms]"
        style={{
          width: expanded ? 220 : 64,
          background: 'var(--glass-bg)',
          borderColor: 'var(--glass-border)',
          backdropFilter: 'blur(24px)',
          transitionTimingFunction: 'cubic-bezier(0.23, 1, 0.32, 1)',
        }}
      >
        {/* Logo */}
        <div className="flex items-center justify-center h-16 border-b" style={{ borderColor: 'var(--glass-border)' }}>
          <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
            <path d="M14 2L26 8V20L14 26L2 20V8L14 2Z" stroke="var(--accent-primary)" strokeWidth="1.5" fill="none" />
            <path d="M14 10L20 13V19L14 22L8 19V13L14 10Z" fill="var(--accent-primary)" fillOpacity="0.2" stroke="var(--accent-primary)" strokeWidth="1" />
          </svg>
          {expanded && (
            <span className="ml-3 font-display font-bold text-sm tracking-wide" style={{ color: 'var(--accent-primary)' }}>
              PPC Intel
            </span>
          )}
        </div>

        {/* Nav items */}
        <div className="flex-1 py-4 space-y-0.5 px-2 overflow-y-auto">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon
            const isActive = active === item.id
            const isBottom = item.id === 'settings'
            return (
              <button
                key={item.id}
                onClick={() => setActive(item.id)}
                className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl transition-all duration-200"
                style={{
                  background: isActive ? 'rgba(79,142,255,0.08)' : 'transparent',
                  borderLeft: isActive ? '2px solid var(--accent-primary)' : '2px solid transparent',
                  color: isActive ? 'var(--accent-primary)' : 'var(--text-secondary)',
                  marginTop: isBottom ? 'auto' : undefined,
                }}
              >
                <Icon className="w-[18px] h-[18px] flex-shrink-0" />
                {expanded && (
                  <span className="text-sm font-body whitespace-nowrap">{item.label}</span>
                )}
              </button>
            )
          })}
        </div>

        {/* Settings pinned to bottom */}
        <div className="px-2 py-3 border-t" style={{ borderColor: 'var(--glass-border)' }}>
          <button
            onClick={() => setActive('settings')}
            className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl transition-all duration-200"
            style={{
              background: active === 'settings' ? 'rgba(79,142,255,0.08)' : 'transparent',
              borderLeft: active === 'settings' ? '2px solid var(--accent-primary)' : '2px solid transparent',
              color: active === 'settings' ? 'var(--accent-primary)' : 'var(--text-muted)',
            }}
          >
            <SettingsIcon className="w-[18px] h-[18px] flex-shrink-0" />
            {expanded && <span className="text-sm font-body">Settings</span>}
          </button>
        </div>
      </nav>

      {/* Main content */}
      <main
        className="flex-1 transition-all duration-[400ms]"
        style={{
          marginLeft: 64,
          transitionTimingFunction: 'cubic-bezier(0.23, 1, 0.32, 1)',
        }}
      >
        {/* Top bar */}
        <header className="sticky top-0 z-30 px-8 py-4 border-b"
                style={{ background: 'rgba(228,236,247,0.82)', borderColor: 'rgba(255,255,255,0.88)', backdropFilter: 'blur(20px)', WebkitBackdropFilter: 'blur(20px)' }}>
          <h1 className="font-display font-bold text-lg tracking-wide">
            {NAV_ITEMS.find(n => n.id === active)?.label || 'Dashboard'}
          </h1>
        </header>

        {/* Page content */}
        <div className="p-8" key={active}>
          <Page />
        </div>
      </main>
    </div>
  )
}
