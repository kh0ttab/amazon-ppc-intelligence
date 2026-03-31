import { useState } from 'react'
import DataTable from '../components/DataTable'
import { Search, Brain, Target, Zap, AlertTriangle, ChevronDown, ChevronUp } from 'lucide-react'

const ORGANIC_COLS = [
  { key: 'position', label: '#', format: 'number' },
  { key: 'title', label: 'Title' },
  { key: 'asin', label: 'ASIN' },
  { key: 'price', label: 'Price' },
]
const BID_COLS = [
  { key: 'keyword', label: 'Gap Keyword' },
  { key: 'estimated_cpc', label: 'Est. CPC', format: 'currency', align: 'right' },
  { key: 'suggested_bid', label: 'Suggested Bid', format: 'currency', align: 'right' },
  { key: 'match_type', label: 'Match' },
  { key: 'competition', label: 'Competition' },
]

const PRIORITY_COLOR = {
  high: 'var(--accent-danger)',
  medium: 'var(--accent-warning)',
  low: 'var(--accent-success)',
}

const COMPETITION_COLOR = {
  high: 'var(--accent-danger)',
  medium: '#f59e0b',
  low: 'var(--accent-success)',
}

function Section({ title, icon: Icon, children, delay = 0 }) {
  const [open, setOpen] = useState(true)
  return (
    <div className="glass-card overflow-hidden animate-in" style={{ animationDelay: `${delay}ms` }}>
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-5 py-3 border-b hover:bg-white/[0.02] transition-colors"
        style={{ borderColor: 'var(--glass-border)' }}
      >
        <div className="flex items-center gap-2">
          {Icon && <Icon className="w-4 h-4" style={{ color: 'var(--accent-primary)' }} />}
          <span className="font-display text-sm font-semibold" style={{ color: 'var(--text-secondary)' }}>
            {title}
          </span>
        </div>
        {open ? <ChevronUp className="w-4 h-4" style={{ color: 'var(--text-muted)' }} />
               : <ChevronDown className="w-4 h-4" style={{ color: 'var(--text-muted)' }} />}
      </button>
      {open && <div className="p-5">{children}</div>}
    </div>
  )
}

