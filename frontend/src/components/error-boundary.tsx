import { Component, type ReactNode } from 'react';
import { Button } from './ui/button';
export class ErrorBoundary extends Component<
  { children: ReactNode; embedded?: boolean },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    const Container = this.props.embedded ? 'section' : 'main';
    if (this.state.failed)
      return (
        <Container className={this.props.embedded ? 'panel' : 'standalone'} role="alert">
          <h1>This page could not load</h1>
          <p>Your saved data has not been changed. Reload to try again.</p>
          <Button onClick={() => window.location.reload()}>Reload page</Button>
        </Container>
      );
    return this.props.children;
  }
}
