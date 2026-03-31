/**
 * Creative Cockpit — Facebook ad creative performance.
 * Shows each ad's spend, ROAS, CPA, CTR with thumbnail previews.
 * Inspired by TripleWhale's Creative Cockpit feature.
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { RefreshCw, TrendingUp, Eye, MousePointer, DollarSign, ShoppingCart } from 'lucide-react'

const API = '/api'

function fmt(v, type) {
  if (v == null || v === 0) return '—'
  if (type === 'currency') return `$${Number(v).toFixed(2)}`
  if (type === 'pct') return `${Number(v).toFixed(2)}%`
  if (type === 'roas') return `${Number(v).toFixed(2)}x`
  if (type === 'int') return Number(v).toLocaleString()
  return v
}

function CreativeCard({ creative, rank }) {
  const roasColor = creative.roas >= 2 ? 'var(--accent-success)'
                  : creative.roas >= 1 ? '#f59e0b'
                  : 'var(--accent-danger)'

  return (
    <div className="glass-card overflow-hidden animate-in hover:scale-[1.01] transition-transform duration-200">
      {/* Creative thumbnail */}
      <div className="relative bg-black/30 h-40 flex items-center justify-center overflow-hidden">
        {creative.thumbnail_url || creative.image_url ? (
          <img
            src={creative.thumbnail_url || creative.image_url}
            alt={creative.ad_name || 'Ad Creative'}
            className="w-full h-full object-cover opacity-80"
            onError={e => { e.target.style.display = 'none' }}
          />
        ) : (
          <div className="flex flex-col items-center gap-2" style={{ color: 'var(--text-muted)' }}>
            <Eye className="w-8 h-8 opacity-30" />
            <span className="text-xs">No preview</span>
          </div>
        )}
        {/* Rank badge */}
        <div className="absolute top-2 left-2 w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold"
             style={{ background: rank <= 3 ? 'var(--accent-primary)' : 'rgba(0,0,0,0.6)',
                      color: 'white' }}>
          {rank}
        </div>
        {/* ROAS badge */}
        <div className="absolute top-2 right-2 px-2 py-0.5 rounded font-mono text-xs font-bold"
             style={{ background: `${roasColor}22`, color: roasColor, border: `1px solid ${roasColor}44` }}>
          {fmt(creative.roas, 'roas')}
        </div>
      </div>

      <div className="p-4 space-y-3">
        {/* Ad name */}
        <div>
          <div className="text-xs font-semibold truncate" style={{ color: 'var(--text-primary)' }}>
            {creative.ad_name || `Ad ${creative.ad_id}`}
          </div>
          <div className="text-xs truncate" style={{ color: 'var(--text-muted)' }}>
            {creative.campaign_name}
          </div>
        </div>

        {/* Creative copy preview */}
        {(creative.title || creative.body) && (
          <div className="p-2 rounded text-xs" style={{ background: 'rgba(255,255,255,0.03)' }}>
            {creative.title && (
              <div className="font-semibold truncate mb-0.5" style={{ color: 'var(--text-secondary)' }}>
                {creative.title}
              </div>
            )}
            {creative.body && (
              <div className="line-clamp-2" style={{ color: 'var(--text-muted)' }}>
                {creative.body}
              </div>
            )}
          </div>
        )}

        {/* Metrics grid */}
        <div className="grid grid-cols-2 gap-2">
          <div>
            <div className="text-xs" style={{ color: 'var(--text-muted)' }}>Spend</div>
            <div className="font-mono text-sm font-semibold" style={{ color: 'var(--accent-danger)' }}>
              {fmt(creative.spend, 'currency')}
            </div>
          </div>
          <div>
            <div className="text-xs" style={{ color: 'var(--text-muted)' }}>Revenue</div>
            <div className="font-mono text-sm font-semibold" style={{ color: 'var(--accent-success)' }}>
              {fmt(creative.purchase_value, 'currency')}
            </div>
          </div>
          <div>
            <div className="text-xs" style={{ color: 'var(--text-muted)' }}>CPA</div>
            <div className="font-mono text-sm" style={{ color: 'var(--text-secondary)' }}>
              {fmt(creative.cpa, 'currency')}
            </div>
          </div>
          <div>
            <div className="text-xs" style={{ color: 'var(--text-muted)' }}>Purchases</div>
            <div className="font-mono text-sm" style={{ color: 'var(--text-secondary)' }}>
              {fmt(creative.purchases, 'int')}
            </div>
          </div>
          <div>
            <div className="text-xs" style={{ color: 'var(--text-muted)' }}>CTR</div>
            <div className="font-mono text-sm" style={{ color: 'var(--text-secondary)' }}>
              {fmt(creative.ctr, 'pct')}
            </div>
          </div>
          <div>
            <div className="text-xs" style={{ color: 'var(--text-muted)' }}>CPC</div>
            <div className="font-mono text-sm" style={{ color: 'var(--text-secondary)' }}>
              {fmt(creative.cpc, 'currency')}
            </div>
          </div>
        </div>

        {/* Impressions / Reach bar */}
        <div className="flex items-center gap-2 text-xs" style={{ color: 'var(--text-muted)' }}>
          <Eye className="w-3 h-3" />
          <span>{fmt(creative.impressions, 'int')} impressions</span>
          {creative.reach > 0 && <span>· {fmt(creative.reach, 'int')} reach</span>}
        </div>
      </div>
    </div>
  )
}

