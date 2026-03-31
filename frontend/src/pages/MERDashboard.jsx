/**
 * MER Dashboard — TripleWhale-style blended ROAS & attribution view.
 * Shows: MER, Blended ROAS, nCAC, channel breakdown, daily trend, anomaly alerts.
 */
import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend, PieChart, Pie, Cell
} from 'recharts'
import { RefreshCw, AlertTriangle, TrendingUp, DollarSign, Users, Zap, ShoppingBag } from 'lucide-react'

const API = '/api'
const COLORS = ['#4f8eff', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6']

function KPI({ label, value, sub, trend, icon: Icon, color, size = 'normal' }) {
  const up = trend > 0
  return (
    <div className="glass-card p-5">
      <div className="flex items-start justify-between mb-2">
        <span className="text-xs font-body" style={{ color: 'var(--text-muted)' }}>{label}</span>
        {Icon && <Icon className="w-4 h-4" style={{ color: color || 'var(--accent-primary)' }} />}
      </div>
      <div className={`font-display font-bold mb-1 ${size === 'large' ? 'text-3xl' : 'text-2xl'}`}
           style={{ color: color || 'var(--text-primary)' }}>
        {value ?? '—'}
      </div>
      <div className="flex items-center gap-2">
        {trend != null && (
          <span className="flex items-center gap-0.5 text-xs font-mono"
                style={{ color: up ? 'var(--accent-success)' : 'var(--accent-danger)' }}>
            {up ? '▲' : '▼'} {Math.abs(trend)}%
          </span>
        )}
        {sub && <span className="text-xs" style={{ color: 'var(--text-muted)' }}>{sub}</span>}
      </div>
    </div>
  )
}

function Alert({ alert }) {
  const color = alert.severity === 'high' ? 'var(--accent-danger)' : '#f59e0b'
  return (
    <div className="flex items-start gap-3 p-3 rounded-lg"
         style={{ background: `${color}11`, border: `1px solid ${color}33` }}>
      <AlertTriangle className="w-4 h-4 mt-0.5 flex-shrink-0" style={{ color }} />
      <div>
        <div className="text-xs font-semibold mb-0.5"
             style={{ color }}>{alert.type}</div>
        <div className="text-xs" style={{ color: 'var(--text-secondary)' }}>{alert.message}</div>
      </div>
    </div>
  )
}

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null
  return (
    <div className="glass-card p-3 text-xs font-body space-y-1" style={{ minWidth: 160 }}>
      <div className="font-semibold mb-1.5" style={{ color: 'var(--text-secondary)' }}>{label}</div>
      {payload.map((p, i) => (
        <div key={i} className="flex justify-between gap-4">
          <span style={{ color: p.color }}>{p.name}</span>
          <span className="font-mono" style={{ color: 'var(--text-primary)' }}>
            {p.name === 'MER' ? `${p.value}x` : `$${Number(p.value).toFixed(0)}`}
          </span>
        </div>
      ))}
    </div>
  )
}

