import { Component, type ReactNode } from 'react';
import { Button } from './ui/button';
export class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    if (this.state.failed)
      return (
        <main className="standalone">
          <h1>This page could not load</h1>
          <p>Your saved data has not been changed. Reload to try again.</p>
          <Button onClick={() => window.location.reload()}>Reload page</Button>
        </main>
      );
    return this.props.children;
  }
}
