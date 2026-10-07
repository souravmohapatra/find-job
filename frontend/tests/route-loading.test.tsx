import { Suspense, lazy } from 'react';
import { act, render, screen } from '@testing-library/react';
import { expect, test, vi } from 'vitest';
import { ErrorBoundary } from '../src/components/error-boundary';

test('slow route loading retains navigation and exposes a loading status', async () => {
  let resolve!: (module: { default: () => React.ReactNode }) => void;
  const Page = lazy(
    () =>
      new Promise<{ default: () => React.ReactNode }>((done) => {
        resolve = done;
      }),
  );
  render(
    <>
      <nav aria-label="Main navigation">Navigation</nav>
      <main>
        <Suspense fallback={<p role="status">Opening page…</p>}>
          <Page />
        </Suspense>
      </main>
    </>,
  );
  expect(screen.getByRole('navigation')).toBeVisible();
  expect(screen.getByRole('status')).toHaveTextContent('Opening page…');
  await act(async () => resolve({ default: () => <h1>Loaded page</h1> }));
  expect(screen.getByRole('heading', { name: 'Loaded page' })).toBeVisible();
  expect(screen.queryByRole('status')).toBeNull();
});

test('route errors stay inside the main landmark and navigation resets recovery', () => {
  const log = vi.spyOn(console, 'error').mockImplementation(() => {});
  function Broken(): React.ReactNode {
    throw new Error('Synthetic failed page import');
  }
  const view = render(
    <>
      <nav aria-label="Main navigation">Navigation</nav>
      <main>
        <ErrorBoundary embedded key="first">
          <Broken />
        </ErrorBoundary>
      </main>
    </>,
  );
  expect(screen.getAllByRole('main')).toHaveLength(1);
  expect(screen.getByRole('navigation')).toBeVisible();
  expect(screen.getByRole('alert')).toHaveTextContent('This page could not load');
  expect(screen.getByRole('button', { name: 'Reload page' })).toBeVisible();
  view.rerender(
    <>
      <nav aria-label="Main navigation">Navigation</nav>
      <main>
        <ErrorBoundary embedded key="second">
          <h1>Other page</h1>
        </ErrorBoundary>
      </main>
    </>,
  );
  expect(screen.getByRole('heading', { name: 'Other page' })).toBeVisible();
  expect(screen.queryByRole('alert')).toBeNull();
  log.mockRestore();
});