export default function MERDashboard() {
  const [days, setDays] = useState(30)
  const [syncing, setSyncing] = useState(false)
  const [syncMsg, setSyncMsg] = useState(null)

  const { data: summary, refetch: refetchSummary } = useQuery({
    queryKey: ['mer-summary', days],
    queryFn: () => fetch(`${API}/mer/summary?days=${days}`).then(r => r.json()),
  })

  const { data: trendData } = useQuery({
    queryKey: ['mer-trend', days],
    queryFn: () => fetch(`${API}/mer/trend?days=${days}`).then(r => r.json()),
  })

  const { data: channels } = useQuery({
    queryKey: ['mer-channels', days],
    queryFn: () => fetch(`${API}/mer/channels?days=${days}`).then(r => r.json()),
  })

  const { data: anomalies } = useQuery({
    queryKey: ['mer-anomalies'],
    queryFn: () => fetch(`${API}/mer/anomalies`).then(r => r.json()),
    refetchInterval: 300_000,
  })

  const { data: attribution } = useQuery({
    queryKey: ['shopify-attribution'],
    queryFn: () => fetch(`${API}/shopify/attribution`).then(r => r.json()),
  })

  const syncAll = async () => {
    setSyncing(true)
    setSyncMsg(null)
    try {
      const res = await fetch(`${API}/mer/sync-all`, { method: 'POST' })
      const data = await res.json()
      setSyncMsg(data)
      refetchSummary()
    } catch (e) {
      setSyncMsg({ error: e.message })
    }
    setSyncing(false)
  }

  const s = summary || {}
  const trend = trendData?.trend || []
  const alerts = anomalies?.alerts || []
  const ch = channels?.channels || []
  const attr = attribution?.attribution || []

  const merColor = s.mer >= 3 ? 'var(--accent-success)' : s.mer >= 1.5 ? '#f59e0b' : 'var(--accent-danger)'

  // Pie chart data
  const pieData = ch.map(c => ({ name: c.channel, value: c.spend }))

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex gap-2">
          {[7, 14, 30, 60].map(d => (
            <button key={d} onClick={() => setDays(d)}
                    className="px-3 py-1.5 rounded-lg text-xs font-body transition-all"
                    style={{
                      background: days === d ? 'rgba(79,142,255,0.15)' : 'transparent',
                      color: days === d ? 'var(--accent-primary)' : 'var(--text-muted)',
                      border: `1px solid ${days === d ? 'rgba(79,142,255,0.4)' : 'var(--glass-border)'}`,
                    }}>
              {d}d
            </button>
          ))}
        </div>
        <button onClick={syncAll} disabled={syncing}
                className="flex items-center gap-2 px-4 py-1.5 rounded-lg text-xs font-body border
                           border-accent-primary/30 text-accent-primary hover:bg-accent-primary/10 disabled:opacity-50">
          <RefreshCw className={`w-3 h-3 ${syncing ? 'animate-spin' : ''}`} />
          {syncing ? 'Syncing…' : 'Sync All'}
        </button>
      </div>

      {syncMsg && (
        <div className="glass-card p-3 text-xs font-mono"
             style={{ color: syncMsg.error ? 'var(--accent-danger)' : 'var(--accent-success)' }}>
          {syncMsg.error ? `Error: ${syncMsg.error}` :
            `Facebook: ${syncMsg.facebook?.days_synced ?? syncMsg.facebook?.error ?? '—'} days | Shopify: ${syncMsg.shopify?.days_synced ?? syncMsg.shopify?.error ?? '—'} days`}
        </div>
      )}

      {/* Anomaly alerts — Sonar */}
      {alerts.length > 0 && (
        <div className="glass-card p-4 space-y-2 animate-in"
             style={{ borderColor: 'rgba(239,68,68,0.3)' }}>
          <div className="flex items-center gap-2 mb-2">
            <Zap className="w-4 h-4" style={{ color: 'var(--accent-danger)' }} />
            <span className="text-xs font-semibold" style={{ color: 'var(--accent-danger)' }}>
              SONAR — {alerts.length} Alert{alerts.length > 1 ? 's' : ''}
            </span>
          </div>
          {alerts.map((a, i) => <Alert key={i} alert={a} />)}
        </div>
      )}

      {/* Hero MER KPI */}
      <div className="glass-card p-6 animate-in"
           style={{ borderColor: `${merColor}44` }}>
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-body" style={{ color: 'var(--text-muted)' }}>
            MER — Marketing Efficiency Ratio
          </span>
          <span className="text-xs px-2 py-0.5 rounded font-mono"
                style={{ background: `${merColor}22`, color: merColor }}>
            {s.mer >= 3 ? 'HEALTHY' : s.mer >= 1.5 ? 'OK' : s.mer > 0 ? 'BELOW TARGET' : 'NO DATA'}
          </span>
        </div>
        <div className="font-display font-bold text-5xl mb-1" style={{ color: merColor }}>
          {s.mer ? `${s.mer}x` : '—'}
        </div>
        <div className="text-xs" style={{ color: 'var(--text-muted)' }}>
          Total Revenue ${(s.total_revenue || 0).toFixed(0)} ÷ Total Spend ${(s.total_spend || 0).toFixed(0)} across all channels
        </div>
      </div>

      {/* KPI Grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 animate-in" style={{ animationDelay: '40ms' }}>
        <KPI label="Total Spend" value={`$${(s.total_spend || 0).toFixed(0)}`}
             sub={`FB $${(s.fb_spend || 0).toFixed(0)} + AMZ $${(s.amazon_spend || 0).toFixed(0)}`}
             icon={DollarSign} color="var(--accent-danger)" />
        <KPI label="Total Revenue" value={`$${(s.total_revenue || 0).toFixed(0)}`}
             sub={`Shopify + Amazon`} icon={ShoppingBag} color="var(--accent-success)" />
        <KPI label="Facebook ROAS" value={s.fb_roas ? `${s.fb_roas}x` : '—'}
             sub="Shopify rev / FB spend" icon={TrendingUp}
             color={s.fb_roas >= 2 ? 'var(--accent-success)' : s.fb_roas > 0 ? '#f59e0b' : 'var(--text-muted)'} />
        <KPI label="nCAC" value={s.ncac ? `$${s.ncac.toFixed(2)}` : '—'}
             sub={`${s.new_customers || 0} new customers`} icon={Users} />
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4" style={{ animationDelay: '60ms' }}>
        <KPI label="Amazon ROAS" value={s.amazon_roas ? `${s.amazon_roas}x` : '—'}
             sub="Amazon PPC only" />
        <KPI label="Shopify Revenue" value={`$${(s.shopify_revenue || 0).toFixed(0)}`}
             sub={`${s.shopify_orders || 0} orders`} />
        <KPI label="Avg Order Value" value={s.avg_order_value ? `$${s.avg_order_value.toFixed(2)}` : '—'}
             sub="Shopify AOV" />
        <KPI label="Amazon Revenue" value={`$${(s.amazon_revenue || 0).toFixed(0)}`}
             sub="PPC attributed sales" />
      </div>

      {/* MER Trend Chart */}
      {trend.length > 0 && (
        <div className="glass-card p-5 animate-in" style={{ animationDelay: '80ms' }}>
          <h3 className="font-display text-sm font-semibold mb-4" style={{ color: 'var(--text-secondary)' }}>
            Daily MER + Spend vs Revenue
          </h3>
          <ResponsiveContainer width="100%" height={260}>
            <AreaChart data={trend} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
              <defs>
                <linearGradient id="revGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#10b981" stopOpacity={0.25} />
                  <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="spendGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#ef4444" stopOpacity={0.2} />
                  <stop offset="95%" stopColor="#ef4444" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
              <XAxis dataKey="date" tick={{ fontSize: 10, fill: 'var(--text-muted)' }}
                     tickFormatter={v => v?.slice(5)} />
              <YAxis yAxisId="left" tick={{ fontSize: 10, fill: 'var(--text-muted)' }}
                     tickFormatter={v => `$${v}`} />
              <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 10, fill: 'var(--text-muted)' }}
                     tickFormatter={v => `${v}x`} />
              <Tooltip content={<CustomTooltip />} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Area yAxisId="left" type="monotone" dataKey="total_revenue" name="Revenue"
                    stroke="#10b981" strokeWidth={2} fill="url(#revGrad)" dot={false} />
              <Area yAxisId="left" type="monotone" dataKey="total_spend" name="Spend"
                    stroke="#ef4444" strokeWidth={2} fill="url(#spendGrad)" dot={false} />
              <Area yAxisId="right" type="monotone" dataKey="mer" name="MER"
                    stroke="#4f8eff" strokeWidth={2} fill="none" dot={false} strokeDasharray="4 2" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}

      <div className="grid md:grid-cols-2 gap-4">
        {/* Channel breakdown */}
        {ch.length > 0 && (
          <div className="glass-card p-5 animate-in" style={{ animationDelay: '100ms' }}>
            <h3 className="font-display text-sm font-semibold mb-4" style={{ color: 'var(--text-secondary)' }}>
              Spend by Channel
            </h3>
            <div className="flex items-center gap-4">
              <ResponsiveContainer width={120} height={120}>
                <PieChart>
                  <Pie data={pieData} cx="50%" cy="50%" innerRadius={35} outerRadius={55}
                       dataKey="value" paddingAngle={3}>
                    {pieData.map((_, i) => (
                      <Cell key={i} fill={COLORS[i % COLORS.length]} />
                    ))}
                  </Pie>
                </PieChart>
              </ResponsiveContainer>
              <div className="flex-1 space-y-2">
                {ch.map((c, i) => (
                  <div key={i}>
                    <div className="flex justify-between text-xs mb-1">
                      <span className="flex items-center gap-2">
                        <span className="w-2 h-2 rounded-full" style={{ background: COLORS[i] }} />
                        <span style={{ color: 'var(--text-secondary)' }}>{c.channel}</span>
                      </span>
                      <span className="font-mono" style={{ color: 'var(--text-primary)' }}>
                        ${c.spend.toFixed(0)} ({c.spend_pct}%)
                      </span>
                    </div>
                    <div className="flex items-center gap-2 text-xs">
                      <span style={{ color: 'var(--text-muted)' }}>ROAS</span>
                      <span className="font-mono font-semibold"
                            style={{ color: c.roas >= 2 ? 'var(--accent-success)' : '#f59e0b' }}>
                        {c.roas}x
                      </span>
                      <span style={{ color: 'var(--text-muted)' }}>Rev ${c.revenue.toFixed(0)}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Shopify UTM Attribution */}
        {attr.length > 0 && (
          <div className="glass-card p-5 animate-in" style={{ animationDelay: '120ms' }}>
            <h3 className="font-display text-sm font-semibold mb-3" style={{ color: 'var(--text-secondary)' }}>
              Shopify Order Attribution (UTM)
            </h3>
            <div className="space-y-2">
              {attr.slice(0, 8).map((a, i) => (
                <div key={i} className="flex items-center justify-between text-xs">
                  <div>
                    <span className="font-semibold" style={{ color: 'var(--text-secondary)' }}>
                      {a.source}
                    </span>
                    <span className="ml-2" style={{ color: 'var(--text-muted)' }}>
                      / {a.medium} {a.campaign !== '(not set)' ? `/ ${a.campaign}` : ''}
                    </span>
                  </div>
                  <div className="flex items-center gap-3 font-mono">
                    <span style={{ color: 'var(--accent-success)' }}>${a.revenue.toFixed(0)}</span>
                    <span style={{ color: 'var(--text-muted)' }}>{a.orders} orders</span>
                    {a.new_customers > 0 && (
                      <span style={{ color: 'var(--accent-primary)' }}>{a.new_customers} new</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* No data guide */}
      {!s.total_spend && !s.total_revenue && (
        <div className="glass-card p-5 animate-in"
             style={{ borderColor: 'rgba(79,142,255,0.2)' }}>
          <h3 className="font-display text-sm font-semibold mb-3" style={{ color: 'var(--accent-primary)' }}>
            Setup Multi-Channel Attribution
          </h3>
          <div className="text-xs space-y-1.5 font-body" style={{ color: 'var(--text-muted)' }}>
            <p>Connect your channels in <strong style={{ color: 'var(--text-secondary)' }}>Settings</strong> to see blended ROAS:</p>
            <ul className="list-disc pl-4 space-y-1">
              <li><strong style={{ color: 'var(--text-secondary)' }}>Facebook Ads:</strong> App ID + Access Token + Ad Account ID → pulls daily spend automatically</li>
              <li><strong style={{ color: 'var(--text-secondary)' }}>Shopify:</strong> Shop domain + Admin API Token → pulls daily revenue + UTM attribution</li>
              <li><strong style={{ color: 'var(--text-secondary)' }}>Amazon PPC:</strong> Upload Search Term reports or connect Advertising API</li>
            </ul>
            <p className="mt-2">Then click <strong style={{ color: 'var(--text-secondary)' }}>Sync All</strong> above for your first pull.</p>
          </div>
        </div>
      )}
    </div>
  )
}
