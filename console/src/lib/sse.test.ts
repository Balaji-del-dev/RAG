import { describe, expect, it } from 'vitest'
import { parseBlock, readSse } from './sse'

function streamOf(...pieces: string[]) {
  const encoder = new TextEncoder()
  return new ReadableStream<Uint8Array>({
    start(controller) {
      for (const p of pieces) controller.enqueue(encoder.encode(p))
      controller.close()
    },
  })
}

describe('readSse', () => {
  it('reads events split across network chunks', async () => {
    const events = []
    for await (const e of readSse(streamOf('event: meta\ndata: {"run_id":"r1"}\n\nevent: tok', 'en\ndata: {"text":"Hel', 'lo"}\n\nevent: done\ndata: {"answer":"Hello [1]"}\n\n'))) events.push(e)
    expect(events).toEqual([
      { event: 'meta', data: { run_id: 'r1' } },
      { event: 'token', data: { text: 'Hello' } },
      { event: 'done', data: { answer: 'Hello [1]' } },
    ])
  })

  it('ignores blocks without data and keeps plain text data', () => {
    expect(parseBlock(': keep-alive')).toBeNull()
    expect(parseBlock('event: note\ndata: not json')).toEqual({ event: 'note', data: 'not json' })
  })
})
