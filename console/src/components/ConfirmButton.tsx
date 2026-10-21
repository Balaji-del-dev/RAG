import { useRef, type ReactNode } from 'react'

/** A button that asks first, in a modal dialog that says exactly what will happen. */
export function ConfirmButton({
  label,
  title,
  message,
  confirmLabel = label,
  danger = false,
  disabled = false,
  onConfirm,
}: {
  label: string
  title: string
  message: ReactNode
  confirmLabel?: string
  danger?: boolean
  disabled?: boolean
  onConfirm: () => void
}) {
  const dialog = useRef<HTMLDialogElement>(null)
  return (
    <>
      <button type="button" className={danger ? 'btn btn-danger' : 'btn'} disabled={disabled} onClick={() => dialog.current?.showModal()}>
        {label}
      </button>
      <dialog ref={dialog} className="dialog" aria-label={title}>
        <h2>{title}</h2>
        <div className="dialog-body">{message}</div>
        <div className="actions">
          <button type="button" className="btn" onClick={() => dialog.current?.close()}>
            Cancel
          </button>
          <button
            type="button"
            className={danger ? 'btn btn-danger' : 'btn btn-primary'}
            onClick={() => {
              dialog.current?.close()
              onConfirm()
            }}
          >
            {confirmLabel}
          </button>
        </div>
      </dialog>
    </>
  )
}
