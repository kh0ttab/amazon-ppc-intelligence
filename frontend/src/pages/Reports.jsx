import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { FileText } from 'lucide-react'

const REPORT_TYPES = [
  { id: 'weekly', label: 'Weekly Performance', desc: 'KPIs, winners, bleeders, sales split' },
  { id: 'audit', label: 'Keyword Audit', desc: 'Full keyword scoring and status report' },
  { id: 'budget', label: 'Budget Optimization', desc: 'Waste detection and reallocation' },
]

export default function Reports() {
  const [selected, setSelected] = useState('weekly')
  const [generate, setGenerate] = useState(false)

  const { data, isLoading } = useQuery({
    queryKey: ['report', selected],
    queryFn: () => fetch(`/api/reports/generate?report_type=${selected}`).then(r => r.json()),
    enabled: generate,
  })

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-3 gap-4">
        {REPORT_TYPES.map((rt, i) => (
          <button
            key={rt.id}
            onClick={() => { setSelected(rt.id); setGenerate(false) }}
            className={`glass-card p-5 text-left transition-all animate-in ${
              selected === rt.id ? 'border-accent-primary/30' : ''
            }`}
            style={{ animationDelay: `${i * 60}ms` }}
          >
            <div className="font-display text-sm font-semibold mb-1">{rt.label}</div>
            <div className="text-xs" style={{ color: 'var(--text-muted)' }}>{rt.desc}</div>
          </button>
        ))}
      </div>

      <button
        onClick={() => setGenerate(true)}
        className="flex items-center gap-2 px-6 py-3 rounded-xl text-sm font-body transition-all
                   border border-accent-primary/30 text-accent-primary hover:bg-accent-primary/10
                   active:scale-[0.97]"
      >
        <FileText className="w-4 h-4" />
        Generate Report
      </button>

      {isLoading && <div className="skeleton h-48 rounded-2xl" />}

      {data && !isLoading && (
        <div className="glass-card p-6 animate-in space-y-4">
          <div className="flex justify-between items-center">
            <h3 className="font-display font-semibold">{REPORT_TYPES.find(r => r.id === selected)?.label}</h3>
            <span className="text-xs font-mono" style={{ color: 'var(--text-muted)' }}>{data.generated_at}</span>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {data.kpis && Object.entries({
              Spend: `$${data.kpis.total_spend}`,
              Revenue: `$${data.kpis.total_sales}`,
              ACoS: `${data.kpis.acos}%`,
              ROAS: `${data.kpis.roas}x`,
            }).map(([k, v]) => (
              <div key={k} className="p-3 rounded-xl" style={{ background: 'rgba(255,255,255,0.02)' }}>
                <div className="text-xs uppercase tracking-widest" style={{ color: 'var(--text-muted)' }}>{k}</div>
                <div className="font-mono text-lg mt-1" style={{ color: 'var(--text-data)' }}>{v}</div>
              </div>
            ))}
          </div>

          {data.status_counts && (
            <div className="flex gap-4">
              {Object.entries(data.status_counts).map(([status, count]) => (
                <span key={status} className={`badge-${status.toLowerCase()} px-2.5 py-0.5 rounded-full text-xs font-mono`}>
                  {status}: {count}
                </span>
              ))}
            </div>
          )}

          {data.waste && (
            <div className="p-4 rounded-xl" style={{ background: 'rgba(255,77,106,0.05)', border: '1px solid rgba(255,77,106,0.15)' }}>
              <span className="text-sm" style={{ color: 'var(--accent-danger)' }}>
                Budget Waste: ${data.waste.total_waste} ({data.waste.waste_pct}%) — {data.waste.zero_order_count} zero-order keywords
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
