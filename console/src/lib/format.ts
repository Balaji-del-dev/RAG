const dateTime = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' })

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '—' : dateTime.format(date)
}

/** Only same-site paths are allowed as a post-sign-in destination (no open redirects). */
export function safeNext(value: string | null | undefined, fallback = '/'): string {
  if (!value || !value.startsWith('/') || value.startsWith('//') || value.startsWith('/\\')) return fallback
  return value
}

export function shortUserAgent(agent: string): string {
  if (!agent) return 'Unknown device'
  const browser = /(Firefox|Edg|Chrome|Safari)\/[\d.]+/.exec(agent)?.[0]?.replace('Edg', 'Edge') ?? 'Browser'
  const system = /(Windows|Mac OS X|Android|iPhone|Linux)/.exec(agent)?.[0]?.replace('Mac OS X', 'macOS') ?? ''
  return system ? `${browser} on ${system}` : browser
}
