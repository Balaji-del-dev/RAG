import type { ReactNode } from 'react'
import ReactMarkdown from 'react-markdown'
import rehypeSanitize from 'rehype-sanitize'
import { linkCitations } from '../../lib/citations'

/** Sanitized markdown: no raw HTML, no images, no outside links — only citation chips. */
export function AnswerText({ text, onCite, draft = false }: { text: string; onCite?: (n: number) => void; draft?: boolean }) {
  return (
    <div className={draft ? 'answer-text answer-draft' : 'answer-text'}>
      <ReactMarkdown
        rehypePlugins={[rehypeSanitize]}
        components={{
          img: () => null,
          a: ({ href, children }: { href?: string; children?: ReactNode }) => {
            const match = /^#cite-(\d+)$/.exec(href ?? '')
            if (!match) return <span>{children}</span>
            const n = Number(match[1])
            return (
              <button type="button" className="cite" onClick={() => onCite?.(n)} disabled={draft} aria-label={`Show source ${n}`}>
                {n}
              </button>
            )
          },
        }}
      >
        {linkCitations(text)}
      </ReactMarkdown>
    </div>
  )
}
