import { Component, type ErrorInfo, type ReactNode } from 'react'

type State = { error: Error | null }

/** If one page crashes, show what happened there instead of a blank screen; the menu keeps working. */
export class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Page crashed:', error, info.componentStack)
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <section className="panel" role="alert">
        <h1>This page ran into a problem</h1>
        <p className="muted">The rest of the console still works. Reload the page to try again.</p>
        <pre className="source-text">{this.state.error.message}</pre>
        <button type="button" className="btn btn-primary" onClick={() => window.location.reload()}>
          Reload
        </button>
      </section>
    )
  }
}
