import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Save, AlertTriangle, CheckCircle, Eye, EyeOff } from 'lucide-react'

const API = '/api'

function Field({ label, name, value, onChange, type = 'text', placeholder, hint }) {
  const [show, setShow] = useState(false)
  const isSecret = type === 'password'
  return (
    <div className="space-y-1">
      <label className="text-xs font-semibold" style={{ color: 'var(--text-muted)' }}>{label}</label>
      <div className="relative">
        <input
          type={isSecret && !show ? 'password' : 'text'}
          value={value || ''}
          onChange={e => onChange(name, e.target.value)}
          placeholder={placeholder}
          className="w-full px-3 py-2 rounded-lg text-sm font-mono border transition-all
                     focus:outline-none focus:shadow-[0_0_0_2px_rgba(79,142,255,0.3)]"
          style={{ background: 'var(--glass-bg)', borderColor: 'var(--glass-border)', color: 'var(--text-primary)' }}
        />
        {isSecret && (
          <button type="button" onClick={() => setShow(s => !s)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 p-1"
                  style={{ color: 'var(--text-muted)' }}>
            {show ? <EyeOff className="w-3 h-3" /> : <Eye className="w-3 h-3" />}
          </button>
        )}
      </div>
      {hint && <p className="text-xs" style={{ color: 'var(--text-muted)' }}>{hint}</p>}
    </div>
  )
}

function NumberField({ label, name, value, onChange, min, max, step = 0.1, hint }) {
  return (
    <div className="space-y-1">
      <label className="text-xs font-semibold" style={{ color: 'var(--text-muted)' }}>{label}</label>
      <input
        type="number"
        value={value ?? ''}
        onChange={e => onChange(name, parseFloat(e.target.value))}
        min={min} max={max} step={step}
        className="w-full px-3 py-2 rounded-lg text-sm font-mono border transition-all
                   focus:outline-none focus:shadow-[0_0_0_2px_rgba(79,142,255,0.3)]"
        style={{ background: 'var(--glass-bg)', borderColor: 'var(--glass-border)', color: 'var(--text-primary)' }}
      />
      {hint && <p className="text-xs" style={{ color: 'var(--text-muted)' }}>{hint}</p>}
    </div>
  )
}

function CardSection({ title, children }) {
  return (
    <div className="glass-card p-5 space-y-4">
      <h3 className="font-display text-sm font-semibold pb-2 border-b"
          style={{ color: 'var(--text-secondary)', borderColor: 'var(--glass-border)' }}>
        {title}
      </h3>
      {children}
    </div>
  )
}

export default function Settings() {
  const qc = useQueryClient()
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState(null)

  const { data: cfg, isLoading } = useQuery({
    queryKey: ['config'],
    queryFn: () => fetch(`${API}/config`).then(r => r.json()),
  })

  const [form, setForm] = useState(null)
  if (cfg && !form) setForm(cfg)

  const mutation = useMutation({
    mutationFn: body => fetch(`${API}/config`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).then(r => r.json()),
    onSuccess: () => { setSaved(true); qc.invalidateQueries(['config']); setTimeout(() => setSaved(false), 2500) },
    onError: e => setError(e.message),
  })

  if (isLoading || !form) return <div className="text-sm" style={{ color: 'var(--text-muted)' }}>Loading...</div>

  const set = (name, val) => setForm(f => ({ ...f, [name]: val }))
  const setNested = (section, name, val) => setForm(f => ({ ...f, [section]: { ...(f[section] || {}), [name]: val } }))

  const adsApi = form.amazon_ads_api || {}
  const spApi = form.sp_api || {}

  return (
    <div className="space-y-6 max-w-3xl">
      {/* Claude AI */}
      <CardSection title="Claude AI">
        <Field label="Claude API Key" name="claude_api_key" value={form.claude_api_key} onChange={set}
               type="password" placeholder="sk-ant-..."
               hint="Get from console.anthropic.com — required for AI competitor intelligence and smart recommendations" />
        <div className="space-y-1">
          <label className="text-xs font-semibold" style={{ color: 'var(--text-muted)' }}>Model</label>
          <select value={form.claude_model || 'claude-sonnet-4-6'} onChange={e => set('claude_model', e.target.value)}
                  className="w-full px-3 py-2 rounded-lg text-sm font-mono border"
                  style={{ background: 'var(--glass-bg)', borderColor: 'var(--glass-border)', color: 'var(--text-primary)' }}>
            <option value="claude-sonnet-4-6">claude-sonnet-4-6 (recommended)</option>
            <option value="claude-opus-4-6">claude-opus-4-6 (most capable, slower)</option>
            <option value="claude-haiku-4-5-20251001">claude-haiku-4-5-20251001 (fastest)</option>
          </select>
        </div>
      </CardSection>

      {/* PPC Thresholds */}
      <CardSection title="PPC Thresholds">
        <div className="grid grid-cols-2 gap-4">
          <NumberField label="Target ACoS (%)" name="target_acos" value={form.target_acos} onChange={set}
                       min={1} max={100} hint="Your break-even ACoS goal" />
          <NumberField label="Break-Even ACoS (%)" name="break_even_acos" value={form.break_even_acos} onChange={set}
                       min={1} max={200} hint="Maximum acceptable before pausing" />
          <NumberField label="Harvest Clicks Threshold" name="harvest_clicks_threshold" value={form.harvest_clicks_threshold}
                       onChange={set} min={1} max={100} step={1} hint="Min clicks to promote a search term" />
          <NumberField label="Bid Multiplier" name="bid_multiplier" value={form.bid_multiplier} onChange={set}
                       min={1} max={3} hint="Multiplier for bid suggestions (1.2 = +20%)" />
        </div>
      </CardSection>

      {/* Profitability */}
      <CardSection title="Profitability">
        <div className="grid grid-cols-3 gap-4">
          <NumberField label="COGS per Unit ($)" name="cogs_per_unit" value={form.cogs_per_unit} onChange={set} min={0} step={0.01} />
          <NumberField label="FBA Fee ($)" name="fba_fee" value={form.fba_fee} onChange={set} min={0} step={0.01} />
          <NumberField label="Referral Fee (%)" name="referral_fee_pct" value={form.referral_fee_pct} onChange={set} min={0} max={50} />
        </div>
      </CardSection>

      {/* Amazon Ads API */}
      <CardSection title="Amazon Advertising API (Auto PPC Sync)">
        <div className="text-xs mb-3 p-3 rounded-lg" style={{ background: 'rgba(79,142,255,0.06)', color: 'var(--text-muted)' }}>
          Get credentials at <strong style={{ color: 'var(--text-secondary)' }}>advertising.amazon.com</strong> →
          Apps & Services → Manage Apps → Create New App.
          The Profile ID is your advertising account ID (fetch via GET /v2/profiles after connecting).
        </div>
        <div className="grid grid-cols-2 gap-4">
          <Field label="Client ID" name="client_id" value={adsApi.client_id}
                 onChange={(_, v) => setNested('amazon_ads_api', 'client_id', v)} placeholder="amzn1.application-oa2-client..." />
          <Field label="Client Secret" name="client_secret" value={adsApi.client_secret} type="password"
                 onChange={(_, v) => setNested('amazon_ads_api', 'client_secret', v)} />
          <Field label="Refresh Token" name="refresh_token" value={adsApi.refresh_token} type="password"
                 onChange={(_, v) => setNested('amazon_ads_api', 'refresh_token', v)}
                 hint="From OAuth authorization flow" />
          <Field label="Profile ID" name="profile_id" value={adsApi.profile_id}
                 onChange={(_, v) => setNested('amazon_ads_api', 'profile_id', v)} placeholder="1234567890" />
        </div>
      </CardSection>

      {/* SP-API */}
      <CardSection title="Selling Partner API — SP-API (Sales Tracking)">
        <div className="text-xs mb-3 p-3 rounded-lg" style={{ background: 'rgba(79,142,255,0.06)', color: 'var(--text-muted)' }}>
          Register at <strong style={{ color: 'var(--text-secondary)' }}>developer.amazonservices.com</strong> →
          Create a Self-Authorized App (for your own seller account). This enables daily/weekly units sold tracking.
        </div>
        <div className="grid grid-cols-2 gap-4">
          <Field label="Client ID" name="client_id" value={spApi.client_id}
                 onChange={(_, v) => setNested('sp_api', 'client_id', v)} />
          <Field label="Client Secret" name="client_secret" value={spApi.client_secret} type="password"
                 onChange={(_, v) => setNested('sp_api', 'client_secret', v)} />
          <Field label="Refresh Token" name="refresh_token" value={spApi.refresh_token} type="password"
                 onChange={(_, v) => setNested('sp_api', 'refresh_token', v)} />
          <Field label="Seller ID" name="seller_id" value={spApi.seller_id}
                 onChange={(_, v) => setNested('sp_api', 'seller_id', v)} placeholder="A1B2C3D4E5F6G7" />
        </div>
      </CardSection>

      {/* Facebook Ads API */}
      <CardSection title="Facebook Ads API (Creative Cockpit + MER)">
        <div className="text-xs mb-3 p-3 rounded-lg" style={{ background: 'rgba(79,142,255,0.06)', color: 'var(--text-muted)' }}>
          Go to <strong style={{ color: 'var(--text-secondary)' }}>developers.facebook.com</strong> →
          Create App → Business → Add Marketing API. Then generate a long-lived access token
          from Graph API Explorer. Ad Account ID format: act_1234567890 (from Business Manager).
        </div>
        <div className="grid grid-cols-2 gap-4">
          <Field label="App ID" name="app_id" value={(form.facebook_ads || {}).app_id}
                 onChange={(_, v) => setNested('facebook_ads', 'app_id', v)} />
          <Field label="App Secret" name="app_secret" value={(form.facebook_ads || {}).app_secret} type="password"
                 onChange={(_, v) => setNested('facebook_ads', 'app_secret', v)} />
          <Field label="Access Token (long-lived)" name="access_token" value={(form.facebook_ads || {}).access_token}
                 type="password" onChange={(_, v) => setNested('facebook_ads', 'access_token', v)}
                 hint="60-day token from Graph API Explorer → exchange for long-lived" />
          <Field label="Ad Account ID" name="ad_account_id" value={(form.facebook_ads || {}).ad_account_id}
                 onChange={(_, v) => setNested('facebook_ads', 'ad_account_id', v)} placeholder="act_1234567890" />
        </div>
      </CardSection>

      {/* Shopify API */}
      <CardSection title="Shopify API (Revenue + Attribution)">
        <div className="text-xs mb-3 p-3 rounded-lg" style={{ background: 'rgba(79,142,255,0.06)', color: 'var(--text-muted)' }}>
          Shopify Admin → Settings → Apps & Sales Channels → Develop Apps → Create App →
          set scopes: read_orders, read_customers, read_analytics → Install → copy Admin API access token.
        </div>
        <div className="grid grid-cols-2 gap-4">
          <Field label="Shop Domain" name="shop_domain" value={(form.shopify || {}).shop_domain}
                 onChange={(_, v) => setNested('shopify', 'shop_domain', v)} placeholder="yourstore.myshopify.com"
                 hint="yourstore (without .myshopify.com) or full domain" />
          <Field label="Admin API Access Token" name="access_token" value={(form.shopify || {}).access_token}
                 type="password" onChange={(_, v) => setNested('shopify', 'access_token', v)}
                 placeholder="shpat_..." />
        </div>
      </CardSection>

      {/* Marketplace */}
      <CardSection title="Marketplace">
        <div className="space-y-1">
          <label className="text-xs font-semibold" style={{ color: 'var(--text-muted)' }}>Marketplace</label>
          <select value={form.marketplace || 'US'} onChange={e => set('marketplace', e.target.value)}
                  className="w-full px-3 py-2 rounded-lg text-sm font-mono border"
                  style={{ background: 'var(--glass-bg)', borderColor: 'var(--glass-border)', color: 'var(--text-primary)' }}>
            {['US', 'CA', 'UK', 'DE', 'FR', 'IT', 'ES', 'JP', 'AU', 'IN', 'MX'].map(m => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>
        </div>
      </CardSection>

      {/* Save */}
      <div className="flex items-center gap-4">
        <button
          onClick={() => mutation.mutate(form)}
          disabled={mutation.isPending}
          className="flex items-center gap-2 px-6 py-2.5 rounded-xl text-sm font-body transition-all
                     border border-accent-primary/30 text-accent-primary hover:bg-accent-primary/10
                     active:scale-[0.97] disabled:opacity-50"
        >
          <Save className="w-4 h-4" />
          {mutation.isPending ? 'Saving…' : 'Save Settings'}
        </button>
        {saved && (
          <div className="flex items-center gap-1.5 text-sm" style={{ color: 'var(--accent-success)' }}>
            <CheckCircle className="w-4 h-4" /> Saved
          </div>
        )}
        {error && (
          <div className="flex items-center gap-1.5 text-sm" style={{ color: 'var(--accent-danger)' }}>
            <AlertTriangle className="w-4 h-4" /> {error}
          </div>
        )}
      </div>
    </div>
  )
}
