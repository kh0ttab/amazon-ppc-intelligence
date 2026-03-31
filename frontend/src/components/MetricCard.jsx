import { useEffect, useRef, useState } from 'react'
import Tooltip from './Tooltip'

function AnimatedNumber({ value, prefix = '', suffix = '', decimals = 0 }) {
  const [display, setDisplay] = useState(0)
  const ref = useRef(null)

  useEffect(() => {
    const target = typeof value === 'number' ? value : parseFloat(value) || 0
    const duration = 1200
    const start = performance.now()
    const from = 0

    function tick(now) {
      const elapsed = now - start
      const progress = Math.min(elapsed / duration, 1)
      const eased = 1 - Math.pow(1 - progress, 3)
      setDisplay(from + (target - from) * eased)
      if (progress < 1) ref.current = requestAnimationFrame(tick)
    }

    ref.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(ref.current)
  }, [value])

  return (
    <span className="font-mono font-light text-[2rem] leading-none" style={{ color: 'var(--text-data)' }}>
      {prefix}{display.toFixed(decimals)}{suffix}
    </span>
  )
}

const BORDER_COLORS = {
  spend: 'var(--accent-danger)',
  revenue: 'var(--accent-success)',
  acos: 'var(--accent-primary)',
  tacos: 'var(--accent-warning)',
  roas: 'var(--accent-secondary)',
  orders: 'var(--accent-primary)',
  default: 'var(--accent-primary)',
}

export default function MetricCard({ label, value, prefix = '$', suffix = '', decimals = 2, tooltipKey, variant = 'default', delay = 0 }) {
  const borderColor = BORDER_COLORS[variant] || BORDER_COLORS.default

  return (
    <div
      className="glass-card p-5 flex flex-col gap-3 min-w-[160px] animate-in"
      style={{ borderTopWidth: 2, borderTopColor: borderColor, animationDelay: `${delay}ms` }}
    >
      <Tooltip textKey={tooltipKey}>
        <span
          className="uppercase tracking-[0.12em] text-[0.65rem] font-body"
          style={{ color: 'var(--text-secondary)' }}
        >
          {label}
        </span>
      </Tooltip>
      <AnimatedNumber value={value} prefix={prefix} suffix={suffix} decimals={decimals} />
    </div>
  )
}
