import { useState } from 'react'

/** A JSON text area: reports syntax errors as you type; calls onChange only with valid objects. */
export function JsonEditor({
  value,
  onChange,
  readOnly = false,
  label,
  errors = [],
  rows = 6,
}: {
  value: Record<string, unknown>
  onChange?: (value: Record<string, unknown>) => void
  readOnly?: boolean
  label: string
  errors?: string[]
  rows?: number
}) {
  const [text, setText] = useState(() => JSON.stringify(value, null, 2))
  const [syntax, setSyntax] = useState<string | null>(null)

  return (
    <label className="json-editor">
      <span className="sr-only">{label}</span>
      <textarea
        aria-label={label}
        value={text}
        readOnly={readOnly}
        rows={rows}
        spellCheck={false}
        onChange={(event) => {
          setText(event.target.value)
          try {
            const parsed: unknown = JSON.parse(event.target.value)
            if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error('not an object')
            setSyntax(null)
            onChange?.(parsed as Record<string, unknown>)
          } catch {
            setSyntax('Not valid JSON — use {"setting": value} with double quotes.')
          }
        }}
      />
      {syntax && <span className="field-error">{syntax}</span>}
      {errors.map((message) => (
        <span className="field-error" key={message}>
          {message}
        </span>
      ))}
    </label>
  )
}
