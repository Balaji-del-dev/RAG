import { ApiError } from '../../api/client'

/** What to tell someone whose sign-in failed. */
export function loginErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 423) return error.message
    if (error.status === 429) return 'Too many attempts. Wait a minute and try again.'
    if (error.status === 400) return 'Invalid username or password.'
    if (error.code === 'csrf_failed') return 'Your browser blocked the sign-in. Reload the page and try again.'
    return error.message
  }
  return 'Cannot reach the server. Check that the backend is running.'
}
