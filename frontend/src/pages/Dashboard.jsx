import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import MetricCard from '../components/MetricCard'
import StatusBadge from '../components/StatusBadge'
import Tooltip from '../components/Tooltip'
import { AlertTriangle, Upload, Calendar, ChevronDown } from 'lucide-react'

const fetchDashboard = (from, to) => {
  const params = new URLSearchParams()
  if (from) params.set('date_from', from)
  if (to) params.set('date_to', to)
  return fetch(`/api/dashboard?${params}`).then(r => r.json())
}
const fetchHealth = () => fetch('/api/health').then(r => r.json())
const fetchUploads = () => fetch('/api/uploads').then(r => r.json())

const REPORT_GUIDE = [
  { name: 'Sponsored Products Search Term Report', where: 'Advertising → Reports → Sponsored Products → Search Term', columns: 'Customer Search Term, Impressions, Clicks, Spend, Sales, Orders', purpose: 'PPC keyword analysis, waste detection, harvesting' },
  { name: 'Campaign Performance Report', where: 'Advertising → Campaign Manager → Reports', columns: 'Campaign Name, Ad Group, Targeting, Impressions, Clicks, Spend, Sales', purpose: 'Campaign-level metrics, cannibalization' },
  { name: 'Business Report (Detail Page)', where: 'Reports → Business Reports → Detail Page Sales and Traffic', columns: 'ASIN, Title, Sessions, Units Ordered, Ordered Product Sales', purpose: 'Organic vs PPC split, total orders, TACoS calculation' },
]

