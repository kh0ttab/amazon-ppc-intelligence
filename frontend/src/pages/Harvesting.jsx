import { useQuery } from '@tanstack/react-query'
import DataTable from '../components/DataTable'
import Tooltip from '../components/Tooltip'
import { Download, ArrowRight } from 'lucide-react'

const PROMOTE_COLS = [
  { key: 'search_term', label: 'Search Term' },
  { key: 'campaign', label: 'Campaign' },
  { key: 'clicks', label: 'Clicks', format: 'number', align: 'right' },
  { key: 'orders', label: 'Orders', format: 'number', align: 'right' },
  { key: 'sales', label: 'Revenue', format: 'currency', align: 'right' },
  { key: 'acos', label: 'ACoS', tooltip: 'ACoS', format: 'percent', align: 'right' },
  { key: 'suggested_bid', label: 'Bid', tooltip: 'CPC', format: 'currency', align: 'right' },
]

const NEGATE_COLS = [
  { key: 'search_term', label: 'Search Term' },
  { key: 'campaign', label: 'Campaign' },
  { key: 'clicks', label: 'Clicks', format: 'number', align: 'right' },
  { key: 'spend', label: 'Spend', tooltip: 'Spend', format: 'currency', align: 'right' },
]

export default function Harvesting() {
  const { data, isLoading } = useQuery({
    queryKey: ['harvest'],
    queryFn: () => fetch('/api/harvest').then(r => r.json()),
  })

  if (isLoading) return <div className="space-y-4">{[...Array(5)].map((_, i) => <div key={i} className="skeleton h-12 rounded-xl" />)}</div>

  const h = data || {}

  return (
    <div className="space-y-6">
      {/* Flow diagram */}
      <div className="glass-card p-6 animate-in">
        <Tooltip textKey="Harvesting">
          <h3 className="font-display text-sm font-semibold mb-4" style={{ color: 'var(--text-secondary)' }}>
            Harvesting Pipeline
          </h3>
        </Tooltip>
        <div className="flex items-center justify-center gap-4 text-sm font-mono">
          <div className="px-4 py-2 rounded-xl border" style={{ borderColor: 'var(--accent-warning)', color: 'var(--accent-warning)', background: 'rgba(255,181,71,0.06)' }}>
            AUTO Campaign
          </div>
          <ArrowRight className="w-5 h-5" style={{ color: 'var(--text-muted)' }} />
          <div className="px-4 py-2 rounded-xl border" style={{ borderColor: 'var(--accent-primary)', color: 'var(--text-secondary)', background: 'rgba(79,142,255,0.06)' }}>
            clicks ≥ {h.promote?.[0]?.clicks || '8'} & orders ≥ 1?
          </div>
          <ArrowRight className="w-5 h-5" style={{ color: 'var(--text-muted)' }} />
          <div className="px-4 py-2 rounded-xl border" style={{ borderColor: 'var(--accent-success)', color: 'var(--accent-success)', background: 'rgba(0,224,150,0.06)' }}>
            MANUAL EXACT
          </div>
        </div>
      </div>

      {/* Summary */}
      <div className="grid grid-cols-3 gap-4">
        <div className="glass-card p-4 animate-in" style={{ animationDelay: '60ms', borderTop: '2px solid var(--accent-success)' }}>
          <div className="text-xs uppercase tracking-widest" style={{ color: 'var(--text-muted)' }}>Promote to Exact</div>
          <div className="font-mono text-2xl mt-1" style={{ color: 'var(--accent-success)' }}>{h.promote_count || 0}</div>
        </div>
        <div className="glass-card p-4 animate-in" style={{ animationDelay: '120ms', borderTop: '2px solid var(--accent-danger)' }}>
          <div className="text-xs uppercase tracking-widest" style={{ color: 'var(--text-muted)' }}>Add Negative</div>
          <div className="font-mono text-2xl mt-1" style={{ color: 'var(--accent-danger)' }}>{h.negate_count || 0}</div>
        </div>
        <div className="glass-card p-4 animate-in" style={{ animationDelay: '180ms', borderTop: '2px solid var(--accent-primary)' }}>
          <div className="text-xs uppercase tracking-widest" style={{ color: 'var(--text-muted)' }}>Potential Savings</div>
          <div className="font-mono text-2xl mt-1" style={{ color: 'var(--text-data)' }}>${h.potential_savings?.toFixed(2) || '0.00'}</div>
        </div>
      </div>

      <a
        href="/api/harvest/export"
        className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-body transition-all
                   border border-accent-success/20 text-accent-success/80 hover:bg-accent-success/10 animate-in"
        style={{ animationDelay: '240ms' }}
      >
        <Download className="w-4 h-4" />
        Download Bulk Upload CSV
      </a>

      {h.promote?.length > 0 && (
        <div className="glass-card overflow-hidden animate-in" style={{ animationDelay: '300ms' }}>
          <div className="px-4 py-3 border-b" style={{ borderColor: 'var(--glass-border)' }}>
            <span className="font-display text-sm font-semibold" style={{ color: 'var(--accent-success)' }}>Promote to Manual Exact</span>
          </div>
          <DataTable columns={PROMOTE_COLS} data={h.promote} />
        </div>
      )}

      {h.negate?.length > 0 && (
        <div className="glass-card overflow-hidden animate-in" style={{ animationDelay: '360ms' }}>
          <div className="px-4 py-3 border-b" style={{ borderColor: 'var(--glass-border)' }}>
            <span className="font-display text-sm font-semibold" style={{ color: 'var(--accent-danger)' }}>Add as Negative Exact</span>
          </div>
          <DataTable columns={NEGATE_COLS} data={h.negate} />
        </div>
      )}
    </div>
  )
}
