import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { linkCitations } from '../../lib/citations'
import { AnswerText } from './AnswerText'

describe('AnswerText', () => {
  afterEach(cleanup)

  it('turns [n] into citation chips that open the source', () => {
    const onCite = vi.fn()
    render(<AnswerText text="You get 24 days [1] and 5 carry over [2]." onCite={onCite} />)
    fireEvent.click(screen.getByRole('button', { name: 'Show source 2' }))
    expect(onCite).toHaveBeenCalledWith(2)
  })

  it('never renders raw HTML, images or outside links', () => {
    const { container } = render(<AnswerText text={'<script>alert(1)</script>\n\n![x](http://evil/x.png)\n\n[click](https://evil.example)'} />)
    expect(container.querySelector('script')).toBeNull()
    expect(container.querySelector('img')).toBeNull()
    expect(container.querySelector('a')).toBeNull()
    expect(container.textContent).toContain('click')
  })

  it('a draft cannot be clicked', () => {
    render(<AnswerText text="Draft [1]" draft />)
    expect((screen.getByRole('button', { name: 'Show source 1' }) as HTMLButtonElement).disabled).toBe(true)
  })

  it('leaves real markdown links alone when linking citations', () => {
    expect(linkCitations('see [1] and [a](b)')).toBe('see [[1]](#cite-1) and [a](b)')
  })
})
