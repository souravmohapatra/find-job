import { useEffect, useRef } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { NavLink, Navigate, Outlet, Route, Routes, useLocation } from 'react-router-dom';
import {
  BriefcaseBusiness,
  Building2,
  UserRound,
  Settings2,
  LogOut,
  ArrowRight,
} from 'lucide-react';
import { api, ApiError, errorMessage, type Session } from '../lib/api';
import { Button } from '../components/ui/button';
import { Login } from '../features/auth/login';
import { ProfilePage } from '../features/profile/page';
const nav = [
  { to: '/jobs', label: 'Jobs', icon: BriefcaseBusiness },
  { to: '/companies', label: 'Companies', icon: Building2 },
  { to: '/profile', label: 'Profile', icon: UserRound },
  { to: '/settings', label: 'Settings', icon: Settings2 },
];
function RouteFocus() {
  const { pathname } = useLocation();
  const previous = useRef(pathname);
  useEffect(() => {
    if (previous.current !== pathname) {
      document.querySelector<HTMLElement>('main h1')?.focus();
      previous.current = pathname;
    }
    document.title = `${nav.find((item) => pathname.startsWith(item.to))?.label ?? 'Job Finder'} · Job Finder`;
  }, [pathname]);
  return null;
}
function Shell({ session }: { session: Session }) {
  const client = useQueryClient();
  const logout = useMutation({
    mutationFn: () => api.logout(session.csrf_token),
    onSuccess: () => {
      client.removeQueries({ predicate: (query) => query.queryKey[0] !== 'session' });
      client.setQueryData(['session'], null);
    },
    onError: (error) => {
      if (error instanceof ApiError && error.status === 401) {
        client.removeQueries({ predicate: (query) => query.queryKey[0] !== 'session' });
        client.setQueryData(['session'], null);
      }
    },
  });
  return (
    <div className="app-layout">
      <a href="#main" className="skip-link">
        Skip to content
      </a>
      <aside className="sidebar">
        <div className="brand">
          <BriefcaseBusiness aria-hidden="true" size={24} />
          <span>Job Finder</span>
        </div>
        <nav aria-label="Main navigation">
          {nav.map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to}>
              <Icon size={20} aria-hidden="true" />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="account">
          <span className="account-name">{session.username}</span>
          <Button variant="quiet" onClick={() => logout.mutate()} disabled={logout.isPending}>
            <LogOut size={18} aria-hidden="true" />
            {logout.isPending ? 'Signing out…' : 'Sign out'}
          </Button>
          {logout.isError && (
            <p className="field-error" role="alert">
              {errorMessage(logout.error)}
            </p>
          )}
        </div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <span>Personal workspace</span>
          <span className="badge">Development preview</span>
        </header>
        <main id="main" className="content">
          <RouteFocus />
          <Outlet />
        </main>
      </div>
    </div>
  );
}
const pages = {
  jobs: {
    eyebrow: 'YOUR OPPORTUNITIES',
    title: 'A wider view of what’s next',
    description: 'Relevant roles from the companies you choose, with room to explore.',
    empty: 'Your job search starts here',
    body: 'First, review your experience and the roles you want to explore. Then choose the companies to follow.',
    link: '/profile',
    action: 'View profile setup',
  },
  companies: {
    eyebrow: 'YOUR WATCHLIST',
    title: 'Companies',
    description: 'Keep the companies you care about in one place.',
    empty: 'Company monitoring is being built',
    body: 'You’ll be able to follow a company by name or careers URL, choose a check interval, and browse every collected role.',
  },
  profile: {
    eyebrow: 'YOUR DIRECTION',
    title: 'Profile',
    description: 'Your experience is the starting point. Your preferences set the direction.',
    empty: 'Profile setup is being built',
    body: 'You’ll be able to upload a CV, review the extracted experience, choose target roles, and decide whether to explore new domains.',
  },
};
function FoundationPage({ page }: { page: keyof typeof pages }) {
  const data = pages[page];
  return (
    <>
      <p className="eyebrow">{data.eyebrow}</p>
      <h1 tabIndex={-1}>{data.title}</h1>
      <p className="page-description">{data.description}</p>
      <section className="empty-state" aria-labelledby="empty-title">
        <div className="empty-icon">
          <BriefcaseBusiness aria-hidden="true" size={28} />
        </div>
        <h2 id="empty-title">{data.empty}</h2>
        <p>{data.body}</p>
        {'link' in data && (
          <Button asChild>
            <NavLink to={data.link}>
              {data.action}
              <ArrowRight size={18} aria-hidden="true" />
            </NavLink>
          </Button>
        )}
        <p className="preview-note">
          Company monitoring and job matching are still being built. Profile setup is available.
        </p>
      </section>
    </>
  );
}
function Settings() {
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
    </>
  );
}
export function App() {
  const client = useQueryClient();
  const session = useQuery({
    queryKey: ['session'],
    queryFn: api.session,
    staleTime: 30_000,
    refetchInterval: 60_000,
    refetchIntervalInBackground: false,
  });
  useEffect(() => {
    if (session.data === null) {
      client.removeQueries({ predicate: (query) => query.queryKey[0] !== 'session' });
      client.getMutationCache().clear();
    }
  }, [client, session.data]);
  if (session.isPending)
    return (
      <main className="standalone">
        <p role="status">Opening your workspace…</p>
      </main>
    );
  if (session.isError)
    return (
      <main className="standalone">
        <h1>Cannot open your workspace</h1>
        <p role="alert">{errorMessage(session.error)}</p>
        <Button onClick={() => void session.refetch()}>Try again</Button>
      </main>
    );
  if (!session.data) return <Login />;
  return (
    <Routes>
      <Route element={<Shell session={session.data} />}>
        <Route path="/" element={<Navigate to="/jobs" replace />} />
        <Route path="/login" element={<Navigate to="/jobs" replace />} />
        <Route path="/jobs" element={<FoundationPage page="jobs" />} />
        <Route path="/companies" element={<FoundationPage page="companies" />} />
        <Route path="/profile" element={<ProfilePage />} />
        <Route path="/settings" element={<Settings />} />
        <Route
          path="*"
          element={
            <>
              <h1 tabIndex={-1}>Page not found</h1>
              <Button asChild>
                <NavLink to="/jobs">Back to jobs</NavLink>
              </Button>
            </>
          }
        />
      </Route>
    </Routes>
  );
}
