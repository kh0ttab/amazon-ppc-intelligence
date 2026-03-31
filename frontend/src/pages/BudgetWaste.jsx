import { useQuery } from '@tanstack/react-query'
import DataTable from '../components/DataTable'
import Tooltip from '../components/Tooltip'
import { Download } from 'lucide-react'

const COLUMNS = [
  { key: 'search_term', label: 'Keyword' },
  { key: 'spend', label: 'Spend', tooltip: 'Spend', format: 'currency', align: 'right' },
  { key: 'clicks', label: 'Clicks', tooltip: 'Clicks', format: 'number', align: 'right' },
  { key: 'impressions', label: 'Impr', tooltip: 'Impressions', format: 'number', align: 'right' },
  { key: 'ctr', label: 'CTR', tooltip: 'CTR', format: 'percent', align: 'right' },
  { key: 'action', label: 'Action' },
  { key: 'reason', label: 'Reason', sortable: false },
]

export default function BudgetWaste() {
  const { data, isLoading } = useQuery({
    queryKey: ['waste'],
    queryFn: () => fetch('/api/waste').then(r => r.json()),
  })

  if (isLoading) return <div className="space-y-4">{[...Array(5)].map((_, i) => <div key={i} className="skeleton h-12 rounded-xl" />)}</div>

  const waste = data || {}

  return (
    <div className="space-y-6">
      <div className="glass-card p-6 animate-in" style={{ borderTop: '2px solid var(--accent-danger)' }}>
        <div className="flex items-center justify-between">
          <div>
            <Tooltip textKey="Spend">
              <span className="text-xs uppercase tracking-[0.12em] font-body" style={{ color: 'var(--text-secondary)' }}>
                Total Budget Waste
              </span>
            </Tooltip>
            <div className="font-mono font-light text-3xl mt-2" style={{ color: 'var(--accent-danger)' }}>
              ${waste.total_waste?.toFixed(2)}
            </div>
            <div className="text-xs font-mono mt-1" style={{ color: 'var(--text-muted)' }}>
              {waste.waste_pct?.toFixed(1)}% of ${waste.total_spend?.toFixed(2)} total spend
            </div>
          </div>
          <a
            href="/api/waste/export"
            className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-body transition-all
                       border border-accent-danger/20 text-accent-danger/80 hover:bg-accent-danger/10"
          >
            <Download className="w-4 h-4" />
            Export Negatives CSV
          </a>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="glass-card p-4 animate-in" style={{ animationDelay: '60ms' }}>
          <div className="text-xs uppercase tracking-widest mb-1" style={{ color: 'var(--text-muted)' }}>Zero-Order Waste</div>
          <div className="font-mono text-xl" style={{ color: 'var(--accent-danger)' }}>${waste.zero_order_waste?.toFixed(2)}</div>
        </div>
        <div className="glass-card p-4 animate-in" style={{ animationDelay: '120ms' }}>
          <div className="text-xs uppercase tracking-widest mb-1" style={{ color: 'var(--text-muted)' }}>High ACoS Excess</div>
          <div className="font-mono text-xl" style={{ color: 'var(--accent-warning)' }}>${waste.high_acos_waste?.toFixed(2)}</div>
        </div>
      </div>

      <div className="glass-card overflow-hidden animate-in" style={{ animationDelay: '180ms' }}>
        <DataTable columns={COLUMNS} data={waste.zero_orders || []} />
      </div>
    </div>
  )
}
