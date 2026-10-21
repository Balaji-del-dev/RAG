import { cleanup, fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { SseEvent } from '../../lib/sse'
import { renderWith } from '../../test/render'
import ChatPage from './ChatPage'

const script: { events: SseEvent[] } = { events: [] }

vi.mock('../../api/retrieval', () => ({
  ask: vi.fn(async (_q: string, onEvent: (e: SseEvent) => void) => {
    for (const e of script.events) onEvent(e)
  }),
  myRuns: vi.fn(async () => ({ count: 0, next: null, previous: null, results: [] })),
  getChunk: vi.fn(),
  sendFeedback: vi.fn(async () => ({})),
}))

async function ask(question: string) {
  fireEvent.change(screen.getByLabelText('Your question'), { target: { value: question } })
  fireEvent.click(screen.getByRole('button', { name: 'Ask' }))
}

describe('ChatPage', () => {
  // New Chrome returns a Promise from scrollIntoView; an effect that returned it crashed the page.
  beforeEach(() => {
    Element.prototype.scrollIntoView = vi.fn(() => Promise.resolve()) as unknown as Element['scrollIntoView']
  })
  afterEach(cleanup)

  it('shows the validated answer with citations, and the draft is gone', async () => {
    script.events = [
      { event: 'status', data: { stage: 'searching' } },
      { event: 'token', data: { text: 'You get 24 days ' } },
      { event: 'token', data: { text: '[1].' } },
      {
        event: 'done',
        data: {
          answer: 'You get 24 days [1].',
          answer_id: 'a1',
          status: 'VALIDATED',
          citations: [{ n: 1, chunk_id: 'c1', document_id: 'd1', filename: 'handbook.pdf', page_start: 2, page_end: 2, section_path: 'Leave' }],
        },
      },
    ]
    renderWith(<ChatPage />, { path: '/chat' })
    await ask('How many days of leave?')
    await waitFor(() => expect(screen.getByRole('button', { name: /handbook\.pdf, p\. 2/ })).toBeTruthy())
    expect(screen.queryByText(/Draft — checking the sources/)).toBeNull()
    expect(screen.getByRole('button', { name: 'Show source 1' })).toBeTruthy()
    expect(screen.getByText('Was this helpful?')).toBeTruthy()
  })

  it('answers a greeting as a normal reply, not as a failed search', async () => {
    script.events = [{ event: 'abstain', data: { message: 'Hello! Ask me anything about the documents you can access.', reason: 'small_talk' } }]
    renderWith(<ChatPage />, { path: '/chat' })
    await ask('hi')
    await waitFor(() => expect(screen.getByText('Hello! Ask me anything about the documents you can access.')).toBeTruthy())
    expect(document.querySelector('.alert-warn')).toBeNull()
    expect(screen.queryByText('Was this helpful?')).toBeNull()
  })

  it('replaces the draft with the abstention when the answer cannot be verified', async () => {
    script.events = [
      { event: 'token', data: { text: 'You get 24 days.' } },
      { event: 'abstain', data: { message: 'I could not find this in the documents you can access.', reason: 'unverified_answer' } },
    ]
    renderWith(<ChatPage />, { path: '/chat' })
    await ask('How many days of leave?')
    await waitFor(() => expect(screen.getByText('I could not find this in the documents you can access.')).toBeTruthy())
    expect(screen.queryByText('You get 24 days.')).toBeNull()
  })
})
