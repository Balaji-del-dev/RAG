import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link } from 'react-router'
import { ApiError, errorMessage } from '../../api/client'
import * as retrieval from '../../api/retrieval'
import type { Citation, Run } from '../../api/types'
import { useCan } from '../../auth/session'
import { ErrorMessage, Loading } from '../../components/Feedback'
import { StatusBadge } from '../../components/StatusBadge'
import { formatDateTime } from '../../lib/format'
import type { SseEvent } from '../../lib/sse'
import { AnswerText } from './AnswerText'

const MAX_QUESTION = 2000
const STAGE_TEXT: Record<string, string> = {
  waiting: 'Waiting for another answer to finish…',
  queued: 'Waiting for the model…',
  searching: 'Searching your documents…',
  reranking: 'Picking the best passages…',
  writing: 'Writing the answer…',
  checking: 'Checking the sources…',
}

type Turn = {
  key: string
  question: string
  stage: string | null
  draft: string
  answerId?: string
  answer?: string
  citations: Citation[]
  status?: string
  abstain?: string
  error?: string
  existingFeedback?: number | null
}

function turnFromRun(run: Run): Turn {
  const a = run.answer
  const answered = a && (a.status === 'VALIDATED' || a.status === 'REPAIRED') && a.answer_text
  return {
    key: run.id,
    question: run.query_text,
    stage: null,
    draft: '',
    answerId: a?.id,
    answer: answered ? (a.answer_text ?? undefined) : undefined,
    citations: a?.citation_data ?? [],
    status: a?.status,
    abstain: !answered && run.status !== 'FAILED' ? 'I could not find this in the documents you can access.' : undefined,
    error: run.status === 'FAILED' ? 'The model did not answer this question.' : undefined,
    existingFeedback: a?.my_feedback?.rating ?? null,
  }
}

export default function ChatPage() {
  const queryClient = useQueryClient()
  const [question, setQuestion] = useState('')
  const [turns, setTurns] = useState<Turn[]>([])
  const [busy, setBusy] = useState(false)
  const [source, setSource] = useState<Citation | null>(null)
  const bottom = useRef<HTMLDivElement>(null)
  const history = useQuery({ queryKey: ['my-runs'], queryFn: () => retrieval.myRuns() })

  // Braces matter: newer browsers return a Promise from scrollIntoView, and React would treat it as the cleanup.
  useEffect(() => {
    bottom.current?.scrollIntoView?.({ behavior: 'smooth', block: 'end' })
  }, [turns])

  const update = (key: string, change: (t: Turn) => Partial<Turn>) =>
    setTurns((all) => all.map((t) => (t.key === key ? { ...t, ...change(t) } : t)))

  async function submit(event: FormEvent) {
    event.preventDefault()
    const text = question.trim()
    if (!text || busy) return
    const key = crypto.randomUUID()
    setTurns((all) => [...all, { key, question: text, stage: 'queued', draft: '', citations: [] }])
    setQuestion('')
    setBusy(true)
    try {
      await retrieval.ask(text, ({ event, data }: SseEvent) => {
        const d = data as Record<string, unknown>
        if (event === 'status') update(key, () => ({ stage: String(d.stage) }))
        if (event === 'token') update(key, (t) => ({ draft: t.draft + String(d.text) }))
        if (event === 'done')
          update(key, () => ({ stage: null, answer: String(d.answer), answerId: String(d.answer_id), citations: d.citations as Citation[], status: String(d.status) }))
        if (event === 'abstain' && d.reason === 'small_talk') update(key, () => ({ stage: null, draft: '', answer: String(d.message), citations: [] }))
        else if (event === 'abstain')
          update(key, () => ({ stage: null, draft: '', abstain: String(d.message), answerId: d.answer_id ? String(d.answer_id) : undefined }))
        if (event === 'error') update(key, () => ({ stage: null, draft: '', error: String(d.message) }))
      })
    } catch (err) {
      update(key, () => ({ stage: null, draft: '', error: err instanceof ApiError ? err.message : errorMessage(err) }))
    } finally {
      update(key, (t) => (t.stage ? { stage: null, error: t.answer || t.abstain ? undefined : 'The answer stream ended unexpectedly.' } : {}))
      setBusy(false)
      queryClient.invalidateQueries({ queryKey: ['my-runs'] })
    }
  }

  return (
    <div className="chat">
      <aside className="chat-history" aria-label="Your earlier questions">
        <h2>Your questions</h2>
        {history.isPending && <Loading />}
        {history.data?.results.length === 0 && <p className="muted small">Nothing asked yet.</p>}
        <ul>
          {history.data?.results.map((run) => (
            <li key={run.id}>
              <button type="button" className="history-item" onClick={() => setTurns((all) => (all.some((t) => t.key === run.id) ? all : [...all, turnFromRun(run)]))}>
                <span>{run.query_text}</span>
                <span className="muted small">{formatDateTime(run.created_at)}</span>
              </button>
            </li>
          ))}
        </ul>
      </aside>

      <section className="chat-main">
        <h1>Ask your documents</h1>
        {turns.length === 0 && (
          <p className="muted">
            Answers come only from documents shared with your access groups, and every answer shows its sources. Answers take about 20–60 seconds on this
            computer.
          </p>
        )}
        <ol className="turns">
          {turns.map((turn) => (
            <li key={turn.key} className="turn">
              <p className="question">{turn.question}</p>
              {turn.stage && (
                <p className="stage" role="status">
                  <span className="spinner" aria-hidden /> {STAGE_TEXT[turn.stage] ?? turn.stage}
                </p>
              )}
              {turn.draft && !turn.answer && (
                <>
                  <AnswerText text={turn.draft} draft />
                  <p className="muted small">Draft — checking the sources before it becomes the answer.</p>
                </>
              )}
              {turn.answer && (
                <div className="answer">
                  <AnswerText text={turn.answer} onCite={(n) => setSource(turn.citations.find((c) => c.n === n) ?? null)} />
                  <Sources citations={turn.citations} onOpen={setSource} />
                  {turn.status === 'REPAIRED' && <p className="muted small">The first draft had a citation problem and was corrected.</p>}
                  {turn.answerId && <Feedback answerId={turn.answerId} existing={turn.existingFeedback ?? null} />}
                </div>
              )}
              {turn.abstain && <p className="alert alert-warn">{turn.abstain}</p>}
              {turn.error && <p className="alert alert-error">{turn.error}</p>}
            </li>
          ))}
        </ol>
        <div ref={bottom} />
        <form className="ask-box" onSubmit={submit}>
          <label className="sr-only" htmlFor="question">
            Your question
          </label>
          <textarea
            id="question"
            value={question}
            maxLength={MAX_QUESTION}
            rows={2}
            placeholder="Ask a question about your documents…"
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                e.currentTarget.form?.requestSubmit()
              }
            }}
          />
          <div className="ask-actions">
            <span className="muted small">{question.length}/{MAX_QUESTION}</span>
            <button className="btn btn-primary" disabled={busy || !question.trim()}>
              {busy ? 'Answering…' : 'Ask'}
            </button>
          </div>
        </form>
      </section>

      {source && <SourcePanel citation={source} onClose={() => setSource(null)} />}
    </div>
  )
}