export default function CreativeCockpit() {
  const [sortBy, setSortBy] = useState('spend')
  const [syncing, setSyncing] = useState(false)
  const [syncResult, setSyncResult] = useState(null)

  const { data, refetch } = useQuery({
    queryKey: ['fb-creatives'],
    queryFn: () => fetch(`${API}/facebook/creatives`).then(r => r.json()),
  })

  const creatives = (data?.creatives || []).sort((a, b) => (b[sortBy] || 0) - (a[sortBy] || 0))

  const syncCreatives = async () => {
    setSyncing(true)
    setSyncResult(null)
    try {
      const res = await fetch(`${API}/facebook/sync-creatives`, { method: 'POST' })
      const d = await res.json()
      setSyncResult(d)
      refetch()
    } catch (e) {
      setSyncResult({ error: e.message })
    }
    setSyncing(false)
  }

  // Summary stats
  const totalSpend = creatives.reduce((s, c) => s + (c.spend || 0), 0)
  const totalRev = creatives.reduce((s, c) => s + (c.purchase_value || 0), 0)
  const blendedRoas = totalSpend > 0 ? (totalRev / totalSpend).toFixed(2) : 0
  const totalPurchases = creatives.reduce((s, c) => s + (c.purchases || 0), 0)

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex gap-2">
          {[
            { key: 'spend', label: 'Spend' },
            { key: 'roas', label: 'ROAS' },
            { key: 'purchase_value', label: 'Revenue' },
            { key: 'purchases', label: 'Purchases' },
            { key: 'ctr', label: 'CTR' },
          ].map(s => (
            <button key={s.key} onClick={() => setSortBy(s.key)}
                    className="px-3 py-1.5 rounded-lg text-xs font-body transition-all"
                    style={{
                      background: sortBy === s.key ? 'rgba(79,142,255,0.15)' : 'transparent',
                      color: sortBy === s.key ? 'var(--accent-primary)' : 'var(--text-muted)',
                      border: `1px solid ${sortBy === s.key ? 'rgba(79,142,255,0.4)' : 'var(--glass-border)'}`,
                    }}>
              {s.label}
            </button>
          ))}
        </div>
        <button onClick={syncCreatives} disabled={syncing}
                className="flex items-center gap-2 px-4 py-1.5 rounded-lg text-xs font-body border
                           border-accent-primary/30 text-accent-primary hover:bg-accent-primary/10 disabled:opacity-50">
          <RefreshCw className={`w-3 h-3 ${syncing ? 'animate-spin' : ''}`} />
          {syncing ? 'Syncing…' : 'Sync Creatives'}
        </button>
      </div>

      {syncResult && (
        <div className="glass-card p-3 text-xs font-mono"
             style={{ color: syncResult.error ? 'var(--accent-danger)' : 'var(--accent-success)' }}>
          {syncResult.error ? `Error: ${syncResult.error}` : `Synced ${syncResult.ads_synced} ads (last 14 days)`}
        </div>
      )}

      {/* Summary row */}
      {creatives.length > 0 && (
        <div className="grid grid-cols-4 gap-4 animate-in">
          <div className="glass-card p-4">
            <div className="text-xs mb-1" style={{ color: 'var(--text-muted)' }}>Total Spend</div>
            <div className="font-mono font-bold text-xl" style={{ color: 'var(--accent-danger)' }}>
              ${totalSpend.toFixed(2)}
            </div>
          </div>
          <div className="glass-card p-4">
            <div className="text-xs mb-1" style={{ color: 'var(--text-muted)' }}>Total Revenue</div>
            <div className="font-mono font-bold text-xl" style={{ color: 'var(--accent-success)' }}>
              ${totalRev.toFixed(2)}
            </div>
          </div>
          <div className="glass-card p-4">
            <div className="text-xs mb-1" style={{ color: 'var(--text-muted)' }}>Blended ROAS</div>
            <div className="font-mono font-bold text-xl" style={{ color: 'var(--accent-primary)' }}>
              {blendedRoas}x
            </div>
          </div>
          <div className="glass-card p-4">
            <div className="text-xs mb-1" style={{ color: 'var(--text-muted)' }}>Total Purchases</div>
            <div className="font-mono font-bold text-xl" style={{ color: 'var(--text-primary)' }}>
              {totalPurchases.toLocaleString()}
            </div>
          </div>
        </div>
      )}

      {/* Creative grid */}
      {creatives.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {creatives.map((creative, i) => (
            <CreativeCard key={creative.ad_id || i} creative={creative} rank={i + 1} />
          ))}
        </div>
      ) : (
        <div className="glass-card p-6 animate-in" style={{ borderColor: 'rgba(79,142,255,0.2)' }}>
          <h3 className="font-display text-sm font-semibold mb-3" style={{ color: 'var(--accent-primary)' }}>
            Connect Facebook Ads for Creative Cockpit
          </h3>
          <div className="text-xs space-y-2 font-body" style={{ color: 'var(--text-muted)' }}>
            <p>See which ad creatives drive the most revenue, lowest CPA, and highest ROAS.</p>
            <ol className="list-decimal pl-4 space-y-1">
              <li>Go to <strong style={{ color: 'var(--text-secondary)' }}>developers.facebook.com</strong> → Create App → Business</li>
              <li>Add Marketing API → get App ID + App Secret</li>
              <li>Generate long-lived User Access Token (60-day) from Graph API Explorer</li>
              <li>Get Ad Account ID from Business Manager (format: act_1234567890)</li>
              <li>Add all to <strong style={{ color: 'var(--text-secondary)' }}>Settings → Facebook Ads</strong></li>
              <li>Click <strong style={{ color: 'var(--text-secondary)' }}>Sync Creatives</strong> above</li>
            </ol>
          </div>
        </div>
      )}
    </div>
  )
}
