import { useQuery } from '@tanstack/react-query';
import { api, errorMessage } from '../../lib/api';
import { Button } from '../../components/ui/button';
import { AiSettings } from './ai';
import { NotificationSettings } from './notifications';

export function SettingsPage() {
  const status = useQuery({ queryKey: ['status'], queryFn: api.status });
  return (
    <>
      <p className="eyebrow">YOUR WORKSPACE</p>
      <h1 tabIndex={-1}>Settings</h1>
      <p className="page-description">Processing and workspace status.</p>
      <section className="panel">
        <h2>Connection</h2>
        {status.isPending ? (
          <p role="status">Checking workspace…</p>
        ) : status.isError ? (
          <div role="alert">
            <p>{errorMessage(status.error)}</p>
            <Button variant="secondary" onClick={() => void status.refetch()}>
              Try again
            </Button>
          </div>
        ) : (
          <dl className="settings-list">
            <div>
              <dt>Services</dt>
              <dd>
                {status.data.integration_mode === 'mock'
                  ? 'Mock responses for development'
                  : 'Live integrations'}
              </dd>
            </div>
            <div>
              <dt>Profile</dt>
              <dd>{status.data.profile_configured ? 'Configured' : 'Not configured'}</dd>
            </div>
          </dl>
        )}
      </section>
      <NotificationSettings />
      <AiSettings />
    </>
  );
}
