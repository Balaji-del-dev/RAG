import { cleanup, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { baseMe, renderWith } from '../test/render'
import { RequirePermission } from './RequirePermission'

describe('RequirePermission', () => {
  afterEach(cleanup)

  it('shows the page when the user has the permission', () => {
    renderWith(<RequirePermission perm="rag.ask">secret page</RequirePermission>)
    expect(screen.getByText('secret page')).toBeTruthy()
  })

  it('shows "no permission" instead when the user lacks it', () => {
    renderWith(<RequirePermission perm="accounts.manage">secret page</RequirePermission>)
    expect(screen.queryByText('secret page')).toBeNull()
    expect(screen.getByText("You don't have permission for this")).toBeTruthy()
    expect(screen.getByText('Admin')).toBeTruthy()  // names the role that opens the page
  })

  it('can hide a button entirely', () => {
    renderWith(
      <RequirePermission perm="documents.upload" fallback={null}>
        <button>Upload</button>
      </RequirePermission>,
      { me: { ...baseMe, permissions: [...baseMe.permissions, 'documents.upload'] } },
    )
    expect(screen.getByRole('button', { name: 'Upload' })).toBeTruthy()
  })
})
