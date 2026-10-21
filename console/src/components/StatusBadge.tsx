export type Tone = 'ok' | 'warn' | 'bad' | 'info' | 'neutral'

export function StatusBadge({ label, tone = 'neutral' }: { label: string; tone?: Tone }) {
  return <span className={`badge badge-${tone}`}>{label}</span>
}
