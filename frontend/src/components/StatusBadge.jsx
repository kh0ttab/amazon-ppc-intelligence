import Tooltip from './Tooltip'

const BADGE_MAP = {
  WINNER:    'badge-winner',
  BLEEDING:  'badge-bleeding',
  SLEEPING:  'badge-sleeping',
  POTENTIAL: 'badge-potential',
  NEW:       'badge-new',
}

export default function StatusBadge({ status }) {
  const cls = BADGE_MAP[status] || 'badge-new'
  return (
    <Tooltip textKey={status}>
      <span className={`${cls} inline-block px-2.5 py-0.5 rounded-full text-xs font-mono tracking-wide`}>
        {status}
      </span>
    </Tooltip>
  )
}
