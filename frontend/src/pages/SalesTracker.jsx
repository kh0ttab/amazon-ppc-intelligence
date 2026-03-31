import { useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend
} from 'recharts'
import { TrendingUp, TrendingDown, Package, DollarSign, RefreshCw, Calendar } from 'lucide-react'

const API = '/api'

function MetricCard({ label, value, sub, trend, icon: Icon, color }) {
  const up = trend > 0
  return (
    <div className="glass-card p-5">
      <div className="flex items-start justify-between mb-3">
        <span className="text-xs font-body" style={{ color: 'var(--text-muted)' }}>{label}</span>
        {Icon && <Icon className="w-4 h-4" style={{ color: color || 'var(--accent-primary)' }} />}
      </div>
      <div className="font-display font-bold text-2xl mb-1" style={{ color: 'var(--text-primary)' }}>
        {value ?? '—'}
      </div>
      <div className="flex items-center gap-2">
        {trend != null && (
          <span className="flex items-center gap-1 text-xs font-mono"
                style={{ color: up ? 'var(--accent-success)' : 'var(--accent-danger)' }}>
            {up ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
            {Math.abs(trend)}%
          </span>
        )}
        {sub && <span className="text-xs" style={{ color: 'var(--text-muted)' }}>{sub}</span>}
      </div>
    </div>
  )
}

const CUSTOM_TOOLTIP = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null
  return (
    <div className="glass-card p-3 text-xs font-body space-y-1" style={{ minWidth: 140 }}>
      <div className="font-semibold mb-1" style={{ color: 'var(--text-secondary)' }}>{label}</div>
      {payload.map((p, i) => (
        <div key={i} className="flex justify-between gap-4">
          <span style={{ color: p.color }}>{p.name}</span>
          <span className="font-mono" style={{ color: 'var(--text-primary)' }}>
            {typeof p.value === 'number' && p.name.toLowerCase().includes('revenue')
              ? `$${p.value.toFixed(2)}`
              : p.value}
          </span>
        </div>
      ))}
    </div>
  )
}

