export type SseEvent = { event: string; data: unknown }

/** Parse a text/event-stream body. Events may be split across network chunks; blank lines end an event. */
export async function* readSse(body: ReadableStream<Uint8Array>): AsyncGenerator<SseEvent> {
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  try {
    while (true) {
      const { value, done } = await reader.read()
      buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done })
      let boundary = buffer.indexOf('\n\n')
      while (boundary !== -1) {
        const block = buffer.slice(0, boundary)
        buffer = buffer.slice(boundary + 2)
        const parsed = parseBlock(block)
        if (parsed) yield parsed
        boundary = buffer.indexOf('\n\n')
      }
      if (done) break
    }
    const last = parseBlock(buffer)
    if (last) yield last
  } finally {
    reader.releaseLock()
  }
}

export function parseBlock(block: string): SseEvent | null {
  let event = 'message'
  const data: string[] = []
  for (const line of block.split('\n')) {
    if (line.startsWith('event:')) event = line.slice(6).trim()
    else if (line.startsWith('data:')) data.push(line.slice(5).replace(/^ /, ''))
  }
  if (!data.length) return null
  const text = data.join('\n')
  try {
    return { event, data: JSON.parse(text) }
  } catch {
    return { event, data: text }
  }
}
