import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { JsonEditor } from './JsonEditor'

describe('JsonEditor', () => {
  afterEach(cleanup)

  it('passes valid objects on and shows nothing wrong', () => {
    const onChange = vi.fn()
    render(<JsonEditor label="Settings" value={{ a: 1 }} onChange={onChange} />)
    fireEvent.change(screen.getByLabelText('Settings'), { target: { value: '{"max_tokens": 300}' } })
    expect(onChange).toHaveBeenCalledWith({ max_tokens: 300 })
    expect(screen.queryByText(/Not valid JSON/)).toBeNull()
  })

  it('reports broken JSON and does not pass it on', () => {
    const onChange = vi.fn()
    render(<JsonEditor label="Settings" value={{}} onChange={onChange} />)
    fireEvent.change(screen.getByLabelText('Settings'), { target: { value: "{max_tokens: 300}" } })
    expect(onChange).not.toHaveBeenCalled()
    expect(screen.getByText(/Not valid JSON/)).toBeTruthy()
  })

  it('shows server-side errors under the field', () => {
    render(<JsonEditor label="Settings" value={{}} errors={['max_tokens: must be at most 480']} />)
    expect(screen.getByText('max_tokens: must be at most 480')).toBeTruthy()
  })
})