function Sources({ citations, onOpen }: { citations: Citation[]; onOpen: (c: Citation) => void }) {
  if (!citations.length) return null
  return (
    <ul className="sources">
      {citations.map((c) => (
        <li key={c.n}>
          <button type="button" className="source-chip" onClick={() => onOpen(c)}>
            <span className="cite">{c.n}</span> {c.filename}
            {c.page_start ? `, p. ${c.page_start}` : ''}
          </button>
        </li>
      ))}
    </ul>
  )
}

function SourcePanel({ citation, onClose }: { citation: Citation; onClose: () => void }) {
  const can = useCan()
  const chunk = useQuery({ queryKey: ['chunk', citation.chunk_id], queryFn: () => retrieval.getChunk(citation.chunk_id) })
  return (
    <aside className="source-panel" aria-label={`Source ${citation.n}`}>
      <div className="page-header">
        <h2>
          <span className="cite">{citation.n}</span> {citation.filename}
        </h2>
        <button type="button" className="btn btn-small" onClick={onClose}>
          Close
        </button>
      </div>
      <p className="muted small">
        {citation.section_path}
        {citation.page_start ? ` · page ${citation.page_start}` : ''}
      </p>
      {chunk.isPending && <Loading />}
      <ErrorMessage error={chunk.error} />
      {chunk.data && <pre className="source-text">{chunk.data.text_content}</pre>}
      {can('documents.view') && (
        <Link className="btn btn-small" to={`/documents/${citation.document_id}`}>
          Open the document
        </Link>
      )}
    </aside>
  )
}

const PROBLEMS: [string, string][] = [
  ['', 'What was wrong? (optional)'],
  ['WRONG_RETRIEVAL', 'It used the wrong documents'],
  ['NOT_GROUNDED', 'The sources do not say this'],
  ['INCOMPLETE', 'The answer is incomplete'],
  ['WRONG_CITATION', 'A citation points to the wrong place'],
  ['LATENCY', 'It was too slow'],
]

function Feedback({ answerId, existing }: { answerId: string; existing: number | null }) {
  const [rating, setRating] = useState<number | null>(existing)
  const [problem, setProblem] = useState('')
  const [comment, setComment] = useState('')
  const send = useMutation({ mutationFn: (stars: number) => retrieval.sendFeedback(answerId, stars, comment, problem) })
  return (
    <div className="feedback">
      <span className="muted small">Was this helpful?</span>
      <span className="stars" role="radiogroup" aria-label="Rating">
        {[1, 2, 3, 4, 5].map((n) => (
          <button
            key={n}
            type="button"
            role="radio"
            aria-checked={rating === n}
            aria-label={`${n} star${n > 1 ? 's' : ''}`}
            className={rating && n <= rating ? 'star star-on' : 'star'}
            onClick={() => {
              setRating(n)
              if (n >= 3) send.mutate(n)
            }}
          >
            ★
          </button>
        ))}
      </span>
      {rating !== null && rating <= 2 && !send.isSuccess && (
        <div className="feedback-detail">
          <select aria-label="What was wrong" value={problem} onChange={(e) => setProblem(e.target.value)}>
            {PROBLEMS.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
          <input aria-label="Comment" placeholder="Comment (optional)" value={comment} onChange={(e) => setComment(e.target.value)} />
          <button type="button" className="btn btn-small" onClick={() => send.mutate(rating)}>
            Send
          </button>
        </div>
      )}
      {send.isSuccess && <StatusBadge label="Thanks" tone="ok" />}
      <ErrorMessage error={send.error} />
    </div>
  )
}