export default function SalesTracker() {
  const [view, setView] = useState('daily')  // 'daily' | 'weekly'
  const [syncing, setSyncing] = useState(false)
  const [syncResult, setSyncResult] = useState(null)

  const { data: velocity, refetch: refetchVelocity } = useQuery({
    queryKey: ['sales-velocity'],
    queryFn: () => fetch(`${API}/sales/velocity`).then(r => r.json()),
    refetchInterval: 60_000,
  })

  const { data: daily, refetch: refetchDaily } = useQuery({
    queryKey: ['sales-daily'],
    queryFn: () => fetch(`${API}/sales/daily?days=30`).then(r => r.json()),
    enabled: view === 'daily',
  })

  const { data: weekly, refetch: refetchWeekly } = useQuery({
    queryKey: ['sales-weekly'],
    queryFn: () => fetch(`${API}/sales/weekly?weeks=12`).then(r => r.json()),
    enabled: view === 'weekly',
  })

  const { data: topAsins } = useQuery({
    queryKey: ['sales-top-asins'],
    queryFn: () => fetch(`${API}/sales/top-asins?days=30`).then(r => r.json()),
  })

  const handleSync = async () => {
    setSyncing(true)
    setSyncResult(null)
    try {
      const res = await fetch(`${API}/sales/sync`, { method: 'POST' })
      const data = await res.json()
      setSyncResult(data)
      refetchVelocity()
      refetchDaily()
      refetchWeekly()
    } catch (e) {
      setSyncResult({ error: e.message })
    }
    setSyncing(false)
  }

  const v = velocity || {}
  const chartData = view === 'daily'
    ? (daily?.daily || []).slice().reverse().map(d => ({
        date: d.date?.slice(5),  // MM-DD
        'Units Sold': d.units || 0,
        'Revenue': d.revenue || 0,
      }))
    : (weekly?.weekly || []).slice().reverse().map(w => ({
        date: `${w.week_start?.slice(5)} – ${w.week_end?.slice(5)}`,
        'Units Sold': w.units || 0,
        'Revenue': w.revenue || 0,
      }))

  return (
    <div className="space-y-6">
      {/* Header row */}
      <div className="flex items-center justify-between">
        <div className="flex gap-2">
          {['daily', 'weekly'].map(mode => (
            <button
              key={mode}
              onClick={() => setView(mode)}
              className="px-4 py-1.5 rounded-lg text-xs font-body capitalize transition-all"
              style={{
                background: view === mode ? 'rgba(79,142,255,0.15)' : 'transparent',
                color: view === mode ? 'var(--accent-primary)' : 'var(--text-muted)',
                border: `1px solid ${view === mode ? 'rgba(79,142,255,0.4)' : 'var(--glass-border)'}`,
              }}
            >
              {mode}
            </button>
          ))}
        </div>
        <button
          onClick={handleSync}
          disabled={syncing}
          className="flex items-center gap-2 px-4 py-1.5 rounded-lg text-xs font-body border transition-all
                     border-accent-primary/30 text-accent-primary hover:bg-accent-primary/10
                     disabled:opacity-50"
        >
          <RefreshCw className={`w-3 h-3 ${syncing ? 'animate-spin' : ''}`} />
          {syncing ? 'Syncing…' : 'Sync SP-API'}
        </button>
      </div>

      {syncResult && (
        <div className="glass-card p-3 text-xs font-mono"
             style={{ color: syncResult.error ? 'var(--accent-danger)' : 'var(--accent-success)' }}>
          {syncResult.error
            ? `Sync error: ${syncResult.error}`
            : `Synced ${syncResult.days_synced ?? syncResult.rows_synced ?? 0} records from ${syncResult.source}`}
        </div>
      )}

      {/* Velocity KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 animate-in">
        <MetricCard
          label="Units Today"
          value={v.today_units ?? '—'}
          sub="vs yesterday"
          trend={v.today_vs_yesterday_pct}
          icon={Package}
        />
        <MetricCard
          label="Units This Week"
          value={v.this_week_units ?? '—'}
          sub="vs last week"
          trend={v.week_over_week_pct}
          icon={Calendar}
        />
        <MetricCard
          label="Revenue This Week"
          value={v.week_revenue != null ? `$${v.week_revenue.toFixed(2)}` : '—'}
          sub="7 days"
          icon={DollarSign}
          color="var(--accent-success)"
        />
        <MetricCard
          label="Avg Daily Units (30d)"
          value={v.avg_daily_units_30d ?? '—'}
          sub={`$${(v.avg_daily_revenue_30d || 0).toFixed(0)}/day avg`}
          icon={TrendingUp}
        />
      </div>

      {/* Chart */}
      <div className="glass-card p-5 animate-in" style={{ animationDelay: '60ms' }}>
        <h3 className="font-display text-sm font-semibold mb-4" style={{ color: 'var(--text-secondary)' }}>
          {view === 'daily' ? 'Daily Units Sold (30 days)' : 'Weekly Units Sold (12 weeks)'}
        </h3>
        {chartData.length > 0 ? (
          <ResponsiveContainer width="100%" height={260}>
            <AreaChart data={chartData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
              <defs>
                <linearGradient id="unitsGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="var(--accent-primary)" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="var(--accent-primary)" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
              <XAxis dataKey="date" tick={{ fontSize: 10, fill: 'var(--text-muted)' }} />
              <YAxis tick={{ fontSize: 10, fill: 'var(--text-muted)' }} />
              <Tooltip content={<CUSTOM_TOOLTIP />} />
              <Area
                type="monotone"
                dataKey="Units Sold"
                stroke="var(--accent-primary)"
                strokeWidth={2}
                fill="url(#unitsGrad)"
                dot={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <div className="flex items-center justify-center h-40 text-sm"
               style={{ color: 'var(--text-muted)' }}>
            No sales data yet. Upload a Business Report or connect SP-API.
          </div>
        )}
      </div>

      {/* Revenue chart */}
      {chartData.length > 0 && (
        <div className="glass-card p-5 animate-in" style={{ animationDelay: '100ms' }}>
          <h3 className="font-display text-sm font-semibold mb-4" style={{ color: 'var(--text-secondary)' }}>
            {view === 'daily' ? 'Daily Revenue (30 days)' : 'Weekly Revenue (12 weeks)'}
          </h3>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={chartData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
              <XAxis dataKey="date" tick={{ fontSize: 10, fill: 'var(--text-muted)' }} />
              <YAxis tick={{ fontSize: 10, fill: 'var(--text-muted)' }}
                     tickFormatter={v => `$${v}`} />
              <Tooltip content={<CUSTOM_TOOLTIP />} />
              <Bar dataKey="Revenue" fill="var(--accent-success)" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Top ASINs table */}
      {topAsins?.asins?.length > 0 && (
        <div className="glass-card overflow-hidden animate-in" style={{ animationDelay: '140ms' }}>
          <div className="px-5 py-3 border-b" style={{ borderColor: 'var(--glass-border)' }}>
            <span className="font-display text-sm font-semibold" style={{ color: 'var(--text-secondary)' }}>
              Top ASINs — Last 30 Days
            </span>
          </div>
          <table className="w-full text-xs font-body">
            <thead>
              <tr style={{ borderBottom: '1px solid var(--glass-border)' }}>
                {['ASIN', 'Total Units', 'Revenue', 'Avg Daily', 'Days Tracked'].map(h => (
                  <th key={h} className="px-4 py-2.5 text-left font-semibold"
                      style={{ color: 'var(--text-muted)' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {topAsins.asins.map((a, i) => (
                <tr key={i} style={{ borderBottom: '1px solid rgba(255,255,255,0.03)' }}
                    className="hover:bg-white/[0.02] transition-colors">
                  <td className="px-4 py-2.5 font-mono" style={{ color: 'var(--accent-primary)' }}>
                    {a.asin}
                  </td>
                  <td className="px-4 py-2.5 font-semibold" style={{ color: 'var(--text-primary)' }}>
                    {a.total_units?.toLocaleString()}
                  </td>
                  <td className="px-4 py-2.5" style={{ color: 'var(--accent-success)' }}>
                    ${(a.total_revenue || 0).toFixed(2)}
                  </td>
                  <td className="px-4 py-2.5" style={{ color: 'var(--text-secondary)' }}>
                    {a.avg_daily_units} / day
                  </td>
                  <td className="px-4 py-2.5" style={{ color: 'var(--text-muted)' }}>
                    {a.days_with_data}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* SP-API Setup Guide */}
      <div className="glass-card p-5 animate-in" style={{ animationDelay: '180ms', borderColor: 'rgba(79,142,255,0.2)' }}>
        <h3 className="font-display text-sm font-semibold mb-3" style={{ color: 'var(--accent-primary)' }}>
          Automated Sales Tracking Setup
        </h3>
        <div className="text-xs font-body space-y-2" style={{ color: 'var(--text-muted)' }}>
          <p>Connect <strong style={{ color: 'var(--text-secondary)' }}>Amazon SP-API</strong> for automatic daily/weekly sales tracking.
             Data syncs every day at 6AM UTC.</p>
          <ol className="list-decimal list-inside space-y-1 pl-2">
            <li>Go to <strong style={{ color: 'var(--text-secondary)' }}>developer.amazonservices.com</strong> → Register as developer</li>
            <li>Create a <strong style={{ color: 'var(--text-secondary)' }}>Self-Authorized App</strong> (for your own store)</li>
            <li>Note your <strong style={{ color: 'var(--text-secondary)' }}>Client ID, Client Secret, Refresh Token, Seller ID</strong></li>
            <li>Add credentials in <strong style={{ color: 'var(--text-secondary)' }}>Settings → SP-API</strong></li>
            <li>Click <strong style={{ color: 'var(--text-secondary)' }}>Sync SP-API</strong> above for first pull</li>
          </ol>
          <p className="mt-2">Until connected, upload your <strong style={{ color: 'var(--text-secondary)' }}>Business Report</strong> CSV
             from Seller Central → Reports → Business Reports.</p>
        </div>
      </div>
    </div>
  )
}