export default function Dashboard() {
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [showGuide, setShowGuide] = useState(false)
  const [selectedWeek, setSelectedWeek] = useState(null)

  const { data, isLoading } = useQuery({
    queryKey: ['dashboard', dateFrom, dateTo],
    queryFn: () => fetchDashboard(dateFrom, dateTo),
  })
  const { data: health } = useQuery({ queryKey: ['health'], queryFn: fetchHealth })
  const { data: uploads } = useQuery({ queryKey: ['uploads'], queryFn: fetchUploads })

  const handleWeekClick = (week) => {
    setSelectedWeek(week.week)
    setDateFrom(week.week_start)
    setDateTo(week.week_end)
  }

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="grid grid-cols-2 lg:grid-cols-4 xl:grid-cols-8 gap-4">
          {[...Array(8)].map((_, i) => <div key={i} className="skeleton h-28 rounded-2xl" />)}
        </div>
      </div>
    )
  }

  const kpis = data?.kpis || {}
  const winners = data?.top_winners || []
  const bleeders = data?.top_bleeders || []
  const status = data?.status_counts || {}
  const weeks = uploads?.weeks || []

  return (
    <div className="space-y-6">
      {/* Ollama warning */}
      {health && !health.ollama_online && (
        <div className="flex items-center gap-3 px-5 py-3 rounded-xl animate-in"
             style={{ background: 'rgba(255,181,71,0.08)', border: '1px solid rgba(255,181,71,0.2)' }}>
          <AlertTriangle className="w-4 h-4 flex-shrink-0" style={{ color: 'var(--accent-warning)' }} />
          <span className="text-sm" style={{ color: 'var(--accent-warning)' }}>
            Ollama не запущен — AI функции недоступны. Запустите: <code className="font-mono bg-white/5 px-1.5 py-0.5 rounded">ollama serve</code>
          </span>
        </div>
      )}

      {/* Upload guide toggle */}
      <div className="flex items-center justify-between">
        <button
          onClick={() => setShowGuide(!showGuide)}
          className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-body transition-all
                     border border-accent-primary/20 text-accent-primary/70 hover:bg-accent-primary/5"
        >
          <Upload className="w-4 h-4" />
          Какие отчёты загружать?
          <ChevronDown className={`w-3 h-3 transition-transform ${showGuide ? 'rotate-180' : ''}`} />
        </button>

        {/* Week selector */}
        {weeks.length > 0 && (
          <div className="flex items-center gap-2">
            <Calendar className="w-4 h-4" style={{ color: 'var(--text-muted)' }} />
            <div className="flex gap-1 overflow-x-auto max-w-[500px]">
              <button
                onClick={() => { setDateFrom(''); setDateTo(''); setSelectedWeek(null) }}
                className={`px-3 py-1 rounded-lg text-xs font-mono whitespace-nowrap transition-all border ${
                  !selectedWeek ? 'border-accent-primary/40 bg-accent-primary/10 text-accent-primary' : 'border-white/5 text-white/40 hover:border-white/10'
                }`}
              >
                All
              </button>
              {weeks.slice(0, 8).map((w) => (
                <button
                  key={w.week}
                  onClick={() => handleWeekClick(w)}
                  className={`px-3 py-1 rounded-lg text-xs font-mono whitespace-nowrap transition-all border ${
                    selectedWeek === w.week ? 'border-accent-primary/40 bg-accent-primary/10 text-accent-primary' : 'border-white/5 text-white/40 hover:border-white/10'
                  }`}
                >
                  {w.week}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Upload guide panel */}
      {showGuide && (
        <div className="glass-card p-5 space-y-4 animate-in">
          <h3 className="font-display text-sm font-semibold" style={{ color: 'var(--text-secondary)' }}>
            Amazon Seller Central Reports
          </h3>
          {REPORT_GUIDE.map((r, i) => (
            <div key={i} className="p-4 rounded-xl" style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.04)' }}>
              <div className="font-display text-sm font-semibold mb-1" style={{ color: 'var(--accent-primary)' }}>{r.name}</div>
              <div className="text-xs mb-1" style={{ color: 'var(--text-secondary)' }}>
                <span style={{ color: 'var(--text-muted)' }}>Путь:</span> {r.where}
              </div>
              <div className="text-xs mb-1" style={{ color: 'var(--text-secondary)' }}>
                <span style={{ color: 'var(--text-muted)' }}>Колонки:</span> {r.columns}
              </div>
              <div className="text-xs" style={{ color: 'var(--accent-success)', opacity: 0.7 }}>
                {r.purpose}
              </div>
            </div>
          ))}
          <div className="text-xs" style={{ color: 'var(--text-muted)' }}>
            Загрузите Business Report для расчёта органических продаж и TACoS.
            Без него — видны только PPC данные.
          </div>
        </div>
      )}

      {/* KPI Cards — now 8 cards with PPC/Organic orders */}
      <div className="grid grid-cols-2 lg:grid-cols-4 xl:grid-cols-8 gap-4">
        <MetricCard label="Ad Spend" value={kpis.total_spend} tooltipKey="Spend" variant="spend" delay={0} />
        <MetricCard label="PPC Revenue" value={kpis.ppc_sales || kpis.total_sales} tooltipKey="Sales" variant="revenue" delay={60} />
        <MetricCard label="ACoS" value={kpis.acos} prefix="" suffix="%" decimals={1} tooltipKey="ACoS" variant="acos" delay={120} />
        <MetricCard label="TACoS" value={kpis.tacos} prefix="" suffix="%" decimals={1} tooltipKey="TACoS" variant="tacos" delay={180} />
        <MetricCard label="PPC Orders" value={kpis.ppc_orders || kpis.total_orders} prefix="" suffix="" decimals={0} tooltipKey="Orders" variant="orders" delay={240} />
        <MetricCard label="Organic Orders" value={kpis.organic_orders || 0} prefix="" suffix="" decimals={0} tooltipKey="Organic" variant="roas" delay={300} />
        <MetricCard label="Total Revenue" value={kpis.total_revenue || kpis.total_sales} tooltipKey="Revenue" variant="revenue" delay={360} />
        <MetricCard label="ROAS" value={kpis.roas} prefix="" suffix="x" tooltipKey="ROAS" variant="roas" delay={420} />
      </div>

      {/* PPC vs Organic bar */}
      {kpis.total_revenue > 0 && (
        <div className="glass-card p-5 animate-in" style={{ animationDelay: '200ms' }}>
          <div className="flex items-center justify-between mb-3">
            <Tooltip textKey="Organic">
              <h3 className="font-display text-sm font-semibold" style={{ color: 'var(--text-secondary)' }}>
                PPC vs Organic Sales
              </h3>
            </Tooltip>
            <div className="flex gap-6 text-xs font-mono">
              <span style={{ color: 'var(--accent-primary)' }}>PPC: ${kpis.ppc_sales?.toFixed(0)} ({kpis.ppc_pct}%)</span>
              <span style={{ color: 'var(--accent-success)' }}>Organic: ${kpis.organic_sales?.toFixed(0)} ({kpis.organic_pct}%)</span>
            </div>
          </div>
          <div className="flex gap-0.5 h-4 rounded-full overflow-hidden" style={{ background: 'rgba(255,255,255,0.04)' }}>
            <div className="rounded-l-full transition-all duration-1000" style={{
              width: `${kpis.ppc_pct || 0}%`, background: 'var(--accent-primary)',
            }} />
            <div className="rounded-r-full transition-all duration-1000" style={{
              width: `${kpis.organic_pct || 0}%`, background: 'var(--accent-success)',
            }} />
          </div>
          <div className="flex justify-between mt-2 text-xs font-mono" style={{ color: 'var(--text-muted)' }}>
            <span>PPC Orders: {kpis.ppc_orders || 0}</span>
            <span>Organic Orders: {kpis.organic_orders || 0}</span>
            <span>Total: {kpis.total_orders || 0}</span>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        {/* Status Distribution */}
        <div className="glass-card p-5 animate-in" style={{ animationDelay: '250ms' }}>
          <h3 className="font-display text-sm font-semibold mb-4" style={{ color: 'var(--text-secondary)' }}>
            Keyword Distribution
          </h3>
          <div className="space-y-3">
            {Object.entries(status).map(([name, count]) => {
              const total = Object.values(status).reduce((a, b) => a + b, 0) || 1
              const pct = (count / total * 100)
              const colors = { WINNER: 'var(--accent-success)', BLEEDING: 'var(--accent-danger)', SLEEPING: 'rgba(255,255,255,0.15)', POTENTIAL: 'var(--accent-warning)', NEW: 'var(--accent-primary)' }
              return (
                <div key={name} className="flex items-center gap-3">
                  <StatusBadge status={name} />
                  <div className="flex-1 h-1.5 rounded-full" style={{ background: 'rgba(255,255,255,0.06)' }}>
                    <div className="h-full rounded-full transition-all duration-1000" style={{ width: `${pct}%`, background: colors[name] }} />
                  </div>
                  <span className="font-mono text-xs w-8 text-right" style={{ color: 'var(--text-data)' }}>{count}</span>
                </div>
              )
            })}
          </div>
        </div>

        {/* Top Winners */}
        <div className="glass-card p-5 animate-in" style={{ animationDelay: '310ms' }}>
          <h3 className="font-display text-sm font-semibold mb-4" style={{ color: 'var(--accent-success)' }}>Top Winners</h3>
          <div className="space-y-2">
            {winners.map((kw, i) => (
              <div key={i} className="flex items-center justify-between py-1.5 transition-colors hover:bg-white/[0.03] rounded px-2 -mx-2">
                <span className="text-sm truncate max-w-[180px] font-body">{kw.search_term}</span>
                <div className="flex items-center gap-3">
                  <span className="font-mono text-xs" style={{ color: 'var(--accent-success)' }}>${kw.sales?.toFixed(0)}</span>
                  <span className="font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>{kw.acos?.toFixed(0)}%</span>
                </div>
              </div>
            ))}
            {winners.length === 0 && <p className="text-xs" style={{ color: 'var(--text-muted)' }}>Загрузите данные</p>}
          </div>
        </div>

        {/* Top Bleeders */}
        <div className="glass-card p-5 animate-in" style={{ animationDelay: '370ms' }}>
          <h3 className="font-display text-sm font-semibold mb-4" style={{ color: 'var(--accent-danger)' }}>Top Bleeders</h3>
          <div className="space-y-2">
            {bleeders.map((kw, i) => (
              <div key={i} className="flex items-center justify-between py-1.5 transition-colors hover:bg-white/[0.03] rounded px-2 -mx-2">
                <span className="text-sm truncate max-w-[180px] font-body">{kw.search_term}</span>
                <div className="flex items-center gap-3">
                  <span className="font-mono text-xs" style={{ color: 'var(--accent-danger)' }}>-${kw.spend?.toFixed(0)}</span>
                  <span className="font-mono text-xs" style={{ color: 'var(--text-muted)' }}>{kw.orders?.toFixed(0)} ord</span>
                </div>
              </div>
            ))}
            {bleeders.length === 0 && <p className="text-xs" style={{ color: 'var(--text-muted)' }}>Загрузите данные</p>}
          </div>
        </div>
      </div>

      {/* Upload history */}
      {uploads?.uploads?.length > 0 && (
        <div className="glass-card p-5 animate-in" style={{ animationDelay: '430ms' }}>
          <h3 className="font-display text-sm font-semibold mb-3" style={{ color: 'var(--text-secondary)' }}>
            Loaded Reports
          </h3>
          <div className="space-y-1">
            {uploads.uploads.map((u, i) => (
              <div key={i} className="flex items-center justify-between py-1.5 text-xs">
                <span className="font-body" style={{ color: 'var(--text-primary)' }}>{u.filename}</span>
                <div className="flex items-center gap-4">
                  <span className="font-mono" style={{ color: 'var(--accent-primary)' }}>{u.report_type}</span>
                  <span className="font-mono" style={{ color: 'var(--text-data)' }}>{u.rows_count} rows</span>
                  {u.date_start && (
                    <span className="font-mono" style={{ color: 'var(--text-muted)' }}>
                      {u.date_start} → {u.date_end}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
