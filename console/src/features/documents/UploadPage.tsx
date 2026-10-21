import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useRef, useState, type DragEvent } from 'react'
import { Link, useNavigate } from 'react-router'
import { myAccessGroups } from '../../api/auth'
import { ApiError, errorMessage } from '../../api/client'
import { uploadDocument } from '../../api/documents'
import type { UploadResult } from '../../api/types'
import { PageHeader } from '../../components/Feedback'
import { formatBytes } from '../../lib/status'
import { AccessGroupPicker } from './AccessGroupPicker'

const ACCEPT = '.pdf,.docx,.xlsx,.pptx,.txt,.md,.csv,.json,.xml,.html,.htm'
const MAX_MB = 50

export default function UploadPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const input = useRef<HTMLInputElement>(null)
  const groups = useQuery({ queryKey: ['access-groups-mine'], queryFn: myAccessGroups })
  const [file, setFile] = useState<File | null>(null)
  const [chosenGroups, setGroupIds] = useState<string[] | null>(null)
  const [progress, setProgress] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [duplicate, setDuplicate] = useState<UploadResult | null>(null)
  const [dragging, setDragging] = useState(false)

  // Until the user picks groups themselves, default to "general".
  const general = groups.data?.find((g) => g.name === 'general')
  const groupIds = chosenGroups ?? (general ? [general.id] : [])

  function choose(chosen: File | undefined) {
    setError(null)
    setDuplicate(null)
    if (!chosen) return
    if (chosen.size > MAX_MB * 1024 * 1024) {
      setError(`The file is larger than ${MAX_MB} MB.`)
      return
    }
    setFile(chosen)
  }

  async function upload() {
    if (!file) return
    setError(null)
    setProgress(0)
    try {
      const result = await uploadDocument(file, groupIds, setProgress)
      queryClient.invalidateQueries({ queryKey: ['documents'] })
      if (result.duplicate) setDuplicate(result)
      else navigate(`/documents/${result.document.id}`)
    } catch (err) {
      setError(err instanceof ApiError ? (err.fieldErrors('access_group_ids')[0] ?? err.message) : errorMessage(err))
    } finally {
      setProgress(null)
    }
  }

  return (
    <>
      <p className="muted">
        <Link to="/documents">Documents</Link> / Upload
      </p>
      <PageHeader title="Upload a document" description={`PDF, Word, Excel, PowerPoint, text, Markdown, CSV, JSON, XML or HTML — up to ${MAX_MB} MB.`} />
      <section className="panel">
        <div
          className={dragging ? 'dropzone dropzone-active' : 'dropzone'}
          onDragOver={(e: DragEvent) => {
            e.preventDefault()
            setDragging(true)
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e: DragEvent) => {
            e.preventDefault()
            setDragging(false)
            choose(e.dataTransfer.files[0])
          }}
        >
          <p>{file ? <strong>{file.name}</strong> : 'Drop a file here, or'}</p>
          {file && <p className="muted">{formatBytes(file.size)}</p>}
          <button type="button" className="btn" onClick={() => input.current?.click()}>
            {file ? 'Choose another file' : 'Choose a file'}
          </button>
          <input ref={input} type="file" accept={ACCEPT} hidden aria-label="File to upload" onChange={(e) => choose(e.target.files?.[0])} />
        </div>
        <AccessGroupPicker value={groupIds} onChange={setGroupIds} />
        {progress !== null && (
          <div className="progress" role="progressbar" aria-valuenow={Math.round(progress * 100)} aria-valuemin={0} aria-valuemax={100}>
            <div style={{ width: `${Math.round(progress * 100)}%` }} />
            <span>{progress < 1 ? `Uploading… ${Math.round(progress * 100)}%` : 'Checking the file…'}</span>
          </div>
        )}
        {error && (
          <p className="alert alert-error" role="alert">
            {error}
          </p>
        )}
        {duplicate && (
          <p className="alert alert-warn" role="status">
            This file is already uploaded as <Link to={`/documents/${duplicate.document.id}`}>{duplicate.document.filename}</Link> ({duplicate.document.lifecycle_status}).
          </p>
        )}
        <div className="actions">
          <button type="button" className="btn btn-primary" disabled={!file || groupIds.length === 0 || progress !== null} onClick={upload}>
            Upload
          </button>
        </div>
      </section>
    </>
  )
}
