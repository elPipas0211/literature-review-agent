import { Component } from 'react'

/** Shows a readable message instead of a blank page when a component crashes. */
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    console.error(error, info.componentStack)
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <div className="error-box">
        <strong>Something went wrong in {this.props.area || 'this panel'}.</strong>
        <code>{String(this.state.error.message || this.state.error)}</code>
        <button className="btn btn-outline btn-sm" onClick={() => this.setState({ error: null })}>Try again</button>
        <button className="btn btn-ghost btn-sm" onClick={() => location.reload()}>Reload page</button>
      </div>
    )
  }
}
