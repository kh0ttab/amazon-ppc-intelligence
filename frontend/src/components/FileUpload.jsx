import { useState, useCallback } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Upload, CheckCircle, XCircle } from 'lucide-react'

export default function FileUpload({ onUpload }) {
  const [dragging, setDragging] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [results, setResults] = useState([])
  const qc = useQueryClient()

  const handleFile = useCallback(async (file) => {
    setUploading(true)
    const form = new FormData()
    form.append('file', file)
    try {
      const res = await fetch('/api/upload', { method: 'POST', body: form })
      const data = await res.json()
      setResults(prev => [{ ...data, _file: file.name, _ok: !data.error }, ...prev])
      // Invalidate all data queries so every page refetches
      qc.invalidateQueries({ queryKey: ['dashboard'] })
      qc.invalidateQueries({ queryKey: ['keywords'] })
      qc.invalidateQueries({ queryKey: ['waste'] })
      qc.invalidateQueries({ queryKey: ['harvest'] })
      qc.invalidateQueries({ queryKey: ['uploads'] })
      qc.invalidateQueries({ queryKey: ['health'] })
      if (onUpload) onUpload(data)
    } catch (e) {
      setResults(prev => [{ error: e.message, _file: file.name, _ok: false }, ...prev])
    }
    setUploading(false)
  }, [onUpload, qc])

  const handleFiles = useCallback((files) => {
    Array.from(files).forEach(f => handleFile(f))
  }, [handleFile])

  const onDrop = (e) => {
    e.preventDefault()
    setDragging(false)
    handleFiles(e.dataTransfer.files)
  }

  return (
    <div className="animate-in space-y-3">
      <label
        onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={`flex flex-col items-center justify-center gap-3 p-8 rounded-2xl cursor-pointer
                     transition-all duration-300 border ${
                       dragging
                         ? 'border-solid border-accent-primary/50 bg-accent-primary/[0.06] shadow-[0_0_40px_rgba(79,142,255,0.15)]'
                         : 'border-dashed border-accent-primary/20 hover:border-accent-primary/40 hover:bg-white/[0.02]'
                     }`}
      >
        <Upload className="w-8 h-8" style={{ color: 'var(--accent-primary)', opacity: 0.5 }} />
        <span className="text-sm font-body" style={{ color: 'var(--text-secondary)' }}>
          {uploading ? 'Загрузка...' : 'Перетащите отчет Amazon (CSV / XLSX)'}
        </span>
        <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
          Search Term Report, Campaign Report, Business Report — можно несколько сразу
        </span>
        <input type="file" accept=".csv,.txt,.tsv,.xlsx,.xls" onChange={(e) => handleFiles(e.target.files)} className="hidden" multiple />
      </label>

      {/* Upload results */}
      {results.map((r, i) => (
        <div key={i} className={`flex items-center gap-3 p-3 rounded-xl text-sm font-mono ${
          r._ok ? '' : ''
        }`} style={{
          background: r._ok ? 'rgba(0,224,150,0.08)' : 'rgba(255,77,106,0.08)',
          border: `1px solid ${r._ok ? 'rgba(0,224,150,0.2)' : 'rgba(255,77,106,0.2)'}`,
        }}>
          {r._ok
            ? <CheckCircle className="w-4 h-4 flex-shrink-0" style={{ color: 'var(--accent-success)' }} />
            : <XCircle className="w-4 h-4 flex-shrink-0" style={{ color: 'var(--accent-danger)' }} />
          }
          <span style={{ color: r._ok ? 'var(--accent-success)' : 'var(--accent-danger)' }}>
            {r._ok
              ? `${r.type_label || r.type || 'report'} — ${r.rows || 0} rows loaded from ${r.filename || r._file}`
              : `Error: ${r.error}`
            }
          </span>
          {r.date_range && (
            <span style={{ color: 'var(--text-muted)' }}>
              ({r.date_range.start} → {r.date_range.end})
            </span>
          )}
        </div>
      ))}
    </div>
  )
}
