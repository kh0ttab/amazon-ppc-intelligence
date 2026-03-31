import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import FileUpload from '../components/FileUpload'
import DataTable from '../components/DataTable'

const COLUMNS = [
  { key: 'search_term', label: 'Keyword', tooltip: 'Clicks' },
  { key: 'impressions', label: 'Impr', tooltip: 'Impressions', format: 'number', align: 'right' },
  { key: 'clicks', label: 'Clicks', tooltip: 'Clicks', format: 'number', align: 'right' },
  { key: 'spend', label: 'Spend', tooltip: 'Spend', format: 'currency', align: 'right' },
  { key: 'orders', label: 'Orders', tooltip: 'Orders', format: 'number', align: 'right' },
  { key: 'sales', label: 'Revenue', tooltip: 'Sales', format: 'currency', align: 'right' },
  { key: 'acos', label: 'ACoS', tooltip: 'ACoS', format: 'percent', align: 'right' },
  { key: 'roas', label: 'ROAS', tooltip: 'ROAS', format: 'roas', align: 'right' },
  { key: 'cpc', label: 'CPC', tooltip: 'CPC', format: 'currency', align: 'right' },
  { key: 'cvr', label: 'CVR', tooltip: 'CVR', format: 'percent', align: 'right' },
  { key: 'status', label: 'Status', tooltip: 'WINNER' },
]

export default function Keywords() {
  const [statusFilter, setStatusFilter] = useState('')
  const [sortBy, setSortBy] = useState('spend')
  const [sortDir, setSortDir] = useState('desc')

  const params = new URLSearchParams({ sort_by: sortBy, sort_dir: sortDir, limit: '300' })
  if (statusFilter) params.set('status', statusFilter)

  const { data, isLoading } = useQuery({
    queryKey: ['keywords', statusFilter, sortBy, sortDir],
    queryFn: () => fetch(`/api/keywords?${params}`).then(r => r.json()),
  })

  const handleSort = (key, dir) => { setSortBy(key); setSortDir(dir) }

  return (
    <div className="space-y-6">
      <FileUpload />

      <div className="flex items-center gap-3 flex-wrap">
        {['', 'WINNER', 'BLEEDING', 'SLEEPING', 'POTENTIAL', 'NEW'].map((s) => (
          <button
            key={s}
            onClick={() => setStatusFilter(s)}
            className={`px-3 py-1.5 rounded-full text-xs font-mono transition-all border ${
              statusFilter === s
                ? 'border-accent-primary/40 bg-accent-primary/10 text-accent-primary'
                : 'border-white/5 text-white/40 hover:border-white/10 hover:text-white/60'
            }`}
            style={{ fontFamily: "'DM Mono', monospace" }}
          >
            {s || 'ALL'}
          </button>
        ))}
        <span className="ml-auto text-xs font-mono" style={{ color: 'var(--text-muted)' }}>
          {data?.total ?? 0} keywords
        </span>
      </div>

      {isLoading ? (
        <div className="space-y-2">
          {[...Array(8)].map((_, i) => <div key={i} className="skeleton h-10 rounded-lg" />)}
        </div>
      ) : (
        <div className="glass-card overflow-hidden">
          <DataTable columns={COLUMNS} data={data?.keywords || []} onSort={handleSort} />
        </div>
      )}
    </div>
  )
}