export default function Competitors() {
  const [query, setQuery] = useState('')
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)

  const handleSearch = async () => {
    if (!query.trim()) return
    setLoading(true)
    setData(null)
    try {
      const res = await fetch(`/api/competitors/analyze?keyword=${encodeURIComponent(query)}`, { method: 'POST' })
      setData(await res.json())
    } catch (e) {
      setData({ error: e.message })
    }
    setLoading(false)
  }

  const intel = data?.ai_intel
  const hasIntel = intel && !intel.error

  return (
    <div className="space-y-6">
      {/* Search bar */}
      <div className="flex gap-3 animate-in">
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4" style={{ color: 'var(--text-muted)' }} />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            placeholder="Enter keyword to analyze competitor targeting..."
            className="w-full pl-10 pr-4 py-3 rounded-xl text-sm font-body border transition-all
                       focus:outline-none focus:shadow-[0_0_0_2px_rgba(79,142,255,0.3)]"
            style={{ background: 'var(--glass-bg)', borderColor: 'var(--glass-border)', color: 'var(--text-primary)' }}
          />
        </div>
        <button
          onClick={handleSearch}
          disabled={loading}
          className="flex items-center gap-2 px-6 py-3 rounded-xl text-sm font-body transition-all border
                     border-accent-primary/30 text-accent-primary hover:bg-accent-primary/10
                     active:scale-[0.97] disabled:opacity-50"
        >
          <Brain className="w-4 h-4" />
          {loading ? 'Analyzing…' : 'Analyze with Claude'}
        </button>
      </div>

      {data?.error && (
        <div className="glass-card p-4 text-sm" style={{ color: 'var(--accent-danger)' }}>
          {data.error}
        </div>
      )}

      {/* Claude AI Intelligence Panel */}
      {hasIntel && (
        <div className="glass-card p-5 animate-in"
             style={{ borderColor: 'rgba(79,142,255,0.3)', animationDelay: '20ms' }}>
          <div className="flex items-center gap-2 mb-4">
            <Brain className="w-4 h-4" style={{ color: 'var(--accent-primary)' }} />
            <span className="font-display text-sm font-semibold" style={{ color: 'var(--accent-primary)' }}>
              Claude AI Competitive Intelligence
            </span>
            <span className="ml-auto px-2 py-0.5 rounded-full text-xs font-mono"
                  style={{
                    background: `${COMPETITION_COLOR[intel.competition_level]}22`,
                    color: COMPETITION_COLOR[intel.competition_level],
                    border: `1px solid ${COMPETITION_COLOR[intel.competition_level]}44`,
                  }}>
              {intel.competition_level?.toUpperCase()} COMPETITION
              {intel.competition_score != null && ` · ${intel.competition_score}/100`}
            </span>
          </div>

          {/* Market insight */}
          {intel.market_insight && (
            <p className="text-sm font-body mb-4 leading-relaxed"
               style={{ color: 'var(--text-secondary)' }}>
              {intel.market_insight}
            </p>
          )}

          {/* Bid recommendation */}
          {intel.bid_recommendation && (
            <div className="rounded-xl p-4 mb-4"
                 style={{ background: 'rgba(79,142,255,0.06)', border: '1px solid rgba(79,142,255,0.15)' }}>
              <div className="flex items-center gap-6 flex-wrap">
                <div>
                  <div className="text-xs mb-0.5" style={{ color: 'var(--text-muted)' }}>Min Bid</div>
                  <div className="font-mono font-semibold" style={{ color: 'var(--text-primary)' }}>
                    ${intel.bid_recommendation.min_bid?.toFixed(2)}
                  </div>
                </div>
                <div>
                  <div className="text-xs mb-0.5" style={{ color: 'var(--text-muted)' }}>Suggested Bid</div>
                  <div className="font-mono font-bold text-lg" style={{ color: 'var(--accent-primary)' }}>
                    ${intel.bid_recommendation.suggested_bid?.toFixed(2)}
                  </div>
                </div>
                <div>
                  <div className="text-xs mb-0.5" style={{ color: 'var(--text-muted)' }}>Max Bid</div>
                  <div className="font-mono font-semibold" style={{ color: 'var(--text-primary)' }}>
                    ${intel.bid_recommendation.max_bid?.toFixed(2)}
                  </div>
                </div>
                <div className="flex-1">
                  <div className="text-xs mb-0.5" style={{ color: 'var(--text-muted)' }}>Rationale</div>
                  <div className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                    {intel.bid_recommendation.rationale}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Action plan */}
          {intel.action_plan?.length > 0 && (
            <div className="space-y-2 mb-4">
              <div className="text-xs font-semibold mb-2" style={{ color: 'var(--text-muted)' }}>
                ACTION PLAN
              </div>
              {intel.action_plan.map((item, i) => (
                <div key={i} className="flex items-start gap-3 p-3 rounded-lg"
                     style={{ background: 'rgba(255,255,255,0.02)' }}>
                  <span className="flex-shrink-0 w-5 h-5 rounded-full flex items-center justify-center text-xs font-mono font-bold"
                        style={{ background: 'rgba(79,142,255,0.15)', color: 'var(--accent-primary)' }}>
                    {item.priority}
                  </span>
                  <div>
                    <div className="text-xs font-semibold mb-0.5" style={{ color: 'var(--text-secondary)' }}>
                      {item.action}
                    </div>
                    <div className="text-xs" style={{ color: 'var(--text-muted)' }}>
                      Expected: {item.expected_impact}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Keyword Gaps from Claude */}
      {hasIntel && intel.keyword_gaps?.length > 0 && (
        <Section title={`Claude Keyword Gaps (${intel.keyword_gaps.length})`} icon={Target} delay={40}>
          <div className="space-y-2">
            {intel.keyword_gaps.map((gap, i) => (
              <div key={i} className="flex items-start justify-between p-3 rounded-lg"
                   style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid var(--glass-border)' }}>
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-mono text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
                      {gap.keyword}
                    </span>
                    <span className="px-1.5 py-0.5 rounded text-xs"
                          style={{
                            background: `${PRIORITY_COLOR[gap.priority]}22`,
                            color: PRIORITY_COLOR[gap.priority],
                          }}>
                      {gap.priority}
                    </span>
                    <span className="text-xs px-1.5 py-0.5 rounded"
                          style={{ background: 'rgba(255,255,255,0.05)', color: 'var(--text-muted)' }}>
                      {gap.match_type}
                    </span>
                  </div>
                  <div className="text-xs" style={{ color: 'var(--text-muted)' }}>{gap.rationale}</div>
                </div>
                <div className="ml-4 text-right flex-shrink-0">
                  <div className="font-mono text-sm font-semibold" style={{ color: 'var(--accent-primary)' }}>
                    ${gap.suggested_bid?.toFixed(2)}
                  </div>
                  <div className="text-xs" style={{ color: 'var(--text-muted)' }}>bid</div>
                </div>
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* Competitor Strategies */}
      {hasIntel && intel.competitor_strategies?.length > 0 && (
        <Section title="Competitor Strategies" icon={Zap} delay={80}>
          <div className="space-y-3">
            {intel.competitor_strategies.map((s, i) => (
              <div key={i} className="p-3 rounded-lg" style={{ background: 'rgba(255,255,255,0.02)' }}>
                <div className="font-semibold text-sm mb-1" style={{ color: 'var(--text-secondary)' }}>
                  {s.strategy}
                </div>
                <div className="text-xs mb-2" style={{ color: 'var(--text-muted)' }}>{s.description}</div>
                {s.keywords_used?.length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    {s.keywords_used.map((kw, j) => (
                      <span key={j} className="px-2 py-0.5 rounded text-xs font-mono"
                            style={{ background: 'rgba(79,142,255,0.08)', color: 'var(--accent-primary)' }}>
                        {kw}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* Long-tail opportunities + Negatives */}
      {hasIntel && (intel.long_tail_opportunities?.length > 0 || intel.negative_keyword_suggestions?.length > 0) && (
        <div className="grid md:grid-cols-2 gap-4">
          {intel.long_tail_opportunities?.length > 0 && (
            <div className="glass-card p-5 animate-in" style={{ animationDelay: '120ms' }}>
              <h3 className="font-display text-sm font-semibold mb-3" style={{ color: 'var(--accent-success)' }}>
                Long-Tail Opportunities
              </h3>
              <div className="flex flex-wrap gap-2">
                {intel.long_tail_opportunities.map((kw, i) => (
                  <span key={i} className="px-2 py-1 rounded-lg text-xs font-mono"
                        style={{ background: 'rgba(16,185,129,0.08)', color: 'var(--accent-success)' }}>
                    {kw}
                  </span>
                ))}
              </div>
            </div>
          )}
          {intel.negative_keyword_suggestions?.length > 0 && (
            <div className="glass-card p-5 animate-in" style={{ animationDelay: '140ms' }}>
              <h3 className="font-display text-sm font-semibold mb-3" style={{ color: 'var(--accent-danger)' }}>
                Add as Negatives
              </h3>
              <div className="flex flex-wrap gap-2">
                {intel.negative_keyword_suggestions.map((kw, i) => (
                  <span key={i} className="px-2 py-1 rounded-lg text-xs font-mono"
                        style={{ background: 'rgba(239,68,68,0.08)', color: 'var(--accent-danger)' }}>
                    {kw}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Classic gap keywords (fallback / non-AI) */}
      {!hasIntel && data?.comparison?.gap?.length > 0 && (
        <div className="glass-card p-5 animate-in" style={{ animationDelay: '60ms' }}>
          <h3 className="font-display text-sm font-semibold mb-3" style={{ color: 'var(--accent-success)' }}>
            Gap Keywords ({data.comparison.gap.length})
          </h3>
          <p className="text-xs mb-3" style={{ color: 'var(--text-muted)' }}>
            Keywords competitors rank for that you're missing (add Claude API key for deeper analysis)
          </p>
          <div className="flex flex-wrap gap-2">
            {data.comparison.gap.slice(0, 30).map((kw, i) => (
              <span key={i} className="badge-new px-2 py-0.5 rounded-full text-xs font-mono">{kw}</span>
            ))}
          </div>
        </div>
      )}

      {/* Bid suggestions */}
      {data?.bid_suggestions?.length > 0 && (
        <Section title="Bid Suggestions for Gap Keywords" delay={160}>
          <DataTable columns={BID_COLS} data={data.bid_suggestions} />
        </Section>
      )}

      {/* Organic results */}
      {data?.organic?.length > 0 && (
        <Section title={`Organic Results (${data.organic.length})`} delay={200}>
          <DataTable columns={ORGANIC_COLS} data={data.organic} />
        </Section>
      )}

      {/* Sponsored results */}
      {data?.sponsored?.length > 0 && (
        <Section title={`Sponsored Ads (${data.sponsored.length})`} delay={220}>
          <DataTable columns={ORGANIC_COLS} data={data.sponsored} />
        </Section>
      )}

      {/* AI error notice */}
      {intel?.error && (
        <div className="glass-card p-4 text-xs font-mono" style={{ color: 'var(--accent-warning)' }}>
          Claude AI: {intel.error} — add your API key in Settings to enable deep competitor analysis.
        </div>
      )}
    </div>
  )
}
