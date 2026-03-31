import { useState } from 'react'
import { InfoIcon } from './Tooltip'
import StatusBadge from './StatusBadge'

export default function DataTable({ columns, data, onSort }) {
  const [sortCol, setSortCol] = useState(null)
  const [sortDir, setSortDir] = useState('desc')

  const handleSort = (col) => {
    const newDir = sortCol === col.key && sortDir === 'desc' ? 'asc' : 'desc'
    setSortCol(col.key)
    setSortDir(newDir)
    if (onSort) onSort(col.key, newDir)
  }

  const sorted = [...data]
  if (sortCol && !onSort) {
    sorted.sort((a, b) => {
      const av = a[sortCol] ?? 0
      const bv = b[sortCol] ?? 0
      const cmp = typeof av === 'number' ? av - bv : String(av).localeCompare(String(bv))
      return sortDir === 'desc' ? -cmp : cmp
    })
  }

  return (
    <div className="overflow-x-auto animate-in">
      <table className="w-full">
        <thead>
          <tr>
            {columns.map((col) => (
              <th
                key={col.key}
                onClick={() => col.sortable !== false && handleSort(col)}
                className={`px-3 py-2.5 text-left font-mono text-[0.65rem] uppercase tracking-[0.1em] cursor-pointer
                            select-none transition-colors hover:text-white/60 ${col.align === 'right' ? 'text-right' : ''}`}
                style={{ color: 'var(--text-muted)' }}
              >
                <span className="inline-flex items-center gap-1.5">
                  {col.label}
                  {col.tooltip && <InfoIcon textKey={col.tooltip} />}
                  {sortCol === col.key && (
                    <span className="text-accent-primary text-[10px]">{sortDir === 'desc' ? '▼' : '▲'}</span>
                  )}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((row, i) => (
            <tr
              key={i}
              className="transition-colors duration-150 hover:bg-[rgba(79,142,255,0.05)]"
              style={{
                borderBottom: '1px solid rgba(255,255,255,0.04)',
                animation: `fadeInUp 0.3s cubic-bezier(0.23,1,0.32,1) ${i * 20}ms both`,
              }}
            >
              {columns.map((col) => {
                const val = row[col.key]
                let content = val

                if (col.key === 'status') {
                  content = <StatusBadge status={val} />
                } else if (col.format === 'currency') {
                  content = <span className="font-mono" style={{ color: 'var(--text-data)' }}>${Number(val).toFixed(2)}</span>
                } else if (col.format === 'percent') {
                  content = <span className="font-mono" style={{ color: 'var(--text-data)' }}>{Number(val).toFixed(1)}%</span>
                } else if (col.format === 'number') {
                  content = <span className="font-mono" style={{ color: 'var(--text-data)' }}>{Number(val).toLocaleString()}</span>
                } else if (col.format === 'roas') {
                  content = <span className="font-mono" style={{ color: 'var(--text-data)' }}>{Number(val).toFixed(2)}x</span>
                }

                return (
                  <td key={col.key} className={`px-3 py-2.5 text-sm font-body ${col.align === 'right' ? 'text-right' : ''}`}>
                    {content}
                  </td>
                )
              })}
            </tr>
          ))}
          {sorted.length === 0 && (
            <tr>
              <td colSpan={columns.length} className="px-3 py-12 text-center text-sm" style={{ color: 'var(--text-muted)' }}>
                Нет данных. Загрузите отчет через меню.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  )
}
