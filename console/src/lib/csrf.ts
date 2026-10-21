export function readCookie(name: string): string | null {
  for (const part of document.cookie.split(';')) {
    const [key, ...value] = part.trim().split('=')
    if (key === name) return decodeURIComponent(value.join('='))
  }
  return null
}

/** Django's CSRF cookie; sent back as the X-CSRFToken header on every write. */
export const csrfToken = (): string | null => readCookie('csrftoken')
