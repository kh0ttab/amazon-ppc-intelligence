import { TOOLTIPS } from '../constants/tooltips'

export default function Tooltip({ textKey, text, children }) {
  const content = text || TOOLTIPS[textKey] || ''
  if (!content) return children

  return (
    <div className="relative group/tip inline-flex items-center gap-1">
      {children}
      <div
        className="absolute z-50 hidden group-hover/tip:block bottom-full mb-2
                    left-1/2 -translate-x-1/2 px-3.5 py-2.5 rounded-[10px] text-[0.78rem]
                    leading-relaxed whitespace-pre-line pointer-events-none
                    border shadow-[0_8px_32px_rgba(0,0,0,0.6),0_0_0_0.5px_rgba(79,142,255,0.1)]"
        style={{
          background: 'rgba(10,14,26,0.95)',
          borderColor: 'rgba(79,142,255,0.2)',
          backdropFilter: 'blur(20px)',
          color: 'rgba(255,255,255,0.8)',
          maxWidth: 240,
          fontFamily: "'Outfit', sans-serif",
          animation: 'tooltipIn 0.15s cubic-bezier(0.23, 1, 0.32, 1)',
        }}
      >
        {content}
      </div>
    </div>
  )
}

export function InfoIcon({ textKey }) {
  return (
    <Tooltip textKey={textKey}>
      <svg className="w-3.5 h-3.5 opacity-25 hover:opacity-60 transition-opacity cursor-help" viewBox="0 0 16 16" fill="currentColor">
        <circle cx="8" cy="8" r="7" fill="none" stroke="currentColor" strokeWidth="1.2" />
        <text x="8" y="11.5" textAnchor="middle" fontSize="9" fontFamily="'DM Mono', monospace">i</text>
      </svg>
    </Tooltip>
  )
}
