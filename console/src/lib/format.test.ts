import { describe, expect, it } from 'vitest'
import { safeNext } from './format'

describe('safeNext', () => {
  it('keeps same-site paths', () => {
    expect(safeNext('/admin/users?page=2')).toBe('/admin/users?page=2')
  })

  it.each([null, '', 'https://evil.example', '//evil.example', '/\\evil.example', 'javascript:alert(1)'])(
    'falls back to / for %s',
    (value) => {
      expect(safeNext(value)).toBe('/')
    },
  )
})
