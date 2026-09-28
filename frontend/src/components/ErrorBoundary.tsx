import { Component, type ErrorInfo, type ReactNode } from 'react'

/** Keeps one broken screen from blanking the whole app; offers a way back. */
export class ErrorBoundary extends Component<{ children: ReactNode; resetKey?: string }, { error: Error | null }> {
  state = { error: null as Error | null }

  static getDerivedStateFromError(error: Error) {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Screen crashed', error, info.componentStack)
  }

  componentDidUpdate(prev: { resetKey?: string }) {
    if (prev.resetKey !== this.props.resetKey && this.state.error) this.setState({ error: null })
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <div className="mx-auto max-w-lg p-6">
        <div className="card p-5">
          <h2 className="text-lg font-bold">This screen hit a problem</h2>
          <p className="mt-1 text-sm text-slate-600">Your data is safe — drafts and unsent items stay on this device.</p>
          <pre className="mt-3 max-h-32 overflow-auto rounded-lg bg-slate-50 p-2 text-xs text-slate-500">{this.state.error.message}</pre>
          <div className="mt-4 flex gap-2">
            <button className="btn-primary" onClick={() => this.setState({ error: null })}>Try again</button>
            <a className="btn-ghost" href="/">Go home</a>
          </div>
        </div>
      </div>
    )
  }
}
